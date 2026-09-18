"""Unit tests for the AI engine, independent of the API."""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture(scope="module")
def references():
    from ai.datasets.reference_species import species_references

    return species_references()


@pytest.fixture(scope="module")
def config():
    from ai.config import AIConfig

    return AIConfig()


# --------------------------------------------------------------------------- #
# calibration
# --------------------------------------------------------------------------- #
def test_standardised_softmax_is_scale_invariant() -> None:
    """The whole point: the confidence must not move when the scale does."""
    from ai.calibration import standardised_softmax

    distances = np.array([0.10, 0.20, 0.25, 0.40])
    small = standardised_softmax(distances, 0.4, higher_is_better=False)
    large = standardised_softmax(distances * 1000, 0.4, higher_is_better=False)
    assert np.allclose(small, large, atol=1e-9)
    assert np.isclose(small.sum(), 1.0)
    assert small.argmax() == 0, "the smallest distance must win"


def test_standardised_softmax_direction() -> None:
    from ai.calibration import standardised_softmax

    similarities = np.array([0.9, 0.5, 0.1])
    scores = standardised_softmax(similarities, 0.4, higher_is_better=True)
    assert scores.argmax() == 0


def test_temperature_controls_sharpness() -> None:
    from ai.calibration import standardised_softmax

    distances = np.array([0.1, 0.3, 0.5, 0.7])
    sharp = standardised_softmax(distances, 0.15, higher_is_better=False)
    flat = standardised_softmax(distances, 1.5, higher_is_better=False)
    assert sharp.max() > flat.max()


def test_reliability_separates_confident_from_ignorant() -> None:
    from ai.calibration import reliability

    confident = np.array([0.9, 0.05, 0.03, 0.02])
    uninformative = np.full(4, 0.25)
    assert reliability(confident) > 0.6
    assert reliability(uninformative) == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------- #
# vision
# --------------------------------------------------------------------------- #
def test_descriptor_and_prototype_share_a_space(references) -> None:
    from ai.preprocessing.image import DESCRIPTOR_LENGTH, image_descriptor
    from ai.vision.baseline import prototype_from_traits

    image = np.full((64, 64, 3), 0.4, dtype=np.float32)
    descriptor = image_descriptor(image)
    prototype = prototype_from_traits(references[0].visual_traits)
    assert descriptor.shape == prototype.shape == (DESCRIPTOR_LENGTH,)
    assert descriptor.min() >= 0.0 and descriptor.max() <= 1.0


def test_prototype_tolerates_missing_traits() -> None:
    """A partially described species must still participate in ranking."""
    from ai.preprocessing.image import DESCRIPTOR_LENGTH
    from ai.vision.baseline import prototype_from_traits

    for traits in ({}, {"pattern": "striped"}, {"dominant_hues": 0.5}):
        assert prototype_from_traits(traits).shape == (DESCRIPTOR_LENGTH,)


def test_discriminative_scale_downweights_constant_dimensions() -> None:
    from ai.vision.baseline import discriminative_scale

    prototypes = np.array(
        [
            [0.5, 0.1, 0.9],
            [0.5, 0.4, 0.2],
            [0.5, 0.8, 0.5],
        ]
    )
    scale = discriminative_scale(prototypes)
    # Dimension 0 is identical for every species, so it carries no information.
    assert scale[0] < scale[1]
    assert scale[0] < scale[2]


def test_vision_ranks_the_matching_species_first(references, config) -> None:
    """A rendered subject should be ranked first by the descriptor classifier."""
    from ai.datasets.synthetic import render_image
    from ai.vision.baseline import BaselineVisionClassifier

    classifier = BaselineVisionClassifier(references, temperature=config.score_temperature)
    rng = np.random.default_rng(3)
    hits = 0
    trials = 0
    for reference in references:
        if not reference.visual_traits:
            continue
        image = render_image(reference.visual_traits, rng, size=160, difficulty=0.0)
        candidates = classifier.classify(image, top_k=5)
        trials += 1
        if reference.label in [candidate.label for candidate in candidates[:5]]:
            hits += 1
    # Textbook renderings with 32 classes: chance top-5 is ~16%.
    assert trials > 20
    assert hits / trials > 0.5, f"top-5 recall was only {hits / trials:.2f}"


