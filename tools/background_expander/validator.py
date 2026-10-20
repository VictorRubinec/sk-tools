"""Validador dimensional e de integridade visual para imagens com fundo expandido (outpainting)."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Union

from PIL import Image, ImageStat, UnidentifiedImageError

from tools.background_expander.prompt_builder import (
    DEFAULT_BLEED_MM,
    DEFAULT_DPI,
    calculate_bleed_pixels,
    calculate_expanded_dimensions,
    normalize_expansion_mode,
)
from tools.upscaler.validator import PosterImageValidator


@dataclass
class ExpansionValidationResult:
    """Resultado detalhado da validação de uma imagem com fundo expandido."""

    is_valid: bool
    mode: str
    width: int
    height: int
    expected_width: int
    expected_height: int
    bleed_px: int
    has_black_borders: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class ExpandedImageValidator:
    """Inspeciona imagens expandidas garantindo sangria 300 DPI e ausência de barras pretas."""

    MIN_STD_DEV_THRESHOLD: float = 5.0
    MIN_SOURCE_DIMENSION: int = 512

    def __init__(self, min_std_dev_threshold: float = MIN_STD_DEV_THRESHOLD) -> None:
        self.min_std_dev_threshold = min_std_dev_threshold

    @staticmethod
    def trim_black_borders(
        img: Image.Image,
        threshold: int = 20,
        max_margin_ratio: float = 0.20,
    ) -> Image.Image:
        """Reutiliza a detecção e corte de barras pretas periféricas do PosterImageValidator."""
        return PosterImageValidator.trim_black_borders(
            img=img, threshold=threshold, max_margin_ratio=max_margin_ratio
        )

    def validate_expanded_image(
        self,
        image_path_or_bytes: Union[str, Path, bytes],
        base_size: Tuple[int, int] = (750, 1050),
        mode: str = "bleed_5mm",
        bleed_mm: float = DEFAULT_BLEED_MM,
        custom_size: Optional[Tuple[int, int]] = None,
    ) -> ExpansionValidationResult:
        """Valida integridade, ausência de barras pretas e dimensões finais com sangria 300 DPI.

        Args:
            image_path_or_bytes: Caminho do arquivo ou bytes brutos da imagem expandida.
            base_size: Dimensões `(largura, altura)` da imagem original antes da expansão.
            mode: Modo de expansão ('bleed_5mm', 'horizontal', 'caneca', 'custom').
            bleed_mm: Milímetros de margem por borda (padrão: 5.0 mm = 59 px a 300 DPI).
            custom_size: Dimensões alvo opcionais para o modo `custom`.

        Returns:
            Instância de `ExpansionValidationResult`.
        """
        spec = normalize_expansion_mode(mode)
        expected_w, expected_h, bleed_px = calculate_expanded_dimensions(
            base_width=base_size[0],
            base_height=base_size[1],
            mode=spec.code,
            bleed_mm=bleed_mm,
            dpi=DEFAULT_DPI,
            custom_size=custom_size,
        )

        errors: List[str] = []
        warnings: List[str] = []

        raw_bytes = self._load_raw_bytes(image_path_or_bytes, errors)
        if raw_bytes is None:
            return ExpansionValidationResult(
                is_valid=False,
                mode=spec.code,
                width=0,
                height=0,
                expected_width=expected_w,
                expected_height=expected_h,
                bleed_px=bleed_px,
                has_black_borders=False,
                errors=errors,
                warnings=warnings,
            )

        # 1. Integridade física via Pillow verify()
        try:
            with Image.open(io.BytesIO(raw_bytes)) as verify_img:
                verify_img.verify()
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
            errors.append(f"Imagem expandida corrompida ou formato inválido: {exc}")
            return ExpansionValidationResult(
                is_valid=False,
                mode=spec.code,
                width=0,
                height=0,
                expected_width=expected_w,
                expected_height=expected_h,
                bleed_px=bleed_px,
                has_black_borders=False,
                errors=errors,
                warnings=warnings,
            )

        try:
            with Image.open(io.BytesIO(raw_bytes)) as img:
                rgb_img = img.convert("RGB")
                width, height = rgb_img.size
                stat = ImageStat.Stat(rgb_img)
                trimmed_img = self.trim_black_borders(rgb_img)
        except Exception as exc:
            errors.append(f"Falha ao decodificar pixels da imagem expandida: {exc}")
            return ExpansionValidationResult(
                is_valid=False,
                mode=spec.code,
                width=0,
                height=0,
                expected_width=expected_w,
                expected_height=expected_h,
                bleed_px=bleed_px,
                has_black_borders=False,
                errors=errors,
                warnings=warnings,
            )

        # 2. Variância cromática (reprova imagem monocromática/preta/branca)
        mean_std_dev = sum(stat.stddev) / len(stat.stddev) if stat.stddev else 0.0
        if mean_std_dev < self.min_std_dev_threshold:
            errors.append(
                f"Imagem expandida monocromática ou vazia detectada (desvio padrão RGB: {mean_std_dev:.2f})."
            )

        # 3. Detecção de barras pretas periféricas (pillarbox/letterbox)
        has_black_borders = trimmed_img.size != rgb_img.size
        if has_black_borders:
            errors.append(
                f"Barras pretas periféricas detectadas nas bordas (dimensão útil reduzida de "
                f"{width}x{height}px para {trimmed_img.width}x{trimmed_img.height}px)."
            )

        # 4. Orientação exigida para modos panorâmicos
        if spec.requires_horizontal_orientation and width <= height:
            errors.append(
                f"Orientação incompatível com o modo '{spec.code}': esperado horizontal "
                f"(largura > altura), obtido {width}x{height}px."
            )

        # 5. Verificação das dimensões exigidas (incluindo sangria de 5mm por borda a 300 DPI)
        if width < expected_w or height < expected_h:
            errors.append(
                f"Dimensões insuficientes para expansão '{spec.code}' com sangria de {bleed_mm:.1f}mm "
                f"({bleed_px}px/borda): obtido {width}x{height}px, exigido mínimo {expected_w}x{expected_h}px."
            )

        return ExpansionValidationResult(
            is_valid=len(errors) == 0,
            mode=spec.code,
            width=width,
            height=height,
            expected_width=expected_w,
            expected_height=expected_h,
            bleed_px=bleed_px,
            has_black_borders=has_black_borders,
            errors=errors,
            warnings=warnings,
        )

    def conform_expanded_image(
        self,
        raw_bytes: bytes,
        base_size: Tuple[int, int],
        mode: str = "bleed_5mm",
        bleed_mm: float = DEFAULT_BLEED_MM,
        custom_size: Optional[Tuple[int, int]] = None,
    ) -> bytes:
        """Remove eventuais barras pretas periféricas e padroniza a resolução final com sangria 300 DPI."""
        spec = normalize_expansion_mode(mode)
        target_w, target_h, _ = calculate_expanded_dimensions(
            base_width=base_size[0],
            base_height=base_size[1],
            mode=spec.code,
            bleed_mm=bleed_mm,
            dpi=DEFAULT_DPI,
            custom_size=custom_size,
        )

        try:
            with Image.open(io.BytesIO(raw_bytes)) as img:
                rgb_img = img.convert("RGB")
                width, height = rgb_img.size
                stat = ImageStat.Stat(rgb_img)
                mean_std_dev = sum(stat.stddev) / len(stat.stddev) if stat.stddev else 0.0

                if width < self.MIN_SOURCE_DIMENSION or height < self.MIN_SOURCE_DIMENSION:
                    return raw_bytes
                if mean_std_dev < self.min_std_dev_threshold:
                    return raw_bytes

                cleaned_img = self.trim_black_borders(rgb_img)
                if spec.requires_horizontal_orientation and cleaned_img.width <= cleaned_img.height:
                    return raw_bytes

                if cleaned_img.size == (target_w, target_h):
                    out_buf = io.BytesIO()
                    cleaned_img.save(out_buf, format="PNG", dpi=(DEFAULT_DPI, DEFAULT_DPI))
                    return out_buf.getvalue()

                scale = max(target_w / cleaned_img.width, target_h / cleaned_img.height)
                new_w = int(round(cleaned_img.width * scale))
                new_h = int(round(cleaned_img.height * scale))

                scaled = cleaned_img.resize(
                    (new_w, new_h),
                    resample=Image.Resampling.LANCZOS,
                )
                left = max(0, (new_w - target_w) // 2)
                top = max(0, (new_h - target_h) // 2)
                final_img = scaled.crop((left, top, left + target_w, top + target_h))

                out_buf = io.BytesIO()
                final_img.save(out_buf, format="PNG", dpi=(DEFAULT_DPI, DEFAULT_DPI))
                return out_buf.getvalue()
        except Exception:
            return raw_bytes

    @staticmethod
    def _load_raw_bytes(
        source: Union[str, Path, bytes], errors: List[str]
    ) -> Optional[bytes]:
        """Carrega os bytes a partir de caminho de arquivo ou buffer em memória."""
        if isinstance(source, bytes):
            if not source:
                errors.append("O conteúdo em bytes da imagem expandida está vazio.")
                return None
            return source

        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.is_file():
                errors.append(f"Arquivo de imagem expandida não encontrado: {path}")
                return None
            data = path.read_bytes()
            if not data:
                errors.append(f"Arquivo de imagem expandida está vazio (0 bytes): {path}")
                return None
            return data

        errors.append(
            f"Tipo inválido para validação de imagem expandida: {type(source).__name__}"
        )
        return None


__all__ = [
    "ExpandedImageValidator",
    "ExpansionValidationResult",
    "calculate_bleed_pixels",
]
