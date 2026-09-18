"""The reference species catalogue for the Western Ghats deployment.

This module is the single source of truth for the species the platform ships
with: the backend seed script (``scripts/seed.py``) writes these rows into the
``species`` table, and the AI baselines read the same ``visual_traits`` and
``acoustic_signature`` records as their reference descriptors.  Keeping one copy
means the database and the models can never disagree about what a species looks
or sounds like.

Conservation statuses follow the IUCN Red List categories.  The trait and
signature values are *reference priors for identification*, compiled to
represent the published field characteristics of each taxon — they are inputs to
a matching algorithm, not measurements from a specific individual, and the
platform presents every resulting identification as AI-assisted and pending
expert verification.

``is_location_sensitive`` is set for taxa whose precise localities should not be
exposed to unprivileged viewers — large mammals subject to poaching pressure and
the high-value timber and sandalwood species — in addition to the automatic
generalisation applied to every threatened (CR/EN/VU) taxon.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ai.preprocessing.audio import hz_to_mel, mel_to_hz
from ai.schema import SpeciesReference

N_MELS = 64
N_BANDS = 8
FMIN_HZ = 60.0
FMAX_HZ = 10_000.0


def _mel_centres(n_mels: int = N_MELS) -> np.ndarray:
    points = np.linspace(hz_to_mel(FMIN_HZ), hz_to_mel(FMAX_HZ), n_mels + 2)
    return np.asarray(mel_to_hz(points))[1:-1]


def band_profile_for(
    peak_hz: float, bandwidth_hz: float, *, n_mels: int = N_MELS, n_bands: int = N_BANDS
) -> list[float]:
    """Expected 8-band energy profile for a call of given peak and bandwidth.

    Derived from the same mel band layout that
    :func:`ai.preprocessing.audio.extract_audio_features` aggregates over, so the
    reference profile and the measured profile are directly comparable instead of
    being two independently hand-tuned vectors.
    """
    centres = _mel_centres(n_mels)
    sigma = max(float(bandwidth_hz), 60.0)
    energy = np.exp(-0.5 * ((centres - float(peak_hz)) / sigma) ** 2)
    edges = np.linspace(0, n_mels, n_bands + 1).astype(int)
    bands = np.array([energy[edges[i] : edges[i + 1]].sum() for i in range(n_bands)])
    total = bands.sum()
    if total <= 0:  # pragma: no cover - only for out-of-range peaks
        return [round(1.0 / n_bands, 6)] * n_bands
    return [round(float(v), 6) for v in bands / total]


def _acoustic(
    peak_hz: float,
    bandwidth_hz: float,
    pulse_rate_hz: float,
    tonality: float,
    call_duration_s: float,
    vocal_type: str,
    *,
    peak_tolerance: float | None = None,
    pulse_tolerance: float | None = None,
) -> dict[str, Any]:
    return {
        "peak_hz": peak_hz,
        "peak_hz_tolerance": peak_tolerance or max(peak_hz * 0.35, 150.0),
        "bandwidth_hz": bandwidth_hz,
        "pulse_rate_hz": pulse_rate_hz,
        "pulse_rate_tolerance": pulse_tolerance or max(pulse_rate_hz * 0.45, 0.9),
        "tonality": tonality,
        "call_duration_s": call_duration_s,
        "vocal_type": vocal_type,
        "band_profile": band_profile_for(peak_hz, bandwidth_hz),
    }


def _visual(
    dominant_hues: list[float],
    saturation: float,
    brightness: float,
    pattern: str,
    edge_density: float,
    body_aspect: float,
    subject_fill: float,
    scene: str,
) -> dict[str, Any]:
    return {
        "dominant_hues": dominant_hues,
        "saturation": saturation,
        "brightness": brightness,
        "pattern": pattern,
        "edge_density": edge_density,
        "body_aspect": body_aspect,
        "subject_fill": subject_fill,
        "scene": scene,
    }


# --------------------------------------------------------------------------- #
# the catalogue
# --------------------------------------------------------------------------- #
REFERENCE_SPECIES: list[dict[str, Any]] = [
    # ------------------------------------------------------------- mammals
    {
        "common_name": "Indian Gaur",
        "scientific_name": "Bos gaurus",
        "category": "MAMMAL",
        "family": "Bovidae",
        "genus": "Bos",
        "conservation_status": "VU",
        "is_location_sensitive": False,
        "habitat": "Moist deciduous and semi-evergreen forest with grassy clearings.",
        "description": (
            "The largest extant bovid. Dark coffee-brown to near-black coat with "
            "characteristic white stockings and a high dorsal ridge."
        ),
        "visual_traits": _visual([0.06, 0.03], 0.34, 0.24, "uniform", 0.24, 1.85, 0.42,
                                 "understory"),
        "acoustic_signature": _acoustic(240.0, 180.0, 0.35, 0.45, 1.6, "bellow"),
        "research_notes": {"activity": "crepuscular", "herd_species": True},
    },
    {
        "common_name": "Bengal Tiger",
        "scientific_name": "Panthera tigris tigris",
        "category": "MAMMAL",
        "family": "Felidae",
        "genus": "Panthera",
        "conservation_status": "EN",
        "is_location_sensitive": True,
        "habitat": "Deciduous and evergreen forest with dense cover and water access.",
        "description": (
            "Large striped felid. Precise localities are withheld from "
            "unprivileged viewers because of poaching pressure."
        ),
        "visual_traits": _visual([0.08, 0.05], 0.66, 0.46, "striped", 0.52, 2.10, 0.38,
                                 "understory"),
        "acoustic_signature": _acoustic(200.0, 160.0, 0.30, 0.52, 2.4, "roar"),
        "research_notes": {"activity": "nocturnal", "territorial": True},
    },
    {
        "common_name": "Indian Leopard",
        "scientific_name": "Panthera pardus fusca",
        "category": "MAMMAL",
        "family": "Felidae",
        "genus": "Panthera",
        "conservation_status": "VU",
        "is_location_sensitive": True,
        "habitat": "Highly adaptable — forest, scrub and plantation edges.",
        "description": "Rosetted felid, frequently recorded on camera traps at night.",
        "visual_traits": _visual([0.10, 0.07], 0.58, 0.55, "spotted", 0.58, 1.95, 0.34,
                                 "understory"),
        "acoustic_signature": _acoustic(320.0, 240.0, 0.55, 0.30, 1.8, "sawing rasp"),
        "research_notes": {"activity": "nocturnal"},
    },
    {
        "common_name": "Asian Elephant",
        "scientific_name": "Elephas maximus",
        "category": "MAMMAL",
        "family": "Elephantidae",
        "genus": "Elephas",
        "conservation_status": "EN",
        "is_location_sensitive": True,
        "habitat": "Mosaic of forest and grassland along traditional migratory routes.",
        "description": (
            "Recorded acoustically by trumpets; the low-frequency rumbles that "
            "dominate its repertoire fall below this pipeline's 60 Hz analysis floor."
        ),
        "visual_traits": _visual([0.08, 0.00], 0.12, 0.38, "uniform", 0.30, 1.55, 0.55,
                                 "understory"),
        "acoustic_signature": _acoustic(340.0, 300.0, 0.40, 0.58, 2.0, "trumpet"),
        "research_notes": {"activity": "diurnal-crepuscular", "conflict_species": True},
    },
    {
        "common_name": "Dhole",
        "scientific_name": "Cuon alpinus",
        "category": "MAMMAL",
        "family": "Canidae",
        "genus": "Cuon",
        "conservation_status": "EN",
        "is_location_sensitive": True,
        "habitat": "Open deciduous forest; pack-hunting over large ranges.",
        "description": "Asiatic wild dog; rusty-red coat and a distinctive whistling contact call.",
        "visual_traits": _visual([0.04, 0.06], 0.62, 0.48, "uniform", 0.34, 1.75, 0.28,
                                 "grassland"),
        "acoustic_signature": _acoustic(1300.0, 420.0, 0.70, 0.88, 0.8, "whistle"),
        "research_notes": {"activity": "diurnal", "pack_species": True},
    },
    {
        "common_name": "Lion-tailed Macaque",
        "scientific_name": "Macaca silenus",
        "category": "MAMMAL",
        "family": "Cercopithecidae",
        "genus": "Macaca",
        "conservation_status": "EN",
        "is_location_sensitive": True,
        "habitat": "Western Ghats evergreen rainforest canopy; a Cullenia specialist.",
        "description": "Endemic canopy primate with a silver-grey mane and a tufted tail.",
        "visual_traits": _visual([0.00, 0.02], 0.16, 0.22, "mottled", 0.46, 0.95, 0.24,
                                 "canopy"),
        "acoustic_signature": _acoustic(820.0, 520.0, 1.50, 0.44, 1.2, "whoop"),
        "research_notes": {"activity": "diurnal", "canopy_dependent": True},
    },
    {
        "common_name": "Nilgiri Tahr",
        "scientific_name": "Nilgiritragus hylocrius",
        "category": "MAMMAL",
        "family": "Bovidae",
        "genus": "Nilgiritragus",
        "conservation_status": "EN",
        "is_location_sensitive": True,
        "habitat": "Montane grassland and cliff faces above 1,200 m.",
        "description": "Endemic mountain ungulate; adult males show a pale saddle.",
        "visual_traits": _visual([0.07, 0.02], 0.30, 0.36, "uniform", 0.32, 1.45, 0.26,
                                 "rock"),
        "acoustic_signature": _acoustic(1500.0, 500.0, 0.60, 0.62, 0.6, "alarm whistle"),
        "research_notes": {"activity": "diurnal", "elevation_min_m": 1200},
    },
    {
        "common_name": "Malabar Giant Squirrel",
        "scientific_name": "Ratufa indica",
        "category": "MAMMAL",
        "family": "Sciuridae",
        "genus": "Ratufa",
        "conservation_status": "LC",
        "is_location_sensitive": False,
        "habitat": "Upper canopy of evergreen and moist deciduous forest.",
        "description": "Large arboreal squirrel, maroon and cream, with a very long tail.",
        "visual_traits": _visual([0.02, 0.10], 0.64, 0.42, "mottled", 0.52, 2.30, 0.18,
                                 "canopy"),
        "acoustic_signature": _acoustic(2400.0, 900.0, 4.50, 0.32, 0.9, "rattle"),
        "research_notes": {"activity": "diurnal", "canopy_dependent": True},
    },
    {
        "common_name": "Sambar",
        "scientific_name": "Rusa unicolor",
        "category": "MAMMAL",
        "family": "Cervidae",
        "genus": "Rusa",
        "conservation_status": "VU",
        "is_location_sensitive": False,
        "habitat": "Dense forest near water; the principal prey of tiger and leopard.",
        "description": "Large dark-brown deer; its alarm call is a reliable predator cue.",
        "visual_traits": _visual([0.06, 0.04], 0.40, 0.30, "uniform", 0.30, 1.60, 0.34,
                                 "understory"),
        "acoustic_signature": _acoustic(700.0, 380.0, 0.35, 0.50, 1.1, "alarm bark"),
        "research_notes": {"activity": "crepuscular", "alarm_call_indicator": True},
    },
    {
        "common_name": "Chital",
        "scientific_name": "Axis axis",
        "category": "MAMMAL",
        "family": "Cervidae",
        "genus": "Axis",
        "conservation_status": "LC",
        "is_location_sensitive": False,
        "habitat": "Forest edge and grassland; often in large herds.",
        "description": "Spotted deer; rufous coat with permanent white spotting.",
        "visual_traits": _visual([0.05, 0.08], 0.58, 0.54, "spotted", 0.50, 1.70, 0.32,
                                 "grassland"),
        "acoustic_signature": _acoustic(1000.0, 450.0, 0.80, 0.58, 0.7, "alarm bark"),
        "research_notes": {"activity": "diurnal", "herd_species": True},
    },
    {
        "common_name": "Sloth Bear",
        "scientific_name": "Melursus ursinus",
        "category": "MAMMAL",
        "family": "Ursidae",
        "genus": "Melursus",
        "conservation_status": "VU",
        "is_location_sensitive": False,
        "habitat": "Dry and moist deciduous forest with termite mounds and rock shelters.",
        "description": "Shaggy black bear with a pale chest mark; loud snuffling forage noise.",
        "visual_traits": _visual([0.00, 0.03], 0.14, 0.16, "mottled", 0.56, 1.50, 0.36,
                                 "understory"),
        "acoustic_signature": _acoustic(520.0, 600.0, 2.60, 0.18, 1.4, "huff"),
        "research_notes": {"activity": "nocturnal", "conflict_species": True},
    },
    # ---------------------------------------------------------------- birds
    {
        "common_name": "Indian Peafowl",
        "scientific_name": "Pavo cristatus",
        "category": "BIRD",
        "family": "Phasianidae",
        "genus": "Pavo",
        "conservation_status": "LC",
        "is_location_sensitive": False,
        "habitat": "Forest edge, scrub and cultivation margins.",
        "description": "Unmistakable iridescent blue neck; far-carrying 'may-awe' call.",
        "visual_traits": _visual([0.52, 0.30], 0.72, 0.44, "feathered", 0.62, 1.30, 0.30,
                                 "understory"),
        "acoustic_signature": _acoustic(900.0, 520.0, 0.70, 0.52, 1.0, "screech"),
        "research_notes": {"activity": "diurnal", "call_peaks": "pre-monsoon"},
    },
    {
        "common_name": "Malabar Whistling Thrush",
        "scientific_name": "Myophonus horsfieldii",
        "category": "BIRD",
        "family": "Muscicapidae",
        "genus": "Myophonus",
        "conservation_status": "LC",
        "is_location_sensitive": False,
        "habitat": "Rocky forest streams in the Western Ghats.",
        "description": (
            "Endemic. Dark blue plumage; its rambling dawn whistle is the classic "
            "acoustic signature of a Ghats stream."
        ),
        "visual_traits": _visual([0.60, 0.66], 0.52, 0.22, "uniform", 0.40, 1.55, 0.16,
                                 "wetland"),
        "acoustic_signature": _acoustic(2200.0, 700.0, 0.60, 0.90, 2.6, "whistle"),
        "research_notes": {"activity": "dawn-dusk", "stream_associated": True},
    },
    {
        "common_name": "Great Hornbill",
        "scientific_name": "Buceros bicornis",
        "category": "BIRD",
        "family": "Bucerotidae",
        "genus": "Buceros",
        "conservation_status": "VU",
        "is_location_sensitive": False,
        "habitat": "Tall evergreen forest with large fruiting trees and nest cavities.",
        "description": "Very large hornbill; loud duetted barks and audible wingbeats.",
        "visual_traits": _visual([0.12, 0.00], 0.56, 0.40, "feathered", 0.54, 2.05, 0.28,
                                 "canopy"),
        "acoustic_signature": _acoustic(450.0, 300.0, 1.20, 0.40, 1.5, "bark"),
        "research_notes": {"activity": "diurnal", "seed_disperser": True},
    },
    {
        "common_name": "Malabar Grey Hornbill",
        "scientific_name": "Ocyceros griseus",
        "category": "BIRD",
        "family": "Bucerotidae",
        "genus": "Ocyceros",
        "conservation_status": "LC",
        "is_location_sensitive": False,
        "habitat": "Western Ghats evergreen and moist deciduous forest.",
        "description": "Endemic grey hornbill with a raucous cackling call.",
        "visual_traits": _visual([0.09, 0.02], 0.22, 0.44, "feathered", 0.50, 1.90, 0.22,
                                 "canopy"),
        "acoustic_signature": _acoustic(1800.0, 800.0, 5.00, 0.34, 1.2, "cackle"),
        "research_notes": {"activity": "diurnal", "seed_disperser": True},
    },
    {
        "common_name": "Indian Pitta",
        "scientific_name": "Pitta brachyura",
        "category": "BIRD",
        "family": "Pittidae",
        "genus": "Pitta",
        "conservation_status": "LC",
        "is_location_sensitive": False,
        "habitat": "Undergrowth of moist forest; a breeding-season migrant to the Ghats.",
        "description": "Brilliantly multicoloured ground bird; two-note 'wheet-tieu' whistle.",
        "visual_traits": _visual([0.16, 0.55], 0.78, 0.56, "feathered", 0.58, 1.20, 0.14,
                                 "understory"),
        "acoustic_signature": _acoustic(2600.0, 500.0, 0.50, 0.88, 0.5, "whistle"),
        "research_notes": {"activity": "dawn-dusk", "migratory": True},
    },
    {
        "common_name": "Asian Koel",
        "scientific_name": "Eudynamys scolopaceus",
        "category": "BIRD",
        "family": "Cuculidae",
        "genus": "Eudynamys",
        "conservation_status": "LC",
        "is_location_sensitive": False,
        "habitat": "Wooded gardens, plantations and forest edge.",
        "description": "Brood-parasitic cuckoo; the ascending 'ko-el' is highly distinctive.",
        "visual_traits": _visual([0.00, 0.04], 0.18, 0.18, "uniform", 0.38, 1.60, 0.16,
                                 "canopy"),
        "acoustic_signature": _acoustic(1400.0, 420.0, 1.00, 0.86, 1.0, "whistle"),
        "research_notes": {"activity": "diurnal", "brood_parasite": True},
    },
    {
        "common_name": "Crimson-backed Sunbird",
        "scientific_name": "Leptocoma minima",
        "category": "BIRD",
        "family": "Nectariniidae",
        "genus": "Leptocoma",
        "conservation_status": "LC",
        "is_location_sensitive": False,
        "habitat": "Flowering trees in Western Ghats forest and plantations.",
        "description": "India's smallest sunbird; endemic, with rapid high-pitched chirps.",
        "visual_traits": _visual([0.98, 0.35], 0.80, 0.50, "feathered", 0.62, 1.45, 0.08,
                                 "canopy"),
        "acoustic_signature": _acoustic(5200.0, 1200.0, 6.00, 0.70, 0.4, "chirp"),
        "research_notes": {"activity": "diurnal", "pollinator": True},
    },
    {
        "common_name": "Nilgiri Flycatcher",
        "scientific_name": "Eumyias albicaudatus",
        "category": "BIRD",
        "family": "Muscicapidae",
        "genus": "Eumyias",
        "conservation_status": "NT",
        "is_location_sensitive": False,
        "habitat": "Sholas and high-elevation forest edge of the Nilgiris and Palanis.",
        "description": "Endemic indigo-blue flycatcher of montane shola forest.",
        "visual_traits": _visual([0.62, 0.58], 0.66, 0.34, "uniform", 0.42, 1.35, 0.10,
                                 "canopy"),
        "acoustic_signature": _acoustic(4200.0, 900.0, 3.00, 0.76, 0.6, "trill"),
        "research_notes": {"activity": "diurnal", "elevation_min_m": 1000},
    },
    {
        "common_name": "Grey Junglefowl",
        "scientific_name": "Gallus sonneratii",
        "category": "BIRD",
        "family": "Phasianidae",
        "genus": "Gallus",
        "conservation_status": "LC",
        "is_location_sensitive": False,
        "habitat": "Forest floor and bamboo thickets of peninsular India.",
        "description": "Endemic junglefowl; the male's crow is broken into four syllables.",
        "visual_traits": _visual([0.08, 0.00], 0.34, 0.38, "barred", 0.60, 1.40, 0.20,
                                 "understory"),
        "acoustic_signature": _acoustic(1100.0, 600.0, 2.00, 0.56, 1.3, "crow"),
        "research_notes": {"activity": "diurnal", "ground_dwelling": True},
    },
    # --------------------------------------------------------------- plants
    {
        "common_name": "Teak",
        "scientific_name": "Tectona grandis",
        "category": "PLANT",
        "family": "Lamiaceae",
        "genus": "Tectona",
        "conservation_status": "LC",
        "is_location_sensitive": False,
        "habitat": "Moist and dry deciduous forest; extensively planted.",
        "description": "Very large simple opposite leaves with a rough, sandpapery surface.",
        "visual_traits": _visual([0.26, 0.22], 0.44, 0.42, "leafy", 0.46, 0.75, 0.62,
                                 "canopy"),
        "acoustic_signature": {},
        "research_notes": {"phenology": "deciduous, leafless Feb-Apr", "timber": True},
    },
    {
        "common_name": "Indian Sandalwood",
        "scientific_name": "Santalum album",
        "category": "PLANT",
        "family": "Santalaceae",
        "genus": "Santalum",
        "conservation_status": "VU",
        "is_location_sensitive": True,
        "habitat": "Dry deciduous forest and scrub; a root hemiparasite.",
        "description": (
            "Small tree with drooping, thin, opposite leaves. Localities are "
            "generalised because standing trees are targeted by illegal felling."
        ),
        "visual_traits": _visual([0.29, 0.24], 0.38, 0.46, "leafy", 0.42, 0.85, 0.54,
                                 "understory"),
        "acoustic_signature": {},
        "research_notes": {
            "medicinal_relevance": "documented in Ayurvedic materia medica; "
            "records here are observations, not clinical claims",
            "hemiparasite": True,
        },
    },
    {
        "common_name": "Indian Rosewood",
        "scientific_name": "Dalbergia latifolia",
        "category": "PLANT",
        "family": "Fabaceae",
        "genus": "Dalbergia",
        "conservation_status": "VU",
        "is_location_sensitive": True,
        "habitat": "Moist and dry deciduous forest.",
        "description": "Pinnate leaves with broadly ovate leaflets; high-value timber.",
        "visual_traits": _visual([0.27, 0.31], 0.48, 0.44, "leafy", 0.56, 1.10, 0.58,
                                 "canopy"),
        "acoustic_signature": {},
        "research_notes": {"timber": True, "cites_listed": True},
    },
    {
        "common_name": "Wild Durian",
        "scientific_name": "Cullenia exarillata",
        "category": "PLANT",
        "family": "Malvaceae",
        "genus": "Cullenia",
        "conservation_status": "NT",
        "is_location_sensitive": False,
        "habitat": "Mid-elevation Western Ghats evergreen rainforest; a keystone tree.",
        "description": (
            "Endemic canopy tree whose fruiting drives lion-tailed macaque ranging."
        ),
        "visual_traits": _visual([0.24, 0.20], 0.40, 0.34, "leafy", 0.50, 0.70, 0.66,
                                 "canopy"),
        "acoustic_signature": {},
        "research_notes": {"keystone_species": True, "fruiting": "Jan-Apr"},
    },
    {
        "common_name": "Giant Thorny Bamboo",
        "scientific_name": "Bambusa bambos",
        "category": "PLANT",
        "family": "Poaceae",
        "genus": "Bambusa",
        "conservation_status": "LC",
        "is_location_sensitive": False,
        "habitat": "Riparian strips and moist deciduous forest.",
        "description": "Dense clumping bamboo; gregarious flowering at long intervals.",
        "visual_traits": _visual([0.22, 0.18], 0.52, 0.52, "striped", 0.72, 0.45, 0.70,
                                 "understory"),
        "acoustic_signature": {},
        "research_notes": {"gregarious_flowering": True, "elephant_forage": True},
    },
    {
        "common_name": "Neelakurinji",
        "scientific_name": "Strobilanthes kunthiana",
        "category": "PLANT",
        "family": "Acanthaceae",
        "genus": "Strobilanthes",
        "conservation_status": "NE",
        "is_location_sensitive": False,
        "habitat": "Montane grassland of the Western Ghats above 1,300 m.",
        "description": "Mass-flowers at roughly twelve-year intervals, turning slopes violet.",
        "visual_traits": _visual([0.74, 0.70], 0.68, 0.56, "leafy", 0.56, 1.00, 0.72,
                                 "grassland"),
        "acoustic_signature": {},
        "research_notes": {"mass_flowering_years": 12, "elevation_min_m": 1300},
    },
    # ------------------------------------------------- reptiles & amphibians
    {
        "common_name": "King Cobra",
        "scientific_name": "Ophiophagus hannah",
        "category": "REPTILE",
        "family": "Elapidae",
        "genus": "Ophiophagus",
        "conservation_status": "VU",
        "is_location_sensitive": True,
        "habitat": "Dense evergreen forest and bamboo; nests on the forest floor.",
        "description": "World's longest venomous snake; nest localities are withheld.",
        "visual_traits": _visual([0.09, 0.11], 0.42, 0.34, "barred", 0.48, 2.80, 0.22,
                                 "understory"),
        "acoustic_signature": _acoustic(600.0, 900.0, 0.0, 0.12, 1.8, "hiss"),
        "research_notes": {"activity": "diurnal", "nest_builder": True},
    },
    {
        "common_name": "Malabar Pit Viper",
        "scientific_name": "Trimeresurus malabaricus",
        "category": "REPTILE",
        "family": "Viperidae",
        "genus": "Trimeresurus",
        "conservation_status": "LC",
        "is_location_sensitive": False,
        "habitat": "Western Ghats evergreen forest, usually near streams.",
        "description": "Endemic, highly polymorphic pit viper — green, brown and yellow morphs.",
        "visual_traits": _visual([0.30, 0.15], 0.60, 0.40, "mottled", 0.64, 2.40, 0.16,
                                 "understory"),
        "acoustic_signature": {},
        "research_notes": {"activity": "nocturnal", "polymorphic": True},
    },
    {
        "common_name": "Purple Frog",
        "scientific_name": "Nasikabatrachus sahyadrensis",
        "category": "AMPHIBIAN",
        "family": "Nasikabatrachidae",
        "genus": "Nasikabatrachus",
        "conservation_status": "EN",
        "is_location_sensitive": True,
        "habitat": "Fossorial in Western Ghats forest soil; surfaces to breed in the monsoon.",
        "description": (
            "Endemic burrowing frog of an ancient lineage. Detectable almost only "
            "by its underground call during the first monsoon rains."
        ),
        "visual_traits": _visual([0.78, 0.82], 0.36, 0.28, "uniform", 0.24, 1.40, 0.20,
                                 "understory"),
        "acoustic_signature": _acoustic(1200.0, 700.0, 12.00, 0.34, 3.0, "cluck",
                                        pulse_tolerance=4.0),
        "research_notes": {"activity": "monsoon-nocturnal", "fossorial": True},
    },
    {
        "common_name": "Malabar Gliding Frog",
        "scientific_name": "Rhacophorus malabaricus",
        "category": "AMPHIBIAN",
        "family": "Rhacophoridae",
        "genus": "Rhacophorus",
        "conservation_status": "LC",
        "is_location_sensitive": False,
        "habitat": "Canopy and mid-storey near forest pools; builds foam nests.",
        "description": "Endemic green tree frog with extensive webbing used for gliding.",
        "visual_traits": _visual([0.31, 0.27], 0.74, 0.58, "uniform", 0.36, 1.30, 0.18,
                                 "canopy"),
        "acoustic_signature": _acoustic(2000.0, 800.0, 8.00, 0.48, 1.5, "rattle",
                                        pulse_tolerance=3.0),
        "research_notes": {"activity": "monsoon-nocturnal", "foam_nest": True},
    },
    # -------------------------------------------------------------- insects
    {
        "common_name": "Southern Birdwing",
        "scientific_name": "Troides minos",
        "category": "INSECT",
        "family": "Papilionidae",
        "genus": "Troides",
        "conservation_status": "NE",
        "is_location_sensitive": False,
        "habitat": "Western Ghats forest and adjoining gardens with Aristolochia vines.",
        "description": "India's largest butterfly; endemic, with black and golden-yellow wings.",
        "visual_traits": _visual([0.14, 0.00], 0.76, 0.48, "striped", 0.66, 1.25, 0.20,
                                 "understory"),
        "acoustic_signature": {},
        "research_notes": {"activity": "diurnal", "host_plant": "Aristolochia spp."},
    },
    {
        "common_name": "Malabar Tree Nymph",
        "scientific_name": "Idea malabarica",
        "category": "INSECT",
        "family": "Nymphalidae",
        "genus": "Idea",
        "conservation_status": "NE",
        "is_location_sensitive": False,
        "habitat": "Shaded evergreen forest; a slow, drifting flier.",
        "description": "Endemic large white butterfly with black veins and spots.",
        "visual_traits": _visual([0.00, 0.16], 0.10, 0.82, "spotted", 0.58, 1.15, 0.22,
                                 "understory"),
        "acoustic_signature": {},
        "research_notes": {"activity": "diurnal", "indicator_species": True},
    },
]


def species_references(
    catalogue: list[dict[str, Any]] | None = None,
    *,
    id_offset: int = 1,
) -> list[SpeciesReference]:
    """Convert catalogue rows into AI :class:`SpeciesReference` objects.

    ``id_offset`` mirrors the database's 1-based primary keys when the catalogue
    has been seeded in order, so a reference built from this module lines up with
    the ``species`` table without an extra query.
    """
    rows = catalogue if catalogue is not None else REFERENCE_SPECIES
    return [
        SpeciesReference(
            species_id=index + id_offset,
            label=row["common_name"],
            scientific_name=row["scientific_name"],
            category=row["category"],
            visual_traits=row.get("visual_traits") or {},
            acoustic_signature=row.get("acoustic_signature") or {},
        )
        for index, row in enumerate(rows)
    ]


AUDIBLE_SPECIES = [row for row in REFERENCE_SPECIES if row.get("acoustic_signature")]
PLANT_SPECIES = [row for row in REFERENCE_SPECIES if row["category"] == "PLANT"]
THREATENED_SPECIES = [
    row for row in REFERENCE_SPECIES if row["conservation_status"] in {"CR", "EN", "VU"}
]