def test_vision_pipeline_abstains_on_a_blank_frame(references, config) -> None:
    from ai.vision.pipeline import VisionPipeline, build_vision_pipeline

    pipeline: VisionPipeline = build_vision_pipeline(references, config)
    blank = np.full((128, 128, 3), 0.5, dtype=np.float32)
    prediction = pipeline.predict(blank)
    assert prediction.requires_expert_verification is True
    if not prediction.is_uncertain:
        # If it does commit, it must at least be above the configured threshold.
        assert prediction.confidence >= config.min_confidence
    assert "backend" in prediction.diagnostics


def test_vision_explanation_names_the_deciding_blocks(references, config) -> None:
    from ai.datasets.synthetic import render_image
    from ai.vision.baseline import BaselineVisionClassifier

    classifier = BaselineVisionClassifier(references, temperature=config.score_temperature)
    rng = np.random.default_rng(1)
    image = render_image(references[0].visual_traits, rng, size=128)
    explanation = classifier.explain(image)
    assert explanation["top_label"]
    assert set(explanation["block_contributions"]) == {
        "hue",
        "saturation",
        "value",
        "orientation",
        "texture",
        "region",
        "vegetation",
    }
    assert len(explanation["best_matching_blocks"]) == 3


def test_saliency_detector_finds_a_subject() -> None:
    from ai.vision.detect import saliency_detections

    image = np.full((96, 96, 3), 0.45, dtype=np.float32)
    image[30:60, 20:70] = [0.9, 0.1, 0.1]  # a bright, distinct patch
    detections = saliency_detections(image, max_detections=3)
    assert detections
    x, y, w, h = detections[0].bbox
    assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0
    assert w > 0 and h > 0
    assert 0.0 <= detections[0].score <= 1.0


def test_image_validation_rejects_rubbish() -> None:
    from ai.preprocessing.image import ImageValidationError, inspect_image

    with pytest.raises(ImageValidationError):
        inspect_image(b"")
    with pytest.raises(ImageValidationError, match="not a recognised image"):
        inspect_image(b"#!/bin/sh\necho hello\n")


def test_image_validation_rejects_a_tiny_image() -> None:
    import io

    from ai.preprocessing.image import ImageValidationError, inspect_image
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buffer, format="PNG")
    with pytest.raises(ImageValidationError, match="too small"):
        inspect_image(buffer.getvalue())


# --------------------------------------------------------------------------- #
# audio
# --------------------------------------------------------------------------- #
def test_audio_features_recover_the_synthesised_call() -> None:
    from ai.datasets.reference_species import REFERENCE_SPECIES
    from ai.datasets.synthetic import synthesise_call_wav
    from ai.preprocessing.audio import decode_audio, extract_audio_features

    signature = next(
        row["acoustic_signature"]
        for row in REFERENCE_SPECIES
        if row["common_name"] == "Crimson-backed Sunbird"
    )
    audio = decode_audio(
        synthesise_call_wav(signature, seconds=8.0, seed=13), filename="call.wav"
    )
    features = extract_audio_features(audio)
    assert features.peak_frequency_hz == pytest.approx(signature["peak_hz"], rel=0.05)
    assert features.pulse_rate_hz == pytest.approx(signature["pulse_rate_hz"], rel=0.2)
    assert features.snr_db > 3.0


