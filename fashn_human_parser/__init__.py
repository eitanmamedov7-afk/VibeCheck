"""Local FASHN human parser package exports."""

from .labels import (
    BODY_COVERAGE_TO_LABELS,
    CATEGORY_TO_BODY_COVERAGE,
    IDENTITY_LABELS,
    IDS_TO_LABELS,
    LABELS_TO_IDS,
)
from .parser import FashnHumanParser

__version__ = "0.1.1-local"
__all__ = [
    "FashnHumanParser",
    "IDS_TO_LABELS",
    "LABELS_TO_IDS",
    "CATEGORY_TO_BODY_COVERAGE",
    "BODY_COVERAGE_TO_LABELS",
    "IDENTITY_LABELS",
]
