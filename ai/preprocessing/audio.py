"""Audio decoding, noise reduction, mel spectrograms and acoustic features.

WAV/PCM is decoded with the standard library so field recordings work with no
native dependencies.  Compressed formats (FLAC/OGG/MP3) are decoded through
``soundfile`` when it is installed; otherwise the caller gets a clear
:class:`AudioValidationError` instead of a silent failure.

The pipeline follows classical bioacoustics:

    samples → resample → pre-emphasis → STFT → mel filterbank
            → spectral gating (noise reduction) → log-mel
            → acoustic features (peak band, bandwidth, pulse rate, tonality)
"""

from __future__ import annotations

import io
import math
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

try:  # pragma: no cover - optional
    import soundfile as _soundfile
except ImportError:  # pragma: no cover
    _soundfile = None

NATIVE_EXTENSIONS = {".wav", ".wave"}
SOUNDFILE_EXTENSIONS = {".flac", ".ogg", ".oga", ".opus", ".aiff", ".aif", ".mp3"}
MIN_DURATION_SECONDS = 0.20
#: Autocorrelation strength a pulse-rate estimate must reach to be reported.
MIN_PULSE_CORRELATION = 0.25
#: How far the peak must stand above the rest of the search window.
MIN_PULSE_PROMINENCE = 0.10
#: Minimum correlation required at 2x the candidate lag — real periodicity
#: recurs at harmonics of its own period; a single chance spike does not.
MIN_PULSE_HARMONIC = 0.12
MAX_DURATION_SECONDS = 600.0


class AudioValidationError(ValueError):
    """Raised when an upload is not usable audio."""


@dataclass(frozen=True)
class DecodedAudio:
    samples: np.ndarray  # mono float32 in [-1, 1]
    sample_rate: int
    duration_seconds: float
    channels_original: int
    source_format: str

    @property
    def is_silent(self) -> bool:
        return float(np.abs(self.samples).max(initial=0.0)) < 1e-4


@dataclass(frozen=True)
class AudioFeatures:
    """Interpretable acoustic descriptors used by the baseline classifier."""

    duration_seconds: float
    rms_db: float
    peak_frequency_hz: float
    spectral_centroid_hz: float
    bandwidth_hz: float
    rolloff_95_hz: float
    #: Repetition rate of the energy envelope — syllables or wing-beats per second.
    pulse_rate_hz: float
    #: 0 = broadband/noisy (rustling, rain), 1 = pure tone (whistle).
    tonality: float
    #: Share of the recording that is above the estimated noise floor.
    activity_ratio: float
    #: Estimated signal-to-noise ratio after spectral gating, in dB.
    snr_db: float
    band_energies: tuple[float, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, float | list[float]]:
        data = asdict(self)
        data["band_energies"] = [round(float(v), 6) for v in self.band_energies]
        return {
            k: (round(float(v), 6) if isinstance(v, int | float) else v)
            for k, v in data.items()
        }