def test_pulse_rate_reports_zero_for_a_continuous_sound() -> None:
    """Reading rhythm into noise is worse than reporting none."""
    import io
    import wave

    from ai.preprocessing.audio import decode_audio, extract_audio_features

    rng = np.random.default_rng(2)
    samples = (rng.normal(0, 0.25, 22_050 * 5) * 32767 * 0.5).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(22_050)
        handle.writeframes(samples.tobytes())
    features = extract_audio_features(decode_audio(buffer.getvalue(), filename="noise.wav"))
    assert features.pulse_rate_hz == 0.0
    assert features.tonality < 0.5


def test_mel_filterbank_rows_are_normalised() -> None:
    from ai.preprocessing.audio import mel_filterbank

    filters = mel_filterbank(22_050, 1024, 64, fmin=60.0, fmax=10_000.0)
    assert filters.shape == (64, 513)
    row_sums = filters.sum(axis=1)
    assert np.allclose(row_sums[row_sums > 0], 1.0, atol=1e-6)


def test_spectral_gate_lowers_a_constant_noise_floor() -> None:
    from ai.preprocessing.audio import spectral_gate

    power = np.full((32, 100), 1.0)
    power[10, 50] = 20.0  # a transient in one band
    gated = spectral_gate(power, strength=0.9)
    assert gated[0, 0] < power[0, 0]
    assert gated[10, 50] > gated[0, 0] * 5


def test_audio_decoding_rejects_unusable_input() -> None:
    from ai.preprocessing.audio import AudioValidationError, decode_audio

    with pytest.raises(AudioValidationError):
        decode_audio(b"", filename="empty.wav")
    with pytest.raises(AudioValidationError):
        decode_audio(b"RIFFshort", filename="broken.wav")


def test_audio_decoding_rejects_a_recording_that_is_too_short() -> None:
    import io
    import wave

    from ai.preprocessing.audio import AudioValidationError, decode_audio

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(22_050)
        handle.writeframes(np.zeros(100, dtype="<i2").tobytes())
    with pytest.raises(AudioValidationError, match="too short"):
        decode_audio(buffer.getvalue(), filename="blip.wav")


def test_unsupported_format_gives_a_useful_message() -> None:
    from ai.preprocessing import audio as audio_module

    if audio_module._soundfile is not None:  # pragma: no cover - optional dependency
        pytest.skip("soundfile is installed, so compressed formats are supported")
    with pytest.raises(audio_module.AudioValidationError, match="soundfile"):
        audio_module.decode_audio(b"fLaC" + b"\x00" * 1000, filename="call.flac")


def test_audio_classifier_identifies_each_reference_call(references, config) -> None:
    """Template matching on clean synthetic calls should be highly accurate."""
    from ai.audio.baseline import BaselineAudioClassifier
    from ai.datasets.reference_species import REFERENCE_SPECIES
    from ai.datasets.synthetic import synthesise_call_wav
    from ai.preprocessing.audio import decode_audio, extract_audio_features

    classifier = BaselineAudioClassifier(references, temperature=config.audio_temperature)
    audible = [row for row in REFERENCE_SPECIES if row["acoustic_signature"]]
    hits = 0
    for index, row in enumerate(audible):
        audio = decode_audio(
            synthesise_call_wav(row["acoustic_signature"], seconds=8.0, seed=100 + index),
            filename="call.wav",
        )
        features = extract_audio_features(audio)
        candidates = classifier.classify(features, top_k=3)
        if row["common_name"] in [candidate.label for candidate in candidates[:3]]:
            hits += 1
    assert hits / len(audible) > 0.8, f"top-3 recall was {hits / len(audible):.2f}"


def test_audio_pipeline_abstains_on_silence(references, config) -> None:
    import io
    import wave

    from ai.audio.pipeline import build_audio_pipeline

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(22_050)
        handle.writeframes(np.zeros(22_050 * 2, dtype="<i2").tobytes())

    pipeline = build_audio_pipeline(references, config)
    prediction = pipeline.predict(buffer.getvalue(), filename="silence.wav")
    assert prediction.is_uncertain
    assert prediction.label == "UNCERTAIN"
    assert "noise floor" in prediction.diagnostics["reason"]


