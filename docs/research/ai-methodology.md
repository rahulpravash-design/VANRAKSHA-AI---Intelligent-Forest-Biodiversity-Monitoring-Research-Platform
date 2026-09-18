# AI methodology, honestly stated

This document exists so nobody — including a future contributor — mistakes
what the shipped baselines can do for what a validated field system can do.

## The two backends, and what "baseline" actually means

Every pipeline in `ai/` (vision, audio) has a **baseline** backend that
depends only on NumPy and Pillow, and an optional **trained** backend
(Ultralytics YOLO for vision, a small CNN for audio) that activates once
weights are configured. The platform — API, tests, the seed dataset, the
research comparison — runs meaningfully on the baseline alone. That is a
deliberate choice, not a shortcut taken because training a model was out of
scope:

* it keeps the whole system reproducible on any machine, with no model
  download and no GPU;
* it is fully inspectable — every classification's `explain()` method
  reports exactly which measured quantities (hue histogram, texture, call
  peak frequency, pulse rate, …) drove the ranking;
* it gives the verification workflow, the anomaly detector, and the
  analytics module something real to operate on while a forest-specific
  trained model is still being collected for.

### Vision baseline: what it is and its real limits

A **nearest-prototype classifier in a 44-dimensional interpretable descriptor
space** (`ai/preprocessing/image.py`): hue/saturation/value histograms,
an 8-bin gradient-orientation profile, texture statistics, subject geometry,
and vegetation/scene cues, computed over a saliency-weighted crop of the
detected subject. Each reference species contributes a synthetic prototype
built from its `visual_traits` record
(`ai/vision/baseline.py::prototype_from_traits`), and classification is a
per-dimension-weighted distance (the weights are *learned from the reference
set itself* — `discriminative_scale` — so a descriptor dimension every
species agrees on cannot dominate the metric) turned into a confidence via a
standardised softmax.

On the seeded synthetic benchmark (`ai/datasets/synthetic.py`, 32 classes)
this reaches roughly 25-30% top-1 and ~50% top-5 accuracy at moderate
difficulty — informative, well above the ~3% top-1 chance rate, and
**nowhere near what a trained detector achieves on real camera-trap
imagery**. Concretely, it cannot:

* separate congeners that differ mainly in fine markings rather than gross
  colour/pattern/shape (e.g. `Panthera tigris` vs `Panthera pardus` at a
  distance, in dim light);
* handle a photograph where the saliency-based subject detector picks the
  wrong region (dense foliage, multiple animals, strong backlighting);
* generalise beyond the hand-authored trait priors in
  `ai/datasets/reference_species.py` — a species added without a
  `visual_traits` record simply cannot be matched by image.

### Audio baseline: what it is and its real limits

**Acoustic template matching** (`ai/audio/baseline.py`): five interpretable
call parameters — peak frequency, bandwidth (a half-power width localised
around the dominant tone, not the whole spectrum's second moment; see the
bandwidth note below), pulse rate, tonality, and an 8-band energy
profile — matched against each species' `acoustic_signature` with
per-parameter Gaussian scoring, combined in log-space and turned into a
confidence the same standardised-softmax way as vision.

On synthesised calls that match the reference signatures closely (the
seeded benchmark), this reaches **23/23 (100%) top-3 and ~87% top-1**
recall across the catalogue — genuinely strong, because template matching on
clean, well-separated call parameters is close to the classical bioacoustics
method's best case. Two things temper that number:

* the benchmark's synthetic calls are generated *from the same signatures*
  the classifier matches against, with controlled noise — real field
  recordings carry overlapping calls, wind, insects, rain, and equipment
  noise that this benchmark does not model;
