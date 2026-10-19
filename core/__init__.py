"""Pacote core contendo schemas de dados, configurações globais e motor de execução."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.config import AppConfig, BASE_DIR, DEFAULT_CONFIG, INPUT_DIR, OUTPUT_DIR
from core.logger import logger, setup_logger
from core.schema import (
    CardInput,
    STANDARD_CARD_STYLES,
    STANDARD_CARD_TYPES,
    load_cards_from_file,
)

if TYPE_CHECKING:
    from core.runner import CardGenerationRunner

__all__ = [
    "AppConfig",
    "BASE_DIR",
    "CardGenerationRunner",
    "CardInput",
    "DEFAULT_CONFIG",
    "INPUT_DIR",
    "OUTPUT_DIR",
    "STANDARD_CARD_STYLES",
    "STANDARD_CARD_TYPES",
    "load_cards_from_file",
    "logger",
    "setup_logger",
]


def __getattr__(name: str) -> Any:
    """Importa CardGenerationRunner sob demanda para evitar ciclos entre core e browser."""
    if name == "CardGenerationRunner":
        from core.runner import CardGenerationRunner

        return CardGenerationRunner
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