def test_acoustic_template_scores_are_interpretable() -> None:
    from ai.audio.baseline import feature_match_scores
    from ai.preprocessing.audio import AudioFeatures

    features = AudioFeatures(
        duration_seconds=4.0,
        rms_db=-20.0,
        peak_frequency_hz=2200.0,
        spectral_centroid_hz=2300.0,
        bandwidth_hz=700.0,
        rolloff_95_hz=3600.0,
        pulse_rate_hz=0.6,
        tonality=0.9,
        activity_ratio=0.4,
        snr_db=18.0,
        band_energies=(0.0, 0.02, 0.25, 0.45, 0.2, 0.05, 0.02, 0.01),
    )
    matching = {
        "peak_hz": 2200.0,
        "bandwidth_hz": 700.0,
        "pulse_rate_hz": 0.6,
        "tonality": 0.9,
        "call_duration_s": 2.6,
    }
    wrong = {**matching, "peak_hz": 6000.0, "pulse_rate_hz": 9.0, "tonality": 0.1}

    good_score, good_detail = feature_match_scores(features, matching)
    bad_score, _ = feature_match_scores(features, wrong)
    assert good_score > bad_score
    assert good_detail["peak_hz"] == pytest.approx(1.0, abs=1e-6)
    # An empty signature cannot match anything.
    assert feature_match_scores(features, {}) == (0.0, {})


# --------------------------------------------------------------------------- #
# fusion
# --------------------------------------------------------------------------- #
def _prediction(modality: str, pairs: list[tuple[str, float]], *, uncertain: bool = False):
    from ai.schema import Candidate, Prediction

    top_k = tuple(
        Candidate(species_id=index + 1, label=label, confidence=score)
        for index, (label, score) in enumerate(pairs)
    )
    return Prediction(
        modality=modality,
        model_name=f"test-{modality.lower()}",
        model_version="1",
        label="UNCERTAIN" if uncertain else pairs[0][0],
        confidence=0.0 if uncertain else pairs[0][1],
        is_uncertain=uncertain,
        species_id=None if uncertain else 1,
        top_k=top_k,
    )


def test_agreement_sharpens_the_fused_confidence(config) -> None:
    """Log-linear pooling only extremises when there is something to punish.

    If both modalities happen to give the runner-up *identical* support too,
    there is nothing for "disagreement" to act on and the fused score simply
    sits at the geometric mean of the two — never above the max, since a
    geometric mean of any two positive numbers cannot exceed the larger one.
    The compounding this fusion is designed for shows up once the modalities
    agree on the winner but diverge on who is second: that divergence shrinks
    the losing candidates' pooled score by more than agreement shrinks the
    winner's, which is what should push the fused winner's probability above
    what either modality reported alone.
    """
    from ai.multimodal.fusion import fuse_predictions

    image = _prediction("IMAGE", [("Indian Gaur", 0.6), ("Sambar", 0.25), ("Chital", 0.15)])
    audio = _prediction("AUDIO", [("Indian Gaur", 0.6), ("Chital", 0.25), ("Sambar", 0.15)])
    fused = fuse_predictions(image, audio, config=config)
    assert fused.label == "Indian Gaur"
    assert fused.confidence > max(image.confidence, audio.confidence)
    assert fused.diagnostics["modalities_agree"] is True


def test_identical_runner_up_support_gives_no_extra_sharpening(config) -> None:
    """The companion case: agreement everywhere means fusion changes nothing.

    Both modalities give the runner-up the exact same score as each other, so
    there is no disagreement for log-linear pooling to punish, and the fused
    top-1 probability — bounded above by the larger of two geometric-mean
    inputs — stays at or below the higher of the two raw confidences.
    """
    from ai.multimodal.fusion import fuse_predictions

    image = _prediction("IMAGE", [("Indian Gaur", 0.55), ("Sambar", 0.25), ("Chital", 0.2)])
    audio = _prediction("AUDIO", [("Indian Gaur", 0.6), ("Sambar", 0.25), ("Chital", 0.15)])
    fused = fuse_predictions(image, audio, config=config)
    assert fused.label == "Indian Gaur"
    assert fused.confidence <= max(image.confidence, audio.confidence)
    assert fused.confidence >= min(image.confidence, audio.confidence)


