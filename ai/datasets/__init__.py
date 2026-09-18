"""Reference species catalogue and the reproducible evaluation dataset."""

from ai.datasets.reference_species import (
    REFERENCE_SPECIES,
    band_profile_for,
    species_references,
)
from ai.datasets.synthetic import (
    SyntheticSample,
    generate_dataset,
    synthesise_call_wav,
)

__all__ = [
    "REFERENCE_SPECIES",
    "SyntheticSample",
    "band_profile_for",
    "generate_dataset",
    "species_references",
    "synthesise_call_wav",
]