# --------------------------------------------------------------------------- #
# decoding
# --------------------------------------------------------------------------- #
def _pcm_to_float(frames: bytes, width: int) -> np.ndarray:
    """Convert interleaved PCM frames to float32 in ``[-1, 1]``.

    Handles the sample widths field recorders actually produce, including the
    24-bit packed format that ``wave`` exposes as raw bytes.
    """
    if width == 1:  # 8-bit WAV is unsigned by specification
        return (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    if width == 2:
        return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32_768.0
    if width == 3:
        raw = np.frombuffer(frames, dtype=np.uint8)
        usable = (raw.size // 3) * 3
        triplets = raw[:usable].reshape(-1, 3).astype(np.int32)
        packed = triplets[:, 0] | (triplets[:, 1] << 8) | (triplets[:, 2] << 16)
        signed = np.where(packed & 0x800000, packed - 0x1000000, packed)
        return signed.astype(np.float32) / 8_388_608.0
    if width == 4:
        return np.frombuffer(frames, dtype="<i4").astype(np.float32) / 2_147_483_648.0
    raise AudioValidationError(f"unsupported WAV sample width: {width} bytes")


def _decode_wav(data: bytes) -> tuple[np.ndarray, int, int]:
    try:
        with wave.open(io.BytesIO(data), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            frames = handle.readframes(handle.getnframes())
    except (wave.Error, EOFError) as exc:
        raise AudioValidationError(f"not a readable WAV file: {exc}") from exc
    if not frames:
        raise AudioValidationError("WAV file contains no audio frames")
    if channels < 1:  # pragma: no cover - malformed header
        raise AudioValidationError("WAV file declares no audio channels")

    samples = _pcm_to_float(frames, width)
    if channels > 1:
        usable = (samples.size // channels) * channels
        samples = samples[:usable].reshape(-1, channels).mean(axis=1)
    return samples.astype(np.float32), rate, channels


def decode_audio(
    source: bytes | str | Path,
    *,
    filename: str | None = None,
    target_sample_rate: int = 22_050,
    max_seconds: float = MAX_DURATION_SECONDS,
) -> DecodedAudio:
    """Decode audio to mono float32 at ``target_sample_rate``."""
    if isinstance(source, str | Path):
        path = Path(source)
        filename = filename or path.name
        data = path.read_bytes()
    else:
        data = source
    if not data:
        raise AudioValidationError("empty file")

    suffix = Path(filename or "").suffix.lower()
    is_riff = data[:4] == b"RIFF"
    if is_riff or suffix in NATIVE_EXTENSIONS:
        samples, rate, channels = _decode_wav(data)
        source_format = "WAV"
    elif _soundfile is not None:
        try:
            samples, rate = _soundfile.read(io.BytesIO(data), dtype="float32", always_2d=True)
        except Exception as exc:  # pragma: no cover - depends on libsndfile
            raise AudioValidationError(f"audio could not be decoded: {exc}") from exc
        channels = samples.shape[1]
        samples = samples.mean(axis=1)
        source_format = suffix.lstrip(".").upper() or "UNKNOWN"
    else:
        supported = ", ".join(sorted(NATIVE_EXTENSIONS))
        raise AudioValidationError(
            f"'{suffix or 'unknown'}' audio needs the optional 'soundfile' package; "
            f"natively supported formats: {supported}"
        )

    if rate <= 0:  # pragma: no cover - malformed header
        raise AudioValidationError("audio has an invalid sample rate")
    duration = len(samples) / float(rate)
    if duration < MIN_DURATION_SECONDS:
        raise AudioValidationError(
            f"recording is too short ({duration:.2f}s); minimum is {MIN_DURATION_SECONDS}s"
        )
    if duration > max_seconds:
        keep = int(max_seconds * rate)
        samples = samples[:keep]
        duration = max_seconds

    samples = np.nan_to_num(np.asarray(samples, dtype=np.float32), nan=0.0)
    if rate != target_sample_rate:
        samples = resample_linear(samples, rate, target_sample_rate)
        rate = target_sample_rate
    peak = float(np.abs(samples).max(initial=0.0))
    if peak > 1.0:
        samples = samples / peak
    return DecodedAudio(
        samples=samples.astype(np.float32),
        sample_rate=rate,
        duration_seconds=len(samples) / float(rate),
        channels_original=channels,
        source_format=source_format,
    )


def resample_linear(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """Band-limited-enough linear resampling.

    Field recordings are analysed in the mel domain where linear interpolation
    error is well below the mel bin width, so a full polyphase filter would add
    a heavy dependency for no measurable benefit.
    """
    if source_rate == target_rate or samples.size == 0:
        return samples
    duration = samples.size / float(source_rate)
    target_length = max(1, int(round(duration * target_rate)))
    source_positions = np.linspace(0.0, duration, num=samples.size, endpoint=False)
    target_positions = np.linspace(0.0, duration, num=target_length, endpoint=False)
    return np.interp(target_positions, source_positions, samples).astype(np.float32)


# --------------------------------------------------------------------------- #
# spectral analysis
# --------------------------------------------------------------------------- #
def hz_to_mel(hz: np.ndarray | float) -> np.ndarray | float:
    return 2595.0 * np.log10(1.0 + np.asarray(hz, dtype=np.float64) / 700.0)


def mel_to_hz(mel: np.ndarray | float) -> np.ndarray | float:
    return 700.0 * (10.0 ** (np.asarray(mel, dtype=np.float64) / 2595.0) - 1.0)


def mel_filterbank(
    sample_rate: int, n_fft: int, n_mels: int, fmin: float = 60.0, fmax: float | None = None
) -> np.ndarray:
    """Triangular mel filterbank of shape ``(n_mels, n_fft // 2 + 1)``."""
    fmax = min(fmax or sample_rate / 2.0, sample_rate / 2.0)
    n_bins = n_fft // 2 + 1
    fft_freqs = np.linspace(0.0, sample_rate / 2.0, n_bins)
    mel_points = np.linspace(hz_to_mel(fmin), hz_to_mel(fmax), n_mels + 2)
    hz_points = np.asarray(mel_to_hz(mel_points), dtype=np.float64)

    filters = np.zeros((n_mels, n_bins), dtype=np.float64)
    for index in range(n_mels):
        left, centre, right = hz_points[index : index + 3]
        if right <= left:  # pragma: no cover - degenerate configuration
            continue
        rising = (fft_freqs - left) / max(centre - left, 1e-9)
        falling = (right - fft_freqs) / max(right - centre, 1e-9)
        filters[index] = np.clip(np.minimum(rising, falling), 0.0, None)
        area = filters[index].sum()
        if area > 0:
            filters[index] /= area
    return filters


def stft_power(
    samples: np.ndarray, n_fft: int = 1024, hop_length: int = 256, pre_emphasis: float = 0.97
) -> np.ndarray:
    """Power spectrogram of shape ``(n_fft // 2 + 1, n_frames)``."""
    if samples.size < n_fft:
        samples = np.pad(samples, (0, n_fft - samples.size))
    if pre_emphasis:
        samples = np.append(samples[0], samples[1:] - pre_emphasis * samples[:-1])
    window = np.hanning(n_fft).astype(np.float32)
    n_frames = 1 + (samples.size - n_fft) // hop_length
    indices = np.arange(n_fft)[None, :] + hop_length * np.arange(n_frames)[:, None]
    frames = samples[indices] * window
    spectrum = np.fft.rfft(frames, n=n_fft, axis=1)
    return (np.abs(spectrum) ** 2).T.astype(np.float64)


def spectral_gate(power: np.ndarray, strength: float = 0.6, percentile: float = 20.0) -> np.ndarray:
    """Per-band spectral subtraction against a percentile noise floor.

    Forest recordings have a persistent background (wind, insects, distant
    water).  Estimating the floor per frequency band and subtracting a fraction
    of it is the standard first step before classification; ``strength`` scales
    how much of the estimated floor is removed.
    """
    if power.size == 0:
        return power
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength == 0.0:
        return power
    floor = np.percentile(power, percentile, axis=1, keepdims=True)
    gated = power - strength * floor
    return np.maximum(gated, power * 0.02)


def mel_spectrogram(
    samples: np.ndarray,
    sample_rate: int,
    *,
    n_fft: int = 1024,
    hop_length: int = 256,
    n_mels: int = 64,
    fmin: float = 60.0,
    fmax: float | None = 10_000.0,
    noise_reduction: float = 0.6,
    to_db: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(mel_spectrogram, mel_centre_frequencies_hz)``."""
    power = stft_power(samples, n_fft=n_fft, hop_length=hop_length)
    power = spectral_gate(power, strength=noise_reduction)
    filters = mel_filterbank(sample_rate, n_fft, n_mels, fmin=fmin, fmax=fmax)
    mel = filters @ power
    mel_freqs = np.asarray(
        mel_to_hz(np.linspace(hz_to_mel(fmin), hz_to_mel(min(fmax or sample_rate / 2,
                                                             sample_rate / 2)), n_mels + 2))[1:-1]
    )
    if to_db:
        reference = max(mel.max(), 1e-10)
        mel = 10.0 * np.log10(np.maximum(mel, reference * 1e-8) / reference)
    return mel, mel_freqs


# --------------------------------------------------------------------------- #
# feature extraction
# --------------------------------------------------------------------------- #
def _pulse_rate(envelope: np.ndarray, frames_per_second: float) -> float:
    """Dominant repetition rate of the energy envelope, in pulses per second.

    Estimated by autocorrelation, with the two corrections that make the
    estimate usable on field recordings:

    1. **Detrending.** A recording that simply gets louder produces a
       monotonically decaying autocorrelation, whose maximum is always the
       smallest allowed lag.  Subtracting a one-second moving average removes
       that drift before correlating.
    2. **Main-lobe rejection.** Every autocorrelation peaks at lag 0 and decays
       through a main lobe; searching for the maximum from lag 1 just re-finds
       that slope.  The search therefore starts after the first local minimum,
       which is where genuine periodicity shows up.

    Returns ``0.0`` when no convincing periodicity is present — a continuous
    call, or noise.
    """
    if envelope.size < 12 or frames_per_second <= 0:
        return 0.0

    # -- 1. detrend ---------------------------------------------------------
    trend_window = max(3, int(frames_per_second))
    if envelope.size > trend_window * 2:
        kernel = np.ones(trend_window) / trend_window
        trend = np.convolve(envelope, kernel, mode="same")
        signal = envelope - trend
    else:
        signal = envelope - envelope.mean()

    energy = float(np.dot(signal, signal))
    if energy <= 1e-12:
        return 0.0
    correlation = np.correlate(signal, signal, mode="full")[signal.size - 1 :] / energy

    min_lag = max(2, int(frames_per_second / 20.0))  # up to 20 pulses/second
    # Down to 0.25 Hz, but never beyond half the recording: a "period" seen
    # fewer than twice is not evidence of rhythm.
    max_lag = min(correlation.size // 2, int(frames_per_second / 0.25))
    if max_lag <= min_lag:
        return 0.0

    # -- 2. skip the main lobe ---------------------------------------------
    rising = np.flatnonzero(np.diff(correlation[: max_lag + 1]) > 0)
    search_start = max(min_lag, int(rising[0]) + 1) if rising.size else min_lag
    if search_start >= max_lag:
        return 0.0

    window = correlation[search_start : max_lag + 1]
    best = int(np.argmax(window)) + search_start
    # Three guards against reading rhythm into noise: the peak must be strong in
    # absolute terms, it must stand out from the rest of the search window, and
    # — the guard that actually separates a real pulse train from a chance
    # spike — it must recur near twice its own lag. A genuinely periodic call
    # correlates with itself at every multiple of its period (a whistled trill
    # repeating every 1.4 s also half-repeats at 2.8 s, 4.2 s, ...), so its
    # autocorrelation stays well above zero at 2x the candidate lag. Finite
    # noise routinely produces one spurious peak from chance alone — this
    # search tests roughly two hundred candidate lags, so a single peak
    # clearing an absolute threshold is expected even with no periodicity at
    # all — but a *second* peak at exactly double that lag is not.
    prominence = float(correlation[best] - np.median(window))
    if correlation[best] < MIN_PULSE_CORRELATION or prominence < MIN_PULSE_PROMINENCE:
        return 0.0
    second_harmonic_lag = min(2 * best, correlation.size - 1)
    if second_harmonic_lag > best and correlation[second_harmonic_lag] < MIN_PULSE_HARMONIC:
        return 0.0

    # Parabolic interpolation around the peak sharpens the period estimate.
    if 0 < best < correlation.size - 1:
        left, centre, right = correlation[best - 1], correlation[best], correlation[best + 1]
        denominator = left - 2.0 * centre + right
        if abs(denominator) > 1e-9:
            best = best + 0.5 * (left - right) / denominator

    return float(frames_per_second / max(best, 1e-9))


def _peak_local_bandwidth(spectrum: np.ndarray, freqs: np.ndarray, peak_index: int) -> float:
    """Half-power (-3 dB) width of the contiguous band around ``peak_index``.

    Walks outward from the peak bin while the spectrum stays above half the
    peak's power, then stops — so a second harmonic or an unrelated noise band
    a few hundred hertz away does not get folded into "how wide is this call".
    """
    if spectrum.size == 0 or peak_index < 0 or peak_index >= spectrum.size:
        return 0.0
    peak_power = float(spectrum[peak_index])
    if peak_power <= 0:
        return 0.0
    threshold = peak_power * 0.5
    left = peak_index
    while left > 0 and spectrum[left - 1] >= threshold:
        left -= 1
    right = peak_index
    last = spectrum.size - 1
    while right < last and spectrum[right + 1] >= threshold:
        right += 1
    return float(freqs[right] - freqs[left])


def extract_audio_features(
    audio: DecodedAudio,
    *,
    n_fft: int = 1024,
    hop_length: int = 256,
    n_mels: int = 64,
    fmin: float = 60.0,
    fmax: float = 10_000.0,
    noise_reduction: float = 0.6,
    n_bands: int = 8,
) -> AudioFeatures:
    """Compute the interpretable acoustic feature set for one recording."""
    raw_power = stft_power(audio.samples, n_fft=n_fft, hop_length=hop_length)
    gated_power = spectral_gate(raw_power, strength=noise_reduction)
    filters = mel_filterbank(audio.sample_rate, n_fft, n_mels, fmin=fmin, fmax=fmax)
    mel = filters @ gated_power
    mel_total = mel.sum()
    fft_freqs = np.linspace(0.0, audio.sample_rate / 2.0, raw_power.shape[0])

    spectrum = gated_power.mean(axis=1)
    spectrum_sum = spectrum.sum()
    if spectrum_sum <= 1e-20:
        centroid = bandwidth = rolloff = peak_hz = 0.0
    else:
        probabilities = spectrum / spectrum_sum
        centroid = float((fft_freqs * probabilities).sum())
        cumulative = np.cumsum(probabilities)
        rolloff = float(fft_freqs[int(np.searchsorted(cumulative, 0.95))])
        peak_index = int(np.argmax(spectrum))
        peak_hz = float(fft_freqs[peak_index])
        # "Bandwidth" is the half-power width of the band around the dominant
        # tone, not the second moment of the whole spectrum. A whistle's own
        # second harmonic, or broadband insect/rain noise elsewhere in the
        # recording, sits far from the call itself; folding it into the spread
        # would report a call five times wider than the sound anyone hears as
        # "the call". This is also the standard bioacoustic convention (a
        # -3 dB bandwidth around the peak), and it is what the reference
        # ``acoustic_signature.bandwidth_hz`` values in the catalogue describe.
        bandwidth = _peak_local_bandwidth(spectrum, fft_freqs, peak_index)

    # Tonality: geometric/arithmetic mean ratio (spectral flatness), inverted.
    positive = np.maximum(spectrum, 1e-20)
    flatness = float(np.exp(np.log(positive).mean()) / (positive.mean() + 1e-20))
    tonality = float(np.clip(1.0 - flatness, 0.0, 1.0))

    envelope = mel.sum(axis=0)
    frames_per_second = audio.sample_rate / float(hop_length)
    pulse = _pulse_rate(envelope, frames_per_second)

    noise_floor = float(np.percentile(envelope, 20.0)) if envelope.size else 0.0
    activity = float((envelope > noise_floor * 2.0).mean()) if envelope.size else 0.0
    signal_level = float(np.percentile(envelope, 90.0)) if envelope.size else 0.0
    snr_db = 10.0 * math.log10(max(signal_level, 1e-20) / max(noise_floor, 1e-20))

    rms = float(np.sqrt(np.mean(np.square(audio.samples)))) if audio.samples.size else 0.0
    rms_db = 20.0 * math.log10(max(rms, 1e-9))

    if mel_total > 0:
        band_edges = np.linspace(0, n_mels, n_bands + 1).astype(int)
        band_energies = tuple(
            float(mel[band_edges[i] : band_edges[i + 1]].sum() / mel_total) for i in range(n_bands)
        )
    else:
        band_energies = tuple([1.0 / n_bands] * n_bands)

    return AudioFeatures(
        duration_seconds=round(audio.duration_seconds, 3),
        rms_db=rms_db,
        peak_frequency_hz=peak_hz,
        spectral_centroid_hz=centroid,
        bandwidth_hz=bandwidth,
        rolloff_95_hz=rolloff,
        pulse_rate_hz=pulse,
        tonality=tonality,
        activity_ratio=activity,
        snr_db=snr_db,
        band_energies=band_energies,
    )


def write_spectrogram_png(
    audio: DecodedAudio,
    destination: str | Path,
    *,
    n_fft: int = 1024,
    hop_length: int = 256,
    n_mels: int = 128,
    fmin: float = 60.0,
    fmax: float = 10_000.0,
    noise_reduction: float = 0.6,
    height: int = 256,
    max_width: int = 1200,
) -> Path:
    """Render a log-mel spectrogram as a PNG for display beside the recording."""
    from PIL import Image  # imported lazily so audio decoding needs no Pillow

    mel_db, _ = mel_spectrogram(
        audio.samples,
        audio.sample_rate,
        n_fft=n_fft,
        hop_length=hop_length,
        n_mels=n_mels,
        fmin=fmin,
        fmax=fmax,
        noise_reduction=noise_reduction,
        to_db=True,
    )
    normalised = np.clip((mel_db + 80.0) / 80.0, 0.0, 1.0)
    normalised = np.flipud(normalised)  # low frequencies at the bottom

    # A perceptually ordered forest palette: deep canopy → moss → amber call.
    stops = np.array(
        [
            [8, 16, 24],
            [12, 46, 52],
            [18, 86, 74],
            [86, 140, 62],
            [196, 176, 74],
            [240, 214, 140],
        ],
        dtype=np.float64,
    )
    positions = np.linspace(0.0, 1.0, len(stops))
    flat = normalised.reshape(-1)
    rgb = np.stack(
        [np.interp(flat, positions, stops[:, channel]) for channel in range(3)], axis=-1
    ).reshape(*normalised.shape, 3)

    image = Image.fromarray(rgb.astype(np.uint8), mode="RGB")
    width = min(max(image.width, 320), max_width)
    image = image.resize((width, height), Image.BILINEAR)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)
    return destination