def test_disagreement_is_not_averaged_away(config) -> None:
    """A species one modality rules out must not win on the other's strength."""
    from ai.multimodal.fusion import fuse_predictions

    image = _prediction("IMAGE", [("Indian Gaur", 0.9), ("Sambar", 0.05), ("Chital", 0.05)])
    audio = _prediction("AUDIO", [("Chital", 0.9), ("Sambar", 0.05), ("Indian Gaur", 0.05)])
    fused = fuse_predictions(image, audio, config=config)
    assert fused.diagnostics["modalities_agree"] is False
    # Sambar is mid-ranked by both, so pooling can legitimately prefer it; what
    # must not happen is a confident winner emerging from a flat contradiction.
    assert fused.confidence < 0.9


def test_an_uninformative_modality_is_discounted(config) -> None:
    """The bug this weighting exists to fix: fusion scoring below audio alone."""
    from ai.multimodal.fusion import fuse_predictions

    confident = _prediction("AUDIO", [("Indian Pitta", 0.85), ("Asian Koel", 0.08)])
    clueless = _prediction(
        "IMAGE",
        [("Teak", 0.26), ("Sandalwood", 0.25), ("Rosewood", 0.25), ("Bamboo", 0.24)],
        uncertain=True,
    )
    fused = fuse_predictions(clueless, confident, config=config)
    assert fused.label == "Indian Pitta"
    weights = fused.diagnostics["weights"]
    assert weights["audio"] > weights["image"], weights
    assert fused.diagnostics["reliability"]["image"] < fused.diagnostics["reliability"]["audio"]


def test_fusion_with_one_modality_passes_it_through(config) -> None:
    from ai.multimodal.fusion import fuse_predictions

    image = _prediction("IMAGE", [("Great Hornbill", 0.8), ("Malabar Grey Hornbill", 0.1)])
    fused = fuse_predictions(image, None, config=config)
    assert fused.label == "Great Hornbill"
    assert fused.diagnostics["modalities_used"] == ["IMAGE"]


def test_fusion_with_no_evidence_is_uncertain(config) -> None:
    from ai.multimodal.fusion import fuse_predictions

    fused = fuse_predictions(None, None, config=config)
    assert fused.is_uncertain
    assert "no modality" in fused.diagnostics["reason"]


def test_context_prior_breaks_a_tie_but_cannot_invent_a_detection(config) -> None:
    from ai.multimodal.fusion import context_prior_from_history, fuse_predictions

    image = _prediction("IMAGE", [("Sambar", 0.42), ("Chital", 0.40), ("Indian Gaur", 0.18)])
    audio = _prediction("AUDIO", [("Chital", 0.44), ("Sambar", 0.42), ("Indian Gaur", 0.14)])
    prior = context_prior_from_history({"Chital": 90.0, "Sambar": 4.0}, strength=0.5)

    without = fuse_predictions(image, audio, config=config)
    with_prior = fuse_predictions(image, audio, context_prior=prior, config=config)
    chital_without = next(c.confidence for c in without.top_k if c.label == "Chital")
    chital_with = next(c.confidence for c in with_prior.top_k if c.label == "Chital")
    assert chital_with > chital_without

    # A species neither modality proposed cannot appear from the prior alone.
    heavy = context_prior_from_history({"Bengal Tiger": 10_000.0}, strength=1.0)
    fused = fuse_predictions(image, audio, context_prior=heavy, config=config)
    assert "Bengal Tiger" not in [candidate.label for candidate in fused.top_k]


