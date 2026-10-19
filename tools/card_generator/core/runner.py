"""Motor de execução com retentativas automáticas, reforço de prompt e validação de qualidade."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from tools.card_generator.browser.exceptions import (
    GeminiGenerationTimeoutError,
    GeminiImageNotGeneratedError,
    GeminiPromptSubmissionError,
)
from tools.card_generator.browser.orchestrator import generate_card_image
from tools.card_generator.core.config import AppConfig, DEFAULT_CONFIG
from tools.card_generator.core.logger import logger
from tools.card_generator.core.schema import CardInput
from tools.card_generator.validator.card_validator import (
    CardImageValidator,
    ValidationResult,
)


class CardGenerationRunner:
    """Coordena a geração de cartas com validação de imagem e loop de retentativas."""

    def __init__(
        self,
        validator: Optional[CardImageValidator] = None,
        generator_fn: Optional[Callable[..., Path]] = None,
    ) -> None:
        self.validator = validator or CardImageValidator()
        self._generator_fn = generator_fn

    def process_card(
        self,
        card: CardInput,
        config: AppConfig = DEFAULT_CONFIG,
        max_retries: int = 3,
        context: Optional[Any] = None,
    ) -> Tuple[bool, Optional[Path], Optional[ValidationResult]]:
        """Processa uma única carta com até `max_retries` tentativas e validação visual.

        Args:
            card: Instância validada de `CardInput`.
            config: Configurações operacionais (`AppConfig`).
            max_retries: Número máximo de tentativas permitidas (mínimo 1).
            context: Contexto de navegador opcional para reutilização entre cartas.

        Returns:
            Tupla `(sucesso, caminho_da_imagem_aprovada, ultimo_resultado_de_validacao)`.
        """
        if max_retries < 1:
            raise ValueError("O parâmetro 'max_retries' deve ser maior ou igual a 1.")

        last_validation: Optional[ValidationResult] = None
        reinforcement_notes: List[str] = []
        generator = self._generator_fn or generate_card_image

        for attempt in range(1, max_retries + 1):
            attempt_card = self._build_attempt_card(card, attempt, reinforcement_notes)
            logger.info(
                "Processando carta '{}' ({}) - Tentativa {}/{}",
                card.titulo,
                card.tipo,
                attempt,
                max_retries,
            )

            try:
                try:
                    image_path = generator(attempt_card, config=config, context=context)
                except TypeError:
                    image_path = generator(attempt_card, config=config)
            except (
                GeminiImageNotGeneratedError,
                GeminiGenerationTimeoutError,
                GeminiPromptSubmissionError,
            ) as exc:
                logger.warning(
                    "Tentativa {}/{} falhou durante a geração no navegador para '{}': {}",
                    attempt,
                    max_retries,
                    card.titulo,
                    exc,
                )
                reinforcement_notes.append(
                    "Gere obrigatoriamente uma imagem visual completa da carta vertical (proporção 5:7)."
                )
                continue

            validation_result = self.validator.validate_image(image_path, card=card)
            last_validation = validation_result

            if validation_result.is_valid:
                logger.success(
                    "Carta '{}' aprovada na tentativa {}/{} ({}x{}px, ratio={:.2f}).",
                    card.titulo,
                    attempt,
                    max_retries,
                    validation_result.width,
                    validation_result.height,
                    validation_result.aspect_ratio,
                )
                return True, image_path, validation_result

            # Reprovada na validação: apaga o arquivo inválido e prepara reforço no prompt
            logger.warning(
                "Carta '{}' reprovada na tentativa {}/{}. Motivos: {}",
                card.titulo,
                attempt,
                max_retries,
                "; ".join(validation_result.errors),
            )
            self._remove_invalid_image(image_path)
            reinforcement_notes = list(validation_result.errors)

        logger.error(
            "Falha definitiva ao gerar a carta '{}' após {} tentativa(s).",
            card.titulo,
            max_retries,
        )
        return False, None, last_validation

    def process_batch(
        self,
        cards: List[CardInput],
        config: AppConfig = DEFAULT_CONFIG,
        max_retries: int = 3,
        context: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Processa uma lista de cartas sequencialmente e consolida estatísticas do lote.

        Args:
            cards: Lista de objetos `CardInput`.
            config: Configurações operacionais (`AppConfig`).
            max_retries: Número máximo de tentativas por carta.
            context: Contexto de navegador opcional para reutilização no lote.

        Returns:
            Dicionário com estatísticas consolidadas (`total`, `succeeded`, `failed`, `results`).
        """
        total = len(cards)
        succeeded = 0
        failed = 0
        results: List[Dict[str, Any]] = []

        for card in cards:
            ok, output_path, validation = self.process_card(
                card=card, config=config, max_retries=max_retries, context=context
            )
            if ok:
                succeeded += 1
            else:
                failed += 1

            results.append(
                {
                    "titulo": card.titulo,
                    "tipo": card.tipo,
                    "estilo": card.estilo,
                    "success": ok,
                    "output_path": output_path,
                    "validation": validation,
                }
            )

        return {
            "total": total,
            "succeeded": succeeded,
            "failed": failed,
            "results": results,
        }

    @staticmethod
    def _build_attempt_card(
        original_card: CardInput, attempt: int, reinforcement_notes: List[str]
    ) -> CardInput:
        """Retorna uma cópia de `CardInput` com instruções reforçadas para retentativas."""
        if attempt <= 1:
            return original_card

        reasons = (
            " | ".join(reinforcement_notes)
            if reinforcement_notes
            else "Proporção ou resolução inadequada na tentativa anterior."
        )
        reinforcement_suffix = (
            f" [REFORÇO DE QUALIDADE - TENTATIVA {attempt}: Corrija rigorosamente: {reasons}. "
            "A imagem DEVE ter orientação estritamente vertical em proporção 5:7 (ex: 750x1050px), "
            "alta resolução, riqueza de cores e enquadramento completo da carta.]"
        )
        base_desc = original_card.descricao or f"Ilustração temática para {original_card.titulo}."
        return original_card.model_copy(
            update={"descricao": f"{base_desc}{reinforcement_suffix}"}
        )

    @staticmethod
    def _remove_invalid_image(image_path: Optional[Path]) -> None:
        """Remove do disco a imagem reprovada pelo validador."""
        if image_path is None:
            return
        try:
            path_obj = Path(image_path)
            if path_obj.is_file():
                path_obj.unlink()
        except OSError as exc:
            logger.warning(
                "Não foi possível remover a imagem inválida '{}': {}", image_path, exc
            )
