"""Validador técnico de resolução (300 DPI), orientação e integridade para posters (tools/upscaler)."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

from PIL import Image, ImageStat, UnidentifiedImageError

from tools.upscaler.prompt_builder import PosterFormatSpec, normalize_target_format


@dataclass
class PosterValidationResult:
    """Resultado detalhado da inspeção técnica de um poster gerado."""

    is_valid: bool
    target_format: str
    width: int
    height: int
    aspect_ratio: float
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class PosterImageValidator:
    """Valida se o poster gerado atinge os requisitos físicos de 300 DPI da Studio Kustom."""

    ASPECT_RATIO_TOLERANCE: float = 0.20
    MIN_STD_DEV_THRESHOLD: float = 5.0
    MIN_SOURCE_DIMENSION: int = 512

    def __init__(
        self,
        aspect_ratio_tolerance: float = ASPECT_RATIO_TOLERANCE,
        min_std_dev_threshold: float = MIN_STD_DEV_THRESHOLD,
    ) -> None:
        self.aspect_ratio_tolerance = aspect_ratio_tolerance
        self.min_std_dev_threshold = min_std_dev_threshold

    def validate_poster(
        self,
        image_path_or_bytes: Union[str, Path, bytes],
        target_format: str,
    ) -> PosterValidationResult:
        """Valida se a imagem cumpre a resolução, orientação, proporção e integridade do formato alvo.

        Args:
            image_path_or_bytes: Caminho do arquivo ou bytes brutos da imagem.
            target_format: Código do formato ('a4_v', 'a4_h', 'a3_v', 'a3_h').

        Returns:
            Instância de `PosterValidationResult`.
        """
        spec: PosterFormatSpec = normalize_target_format(target_format)
        errors: List[str] = []
        warnings: List[str] = []

        raw_bytes = self._load_raw_bytes(image_path_or_bytes, errors)
        if raw_bytes is None:
            return PosterValidationResult(
                is_valid=False,
                target_format=spec.code,
                width=0,
                height=0,
                aspect_ratio=0.0,
                errors=errors,
                warnings=warnings,
            )

        try:
            with Image.open(io.BytesIO(raw_bytes)) as verify_img:
                verify_img.verify()
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
            errors.append(f"Imagem de poster corrompida ou inválida: {exc}")
            return PosterValidationResult(
                is_valid=False,
                target_format=spec.code,
                width=0,
                height=0,
                aspect_ratio=0.0,
                errors=errors,
                warnings=warnings,
            )

        try:
            with Image.open(io.BytesIO(raw_bytes)) as img:
                rgb_img = img.convert("RGB")
                width, height = rgb_img.size
                stat = ImageStat.Stat(rgb_img)
        except Exception as exc:
            errors.append(f"Falha ao decodificar pixels do poster: {exc}")
            return PosterValidationResult(
                is_valid=False,
                target_format=spec.code,
                width=0,
                height=0,
                aspect_ratio=0.0,
                errors=errors,
                warnings=warnings,
            )

        if width <= 0 or height <= 0:
            errors.append(f"Dimensões inválidas detectadas: {width}x{height}px.")
            return PosterValidationResult(
                is_valid=False,
                target_format=spec.code,
                width=width,
                height=height,
                aspect_ratio=0.0,
                errors=errors,
                warnings=warnings,
            )

        aspect_ratio = round(height / width, 3)

        # 1. Orientação exigida pelo formato
        if spec.orientation == "vertical" and height <= width:
            errors.append(
                f"Orientação incompatível com {spec.code} ({spec.label}): "
                f"esperado vertical (altura > largura), obtido {width}x{height}px."
            )
        elif spec.orientation == "horizontal" and width <= height:
            errors.append(
                f"Orientação incompatível com {spec.code} ({spec.label}): "
                f"esperado horizontal (largura > altura), obtido {width}x{height}px."
            )

        # 2. Tolerância de proporção (aspect ratio)
        if abs(aspect_ratio - spec.aspect_ratio) > self.aspect_ratio_tolerance:
            errors.append(
                f"Proporção {aspect_ratio:.3f} incompatível com o formato {spec.code} "
                f"(esperado ~{spec.aspect_ratio:.3f} ± {self.aspect_ratio_tolerance:.2f})."
            )

        # 3. Resolução mínima exigida para impressão 300 DPI
        if width < spec.width_px or height < spec.height_px:
            errors.append(
                f"Resolução insuficiente para {spec.code} a {spec.dpi} DPI: "
                f"obtido {width}x{height}px, exigido mínimo {spec.width_px}x{spec.height_px}px."
            )

        # 4. Variância cromática contra imagens monocromáticas/vazias
        mean_std_dev = sum(stat.stddev) / len(stat.stddev) if stat.stddev else 0.0
        if mean_std_dev < self.min_std_dev_threshold:
            errors.append(
                f"Poster monocromático ou vazio detectado (desvio padrão médio RGB: {mean_std_dev:.2f})."
            )

        return PosterValidationResult(
            is_valid=len(errors) == 0,
            target_format=spec.code,
            width=width,
            height=height,
            aspect_ratio=aspect_ratio,
            errors=errors,
            warnings=warnings,
        )

    @staticmethod
    def trim_black_borders(
        img: Image.Image,
        threshold: int = 20,
        max_margin_ratio: float = 0.20,
    ) -> Image.Image:
        """Detecta e remove margens/barras pretas (pillarboxing/letterboxing) nas bordas da imagem.

        Converte temporariamente para escala de cinza e analisa o bounding box de pixels úteis
        acima do threshold de luminância (para ignorar ruído de compressão JPEG/dark mode).
        """
        if img.width <= 0 or img.height <= 0:
            return img

        gray = img.convert("L")
        thresh = gray.point(lambda p: 255 if p > threshold else 0)
        bbox = thresh.getbbox()
        if not bbox:
            return img

        left, top, right, bottom = bbox
        max_w = int(img.width * max_margin_ratio)
        max_h = int(img.height * max_margin_ratio)

        # Limita o corte caso a margem detectada exceda a tolerância máxima
        crop_left = left if left <= max_w else 0
        crop_top = top if top <= max_h else 0
        crop_right = right if (img.width - right) <= max_w else img.width
        crop_bottom = bottom if (img.height - bottom) <= max_h else img.height

        if crop_left > 0 or crop_top > 0 or crop_right < img.width or crop_bottom < img.height:
            if crop_right > crop_left and crop_bottom > crop_top:
                return img.crop((crop_left, crop_top, crop_right, crop_bottom))
        return img

    def conform_to_poster_spec(
        self, raw_bytes: bytes, target_format: str
    ) -> bytes:
        """Ajusta uma imagem válida gerada pelo Gemini para a resolução exata de 300 DPI do formato alvo.

        Remove barras pretas periféricas (pillarbox/letterbox) e aplica escalonamento com
        sangria mínima (center-crop cover) para preservar estritamente a proporção original da arte.
        Preserva falhas caso a imagem original seja corrompida, muito pequena (< 512px),
        monocromática ou esteja na orientação incorreta, garantindo que o validador as reprove.
        """
        spec = normalize_target_format(target_format)
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
                if spec.orientation == "vertical" and height <= width:
                    return raw_bytes
                if spec.orientation == "horizontal" and width <= height:
                    return raw_bytes

                # 1. Apara qualquer barra preta periférica (pillarboxing/letterboxing)
                cleaned_img = self.trim_black_borders(rgb_img)

                # Se a imagem limpa já estiver na resolução exata do formato
                if cleaned_img.size == (spec.width_px, spec.height_px):
                    out_buffer = io.BytesIO()
                    cleaned_img.save(out_buffer, format="PNG", dpi=(spec.dpi, spec.dpi))
                    return out_buffer.getvalue()

                # 2. Escalonamento proporcional com corte central de sangria (center-crop cover)
                target_w, target_h = spec.width_px, spec.height_px
                scale = max(target_w / cleaned_img.width, target_h / cleaned_img.height)
                new_w = int(round(cleaned_img.width * scale))
                new_h = int(round(cleaned_img.height * scale))

                scaled = cleaned_img.resize(
                    (new_w, new_h),
                    resample=Image.Resampling.LANCZOS,
                )

                left = max(0, (new_w - target_w) // 2)
                top = max(0, (new_h - target_h) // 2)
                final_poster = scaled.crop((left, top, left + target_w, top + target_h))

                out_buffer = io.BytesIO()
                final_poster.save(out_buffer, format="PNG", dpi=(spec.dpi, spec.dpi))
                return out_buffer.getvalue()
        except Exception:
            return raw_bytes

    @staticmethod
    def _load_raw_bytes(
        source: Union[str, Path, bytes], errors: List[str]
    ) -> Optional[bytes]:
        """Carrega os bytes a partir de caminho em disco ou buffer em memória."""
        if isinstance(source, bytes):
            if not source:
                errors.append("O conteúdo em bytes do poster está vazio.")
                return None
            return source

        if isinstance(source, (str, Path)):
            path = Path(source)
            if not path.is_file():
                errors.append(f"Arquivo de poster não encontrado: {path}")
                return None
            data = path.read_bytes()
            if not data:
                errors.append(f"Arquivo de poster está vazio (0 bytes): {path}")
                return None
            return data

        errors.append(f"Tipo inválido para validação de poster: {type(source).__name__}")
        return None