* pulse-rate detection requires roughly two full periods after its own
  detection lag to confirm periodicity (a deliberate guard — see below), so
  a very low pulse rate (e.g. a tiger's ~0.3 Hz roar cadence) needs a longer
  recording than a high one to be recovered at all.

**Pulse-rate detection is autocorrelation-based with a harmonic-recurrence
guard**: a candidate lag is only accepted if the recording's autocorrelation
also shows a second peak near twice that lag (`ai/preprocessing/audio.py::
_pulse_rate`). This exists because a naive "strongest correlation peak" test
routinely finds a spurious ~0.25-0.3 correlation in pure noise — testing
roughly 200 candidate lags for significance without correction makes at
least one exceeding a fixed absolute threshold the expected outcome, not the
exception. A genuinely periodic call, by contrast, correlates with itself at
every multiple of its own period. This was caught by
`test_pulse_rate_reports_zero_for_a_continuous_sound` reading noise as a
4.3 Hz pulse before the fix.

## An AI output is never taxonomy

Every prediction the API returns carries `is_uncertain`, the ranked
alternatives (`top_k`), the exact model name and version, and
`requires_expert_verification: true` — and the response schema's
`identification_basis` field states "AI-assisted identification — not
confirmed taxonomy" explicitly (`app/schemas/ai.py`). An observation's
`species_id` is set only by the human who recorded it;
`verified_species_id` only by an expert's decision
(`app/services/verification_service.py`). Nothing in the pipeline ever
writes a model's guess into either field.

Below the configured confidence or margin threshold
(`AI_MIN_CONFIDENCE`, `AI_UNCERTAIN_MARGIN`), a pipeline returns the explicit
label `UNCERTAIN` rather than a low-confidence species name — this is the
single gate both modalities and the fusion layer share
(`ai/vision/pipeline.py`, `ai/audio/pipeline.py`,
`ai/multimodal/fusion.py`), so a caller can never mistake "the model
declined to answer" for "the model answered with low confidence."

## Multimodal fusion: a hypothesis, tested, not assumed

`ai/multimodal/fusion.py` combines image and audio evidence with a
**reliability-weighted log-linear pool**: each modality's distribution is
discounted by its own peakedness (`ai/calibration.py::reliability`) before
combining, so a modality that is close to uniform — "I don't know" — cannot
dilute a confident partner just because its configured weight happens to be
larger. This exists because the naive fixed-weight version measurably made
fusion score *below* the better single modality on the reference benchmark;
see the commit history for the before/after numbers.

Whether fusion helps is answered empirically, per deployment, by
`POST /api/v1/research/{id}/run` — comparing `image_only`, `audio_only`,
`image_audio`, and `image_audio_context` on one identical split with one
seed (`ai/evaluation/experiment.py`). The comparison reports **coverage**
(how often a variant commits) and **mean average precision** alongside
macro-F1, because a variant that answers less often is not thereby "worse"
in the way a single accuracy number implies, and log-linear pooling's
extremisation effect only shows up when modalities agree on the winner but
diverge on the runners-up — two distributions that already agree everywhere
change nothing by being combined. See
`test_agreement_sharpens_the_fused_confidence` and its companion test in
`backend/tests/test_ai_engine.py` for a worked example either way.

## Anomaly detection: a detector, not a diagnosis

`ai/anomaly` combines a median/MAD robust baseline with a NumPy-native
Isolation Forest, and reports a window as anomalous only when the forest
actually has discriminating power in that window
(`IsolationForest.score_spread` — a perfectly steady baseline would otherwise
score every window as anomalous purely by construction, caught by
`test_steady_history_raises_nothing`). It windows up to a caller-supplied
`end_date`, not merely the last day with data — a zone that has gone
completely silent is exactly the pattern this needs to catch, and anchoring
to the last populated day would make silence invisible to it.

It never asserts a cause. `candidate_causes()` ranks plausible explanations
from the evidence available (an incomplete window promotes a data-gap
hypothesis; a device that stopped reporting promotes sensor malfunction);
the wording "poaching" or "illegal" never appears anywhere the detector
writes. `confirmed_cause` on an `Alert` is the one field only a human,
closing the alert after investigation, may set — enforced by the API
refusing to close an alert without resolution notes.

## Evaluation

`ai/evaluation/metrics.py` treats an abstention (`UNCERTAIN`) as neither
correct nor incorrect: `coverage` reports how often a model committed,
`selective_accuracy` how well it did when it committed, and plain
`accuracy` counts an abstention as a miss — reporting only one of the three
is exactly how an abstaining model gets flattered or unfairly penalised.
Expected calibration error is reported because an over-confident model is a
specific danger in a verification workflow: reviewers start trusting scores
that have not earned it.

## What would change these numbers

Real forest deployment is what turns these baselines into a validated
system: `ai/training/train_vision.py` and `ai/training/train_audio.py` fine-
tune the trained backends on labelled field data, grouped by recording (not
by clip) so validation never leaks across a source recording. Once weights
exist, setting `AI_VISION_WEIGHTS` / `AI_AUDIO_WEIGHTS` swaps the backend
with no other code change, and re-running the research module's
`dataset="verified"` mode reports real, field-measured performance instead
of the synthetic benchmark's relative ordering.
