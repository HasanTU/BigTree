"""Analysis module public API providing team-specification compatible facades."""

from __future__ import annotations

from bigtree.domain.statistics import (
    compare_green_space_cohorts,
    compute_bivariate_correlation,
)
from bigtree.use_cases.analyze_research_questions import AnalyzeResearchQuestionsUseCase

__all__ = [
    "AnalyzeResearchQuestionsUseCase",
    "compare_green_space_cohorts",
    "compute_bivariate_correlation",
]
