"""Pacote independente de expansão generativa de fundo / outpainting em 300 DPI (tools/background_expander)."""

from __future__ import annotations

from tools.background_expander.api import expand_background
from tools.background_expander.orchestrator import run_background_expansion_orchestration
from tools.background_expander.prompt_builder import (
    DEFAULT_BLEED_MM,
    DEFAULT_DPI,
    EXPANSION_MODES,
    BackgroundExpansionPromptBuilder,
    ExpansionModeSpec,
    calculate_bleed_pixels,
    calculate_expanded_dimensions,
    normalize_expansion_mode,
)
from tools.background_expander.validator import (
    ExpandedImageValidator,
    ExpansionValidationResult,
)

__all__ = [
    "BackgroundExpansionPromptBuilder",
    "DEFAULT_BLEED_MM",
    "DEFAULT_DPI",
    "EXPANSION_MODES",
    "ExpandedImageValidator",
    "ExpansionModeSpec",
    "ExpansionValidationResult",
    "calculate_bleed_pixels",
    "calculate_expanded_dimensions",
    "expand_background",
    "normalize_expansion_mode",
    "run_background_expansion_orchestration",
]
