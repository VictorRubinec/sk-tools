"""Pacote core contendo schemas de dados, configurações globais e motor de execução."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tools.card_generator.core.config import (
    AppConfig,
    BASE_DIR,
    DEFAULT_CONFIG,
    INPUT_DIR,
    OUTPUT_DIR,
    PACKAGE_DIR,
)
from tools.card_generator.core.schema import (
    CardInput,
    STANDARD_CARD_STYLES,
    STANDARD_CARD_TYPES,
    load_cards_from_file,
)

if TYPE_CHECKING:
    from tools.card_generator.core.runner import CardGenerationRunner

__all__ = [
    "AppConfig",
    "BASE_DIR",
    "CardGenerationRunner",
    "CardInput",
    "DEFAULT_CONFIG",
    "INPUT_DIR",
    "OUTPUT_DIR",
    "PACKAGE_DIR",
    "STANDARD_CARD_STYLES",
    "STANDARD_CARD_TYPES",
    "load_cards_from_file",
]


def __getattr__(name: str) -> Any:
    """Importa CardGenerationRunner sob demanda para evitar ciclos entre core e browser."""
    if name == "CardGenerationRunner":
        from tools.card_generator.core.runner import CardGenerationRunner

        return CardGenerationRunner
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