def test_context_prior_is_bounded() -> None:
    from ai.multimodal.fusion import context_prior_from_history

    prior = context_prior_from_history({"A": 1000.0, "B": 0.0}, strength=0.25)
    assert prior["B"] > 0.0, "an unseen species must be unlikely, not impossible"
    assert prior["A"] < 1.0
    assert context_prior_from_history({}) == {}


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def test_precision_recall_f1_on_a_worked_example() -> None:
    from ai.evaluation.metrics import precision_recall_f1

    truth = ["a", "a", "b", "b", "c"]
    predicted = ["a", "b", "b", "b", "c"]
    report = precision_recall_f1(truth, predicted)
    assert report.precision["a"] == pytest.approx(1.0)
    assert report.recall["a"] == pytest.approx(0.5)
    assert report.f1["a"] == pytest.approx(2 / 3)
    assert report.precision["b"] == pytest.approx(2 / 3)
    assert report.recall["b"] == pytest.approx(1.0)
    assert report.accuracy == pytest.approx(0.8)
    assert report.coverage == pytest.approx(1.0)


def test_abstentions_lower_coverage_not_precision() -> None:
    """A model that declines must not be credited *or* charged for it."""
    from ai.evaluation.metrics import precision_recall_f1

    truth = ["a", "a", "b", "b"]
    predicted = ["a", "UNCERTAIN", "b", "UNCERTAIN"]
    report = precision_recall_f1(truth, predicted)
    assert report.coverage == pytest.approx(0.5)
    assert report.selective_accuracy == pytest.approx(1.0)
    assert report.accuracy == pytest.approx(0.5)
    assert report.precision["a"] == pytest.approx(1.0)
    assert report.recall["a"] == pytest.approx(0.5)


def test_confusion_matrix_keeps_uncertain_as_a_column() -> None:
    from ai.evaluation.metrics import confusion_matrix

    matrix, labels = confusion_matrix(["a", "b"], ["a", "UNCERTAIN"])
    assert labels == ["a", "b", "UNCERTAIN"]
    assert matrix.tolist() == [[1, 0, 0], [0, 0, 1]]


def test_average_precision_on_a_perfect_ranking() -> None:
    from ai.evaluation.metrics import average_precision

    assert average_precision([1, 1, 0, 0], [0.9, 0.8, 0.3, 0.1]) == pytest.approx(1.0)
    assert average_precision([0, 0, 1, 1], [0.9, 0.8, 0.3, 0.1]) < 0.6
    assert average_precision([0, 0], [0.5, 0.4]) == 0.0


def test_mean_average_precision_over_classes() -> None:
    from ai.evaluation.metrics import mean_average_precision

    truth = ["a", "b", "a", "b"]
    scores = [
        {"a": 0.9, "b": 0.1},
        {"a": 0.2, "b": 0.8},
        {"a": 0.7, "b": 0.3},
        {"a": 0.3, "b": 0.7},
    ]
    value, per_class = mean_average_precision(truth, scores)
    assert value == pytest.approx(1.0)
    assert set(per_class) == {"a", "b"}


def test_expected_calibration_error_rewards_honest_confidence() -> None:
    from ai.evaluation.metrics import expected_calibration_error

    # Perfectly calibrated: 90% confident and right 90% of the time.
    correct = [True] * 9 + [False]
    confidence = [0.9] * 10
    assert expected_calibration_error(correct, confidence) == pytest.approx(0.0, abs=0.01)

    # Grossly over-confident.
    overconfident = expected_calibration_error([False] * 10, [0.95] * 10)
    assert overconfident > 0.9


def test_top_k_accuracy() -> None:
    from ai.evaluation.metrics import top_k_accuracy

    truth = ["a", "b", "c"]
    ranked = [["x", "a"], ["b", "y"], ["p", "q"]]
    assert top_k_accuracy(truth, ranked, k=1) == pytest.approx(1 / 3)
    assert top_k_accuracy(truth, ranked, k=2) == pytest.approx(2 / 3)


