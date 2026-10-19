"""Pacote validator responsável pela inspeção e validação de imagens de cartas."""

from validator.card_validator import CardImageValidator, ValidationResult

__all__ = [
    "CardImageValidator",
    "ValidationResult",
]
