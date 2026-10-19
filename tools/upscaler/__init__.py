"""Pacote independente de upscaling e redraw de cartas para posters em 300 DPI (tools/upscaler)."""

from __future__ import annotations

from tools.upscaler.api import upscale_card_to_poster
from tools.upscaler.orchestrator import run_upscale_orchestration
from tools.upscaler.prompt_builder import (
    POSTER_FORMATS,
    PosterFormatSpec,
    UpscalePromptBuilder,
    normalize_target_format,
)
from tools.upscaler.validator import PosterImageValidator, PosterValidationResult

__all__ = [
    "POSTER_FORMATS",
    "PosterFormatSpec",
    "PosterImageValidator",
    "PosterValidationResult",
    "UpscalePromptBuilder",
    "normalize_target_format",
    "run_upscale_orchestration",
    "upscale_card_to_poster",
]