# --------------------------------------------------------------------------- #
# the experiment harness
# --------------------------------------------------------------------------- #
def test_synthetic_dataset_is_reproducible(references) -> None:
    from ai.datasets.synthetic import generate_dataset

    first = generate_dataset(references, sample_count=40, seed=99)
    second = generate_dataset(references, sample_count=40, seed=99)
    assert [s.label for s in first] == [s.label for s in second]
    assert np.allclose(first[0].image, second[0].image)

    different = generate_dataset(references, sample_count=40, seed=100)
    assert not np.allclose(first[0].image, different[0].image)


def test_every_sample_carries_some_evidence(references) -> None:
    from ai.datasets.synthetic import generate_dataset

    dataset = generate_dataset(
        references, sample_count=80, seed=7, missing_image_rate=0.5, missing_audio_rate=0.5
    )
    assert dataset
    assert all(sample.has_image or sample.has_audio for sample in dataset)


def test_variant_comparison_reports_coverage_and_a_caveat(references, config) -> None:
    from ai.audio.pipeline import build_audio_pipeline
    from ai.datasets.synthetic import generate_dataset
    from ai.evaluation.experiment import compare_variants
    from ai.vision.pipeline import build_vision_pipeline

    dataset = generate_dataset(references, sample_count=48, seed=21)
    report = compare_variants(
        dataset,
        vision=build_vision_pipeline(references, config),
        audio=build_audio_pipeline(references, config),
        variants=("image_only", "audio_only", "image_audio"),
        config=config,
    )
    assert set(report.results) == {"image_only", "audio_only", "image_audio"}
    for result in report.results.values():
        metrics = result.metrics()
        assert 0.0 <= metrics["coverage"] <= 1.0
        assert 0.0 <= metrics["macro_f1"] <= 1.0
        assert metrics["uncertain_share"] + metrics["coverage"] == pytest.approx(1.0, abs=1e-6)
    # The conclusion must never overstate what a synthetic benchmark shows.
    assert "field" in report.conclusion.lower()
    assert report.best_variant in report.results


def test_unknown_variant_is_rejected(references, config) -> None:
    from ai.audio.pipeline import build_audio_pipeline
    from ai.datasets.synthetic import generate_dataset
    from ai.evaluation.experiment import run_variant
    from ai.vision.pipeline import build_vision_pipeline

    dataset = generate_dataset(references, sample_count=8, seed=1)
    with pytest.raises(ValueError, match="unknown variant"):
        run_variant(
            "telepathy",
            dataset,
            vision=build_vision_pipeline(references, config),
            audio=build_audio_pipeline(references, config),
            config=config,
        )


def test_reference_catalogue_is_internally_consistent() -> None:
    """The catalogue is shared by the seed data and the models, so it must hold."""
    from ai.datasets.reference_species import REFERENCE_SPECIES, band_profile_for

    assert len(REFERENCE_SPECIES) >= 30
    names = [row["scientific_name"] for row in REFERENCE_SPECIES]
    assert len(names) == len(set(names)), "duplicate scientific name"
    for row in REFERENCE_SPECIES:
        assert row["category"] in {
            "MAMMAL",
            "BIRD",
            "PLANT",
            "REPTILE",
            "AMPHIBIAN",
            "INSECT",
            "FUNGI",
            "OTHER",
        }
        assert row["conservation_status"] in {
            "EX", "EW", "CR", "EN", "VU", "NT", "LC", "DD", "NE",
        }
        signature = row.get("acoustic_signature") or {}
        if signature:
            profile = signature["band_profile"]
            assert len(profile) == 8
            assert sum(profile) == pytest.approx(1.0, abs=1e-3)
            assert profile == band_profile_for(
                signature["peak_hz"], signature["bandwidth_hz"]
            )
        traits = row.get("visual_traits") or {}
        if traits:
            assert 0.0 <= traits["saturation"] <= 1.0
            assert 0.0 <= traits["brightness"] <= 1.0
            assert all(0.0 <= hue <= 1.0 for hue in traits["dominant_hues"])
