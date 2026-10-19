"""Validador de integridade, dimensões, proporção e qualidade visual de imagens de cartas."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

from PIL import Image, ImageStat, UnidentifiedImageError

from core.schema import CardInput


@dataclass
class ValidationResult:
    """Resultado detalhado da validação de uma imagem de carta gerada."""

    is_valid: bool
    width: int
    height: int
    aspect_ratio: float
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class CardImageValidator:
    """Inspeciona imagens geradas para assegurar conformidade técnica e visual com TCGs."""

    MIN_WIDTH: int = 512
    MIN_HEIGHT: int = 700
    MIN_ASPECT_RATIO: float = 1.25
    MAX_ASPECT_RATIO: float = 1.65
    MIN_STD_DEV_THRESHOLD: float = 5.0

    def __init__(
        self,
        min_width: int = MIN_WIDTH,
        min_height: int = MIN_HEIGHT,
        min_aspect_ratio: float = MIN_ASPECT_RATIO,
        max_aspect_ratio: float = MAX_ASPECT_RATIO,
        min_std_dev_threshold: float = MIN_STD_DEV_THRESHOLD,
    ) -> None:
        self.min_width = min_width
        self.min_height = min_height
        self.min_aspect_ratio = min_aspect_ratio
        self.max_aspect_ratio = max_aspect_ratio
        self.min_std_dev_threshold = min_std_dev_threshold

    def validate_image(
        self,
        image_path_or_bytes: Union[str, Path, bytes],
        card: Optional[CardInput] = None,
    ) -> ValidationResult:
        """Executa a bateria de validações técnicas na imagem fornecida.

        Etapas:
            1. Integridade do arquivo/bytes via Pillow (`Image.open` + `verify`).
            2. Dimensões mínimas (`width >= 512`, `height >= 700`).
            3. Orientação estritamente vertical (`height > width`) e aspect ratio entre 1.25 e 1.65.
            4. Verificação contra imagens monocromáticas/vazias (desvio padrão dos canais RGB).

        Args:
            image_path_or_bytes: Caminho do arquivo de imagem ou bytes brutos.
            card: Instância opcional de `CardInput` para contexto adicional.

        Returns:
            Instância de `ValidationResult` com o diagnóstico completo.
        """
        errors: List[str] = []
        warnings: List[str] = []

        raw_bytes = self._load_raw_bytes(image_path_or_bytes, errors)
        if raw_bytes is None:
            return ValidationResult(
                is_valid=False,
                width=0,
                height=0,
                aspect_ratio=0.0,
                errors=errors,
                warnings=warnings,
            )

        # 1. Verificação de integridade estrutural via Pillow verify()
        try:
            with Image.open(io.BytesIO(raw_bytes)) as verify_img:
                verify_img.verify()
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
            errors.append(f"Imagem corrompida ou formato inválido: {exc}")
            return ValidationResult(
                is_valid=False,
                width=0,
                height=0,
                aspect_ratio=0.0,
                errors=errors,
                warnings=warnings,
            )

        # Reabre a imagem para leitura de dimensões e estatísticas de pixels
        try:
            with Image.open(io.BytesIO(raw_bytes)) as img:
                rgb_img = img.convert("RGB")
                width, height = rgb_img.size
                stat = ImageStat.Stat(rgb_img)
        except Exception as exc:
            errors.append(f"Falha ao decodificar pixels da imagem: {exc}")
            return ValidationResult(
                is_valid=False,
                width=0,
                height=0,
                aspect_ratio=0.0,
                errors=errors,
                warnings=warnings,
            )

        if width <= 0 or height <= 0:
            errors.append(f"Dimensões inválidas detectadas: {width}x{height}px.")
            return ValidationResult(
                is_valid=False,
                width=width,
                height=height,
                aspect_ratio=0.0,
                errors=errors,
                warnings=warnings,
            )

        aspect_ratio = round(height / width, 4)

        # 2. Verificação de dimensões mínimas
        if width < self.min_width or height < self.min_height:
            errors.append(
                f"Dimensões insuficientes ({width}x{height}px). "
                f"Mínimo exigido: {self.min_width}x{self.min_height}px."
            )

        # 3. Verificação de orientação vertical e proporção de TCG (1.25 a 1.65)
        if height <= width:
            errors.append(
                f"Orientação inválida ({width}x{height}px). "
                "A carta deve ter orientação estritamente vertical (altura > largura)."
            )
        elif not (self.min_aspect_ratio <= aspect_ratio <= self.max_aspect_ratio):
            errors.append(
                f"Proporção (aspect ratio altura/largura = {aspect_ratio:.2f}) fora do intervalo "
                f"esperado para TCG ({self.min_aspect_ratio:.2f} a {self.max_aspect_ratio:.2f})."
            )

        # 4. Verificação de variância cromática (rejeita imagens monocromáticas/em branco/preto)
        mean_std_dev = sum(stat.stddev) / len(stat.stddev) if stat.stddev else 0.0
        if mean_std_dev < self.min_std_dev_threshold:
            errors.append(
                f"Imagem monocromática ou vazia detectada (desvio padrão médio RGB: {mean_std_dev:.2f} "
                f"< limiar mínimo de {self.min_std_dev_threshold:.2f})."
            )

        if card is not None and card.estilo == "Fullart" and width < 600:
            warnings.append(
                "Para cartas no estilo 'Fullart', recomenda-se resolução horizontal superior a 600px."
            )

        return ValidationResult(
            is_valid=len(errors) == 0,
            width=width,
            height=height,
            aspect_ratio=aspect_ratio,
            errors=errors,
            warnings=warnings,
        )

    @staticmethod
    def _load_raw_bytes(
        source: Union[str, Path, bytes], errors: List[str]
    ) -> Optional[bytes]:
        """Extrai os bytes brutos a partir de um caminho de arquivo ou buffer em memória."""
        if isinstance(source, bytes):
            if not source:
                errors.append("O conteúdo em bytes da imagem está vazio.")
                return None
            return source

        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.is_file():
                errors.append(f"Arquivo de imagem não encontrado: {path}")
                return None
            data = path.read_bytes()
            if not data:
                errors.append(f"Arquivo de imagem está vazio (0 bytes): {path}")
                return None
            return data

        errors.append(
            f"Tipo de entrada não suportado para validação de imagem: {type(source).__name__}"
        )
        return None
