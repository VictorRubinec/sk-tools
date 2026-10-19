"""Pacote encapsulado da ferramenta de geração e validação de cartas (card_generator)."""

from __future__ import annotations

from tools.card_generator.api import (
    check_gemini_session,
    generate_batch_cards,
    generate_single_card,
)
from tools.card_generator.core.config import AppConfig, DEFAULT_CONFIG
from tools.card_generator.core.runner import CardGenerationRunner
from tools.card_generator.core.schema import CardInput, load_cards_from_file
from tools.card_generator.validator.card_validator import ValidationResult

__all__ = [
    "AppConfig",
    "CardGenerationRunner",
    "CardInput",
    "DEFAULT_CONFIG",
    "ValidationResult",
    "check_gemini_session",
    "generate_batch_cards",
    "generate_single_card",
    "load_cards_from_file",
]
