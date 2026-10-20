"""Quality Gates determinísticos para inspeção física e digital da esteira Studio Kustom (tools/order_planner/quality_gates.py)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple, Union

import pymupdf as fitz
from PIL import Image, ImageChops, ImageOps, ImageStat, UnidentifiedImageError

from tools.background_expander.prompt_builder import DEFAULT_BLEED_MM, calculate_bleed_pixels
from tools.mug_artist.composer import DPI, MUG_HEIGHT_PX, MUG_WIDTH_PX
from tools.order_planner.schema import QualityGateResult
from tools.upscaler.prompt_builder import PosterFormatSpec, normalize_target_format
from tools.upscaler.validator import PosterImageValidator

BLEED_5MM_PX: int = calculate_bleed_pixels(DEFAULT_BLEED_MM, DPI)  # 59 px por borda @ 300 DPI
MIN_DPI_TOLERANCE: float = 299.0  # PNG pHYs armazena 300 DPI como 11811 px/m (~299.9994 DPI)
MIN_SHEET_DIMENSION_PT: float = 500.0  # A4 (210mm) = 595.2 pt; Super A4 (230mm) = 652.08 pt


def _resolve_poster_format_spec(
    expected_format: str,
    img_size: Tuple[int, int] = (2480, 3543),
) -> PosterFormatSpec:
    """Resolve códigos de formato como 'a4', 'a3', 'a4_v', 'a4_h', 'a3_v', 'a3_h'."""
    cleaned = (expected_format or "").strip().lower().replace("-", "_")
    is_horizontal = img_size[0] > img_size[1]
    if cleaned == "a4":
        cleaned = "a4_h" if is_horizontal else "a4_v"
    elif cleaned == "a3":
        cleaned = "a3_h" if is_horizontal else "a3_v"
    return normalize_target_format(cleaned)


def verify_upscale_gate(
    image_path: Union[str, Path],
    expected_format: str = "a4_v",
) -> QualityGateResult:
    """Avalia o Quality Gate de Upscaling (300 DPI, resolução mínima e ausência de pillarbox).

    Args:
        image_path: Caminho do arquivo de imagem gerado pelo upscaler.
        expected_format: Formato esperado ('a4_v', 'a4_h', 'a3_v', 'a3_h', 'a4', 'a3').

    Returns:
        `QualityGateResult` indicando aprovação ou reprovação determinística.
    """
    path = Path(image_path)
    if not path.is_file():
        return QualityGateResult(
            stage="upscale",
            passed=False,
            details=f"Arquivo de imagem não encontrado para inspeção de upscale: {path}",
            file_checked=path,
        )

    try:
        with Image.open(path) as verify_img:
            verify_img.verify()
        with Image.open(path) as img:
            dpi_info = img.info.get("dpi")
            rgb_img = img.convert("RGB")
            width, height = rgb_img.size
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        return QualityGateResult(
            stage="upscale",
            passed=False,
            details=f"Imagem corrompida ou ilegível em '{path.name}': {exc}",
            file_checked=path,
        )

    try:
        spec = _resolve_poster_format_spec(expected_format, img_size=(width, height))
    except ValueError as exc:
        return QualityGateResult(
            stage="upscale",
            passed=False,
            details=str(exc),
            file_checked=path,
        )

    errors: List[str] = []

    # 1. Verificação de metadado de DPI (quando presente na imagem)
    if dpi_info is not None:
        dpi_x, dpi_y = float(dpi_info[0]), float(dpi_info[1])
        if dpi_x < MIN_DPI_TOLERANCE or dpi_y < MIN_DPI_TOLERANCE:
            errors.append(
                f"DPI insuficiente: obtido ({dpi_x:.1f}, {dpi_y:.1f}) DPI, exigido 300 DPI."
            )

    # 2. Validação técnica de resolução mínima, orientação, aspect ratio e variância cromática
    validator = PosterImageValidator()
    validation = validator.validate_poster(path, spec.code)
    if not validation.is_valid:
        errors.extend(validation.errors)

    # 3. Verificação estrita contra pillarboxing / letterboxing (barras pretas nas bordas)
    trimmed_img = PosterImageValidator.trim_black_borders(rgb_img)
    if trimmed_img.size != rgb_img.size:
        errors.append(
            f"Pillarbox/letterbox (barras pretas periféricas) detectado: "
            f"dimensão original {width}x{height}px reduzida para {trimmed_img.width}x{trimmed_img.height}px."
        )

    if errors:
        return QualityGateResult(
            stage="upscale",
            passed=False,
            details=" | ".join(errors),
            file_checked=path,
        )

    resolved_dpi = (
        f"{int(round(float(dpi_info[0])))} DPI"
        if dpi_info is not None
        else f"{spec.dpi} DPI (nominal)"
    )
    return QualityGateResult(
        stage="upscale",
        passed=True,
        details=(
            f"Upscale aprovado no formato {spec.code}: {width}x{height}px @ {resolved_dpi}, "
            f"proporção {validation.aspect_ratio:.3f}, sem pillarbox."
        ),
        file_checked=path,
    )


def verify_bleed_gate(
    image_path: Union[str, Path],
    original_size: Tuple[int, int],
) -> QualityGateResult:
    """Avalia o Quality Gate de Expansão de Sangria (+59px por borda / 5mm a 300 DPI).

    Args:
        image_path: Caminho da imagem com fundo expandido.
        original_size: Tupla `(largura_original, altura_original)` antes da sangria.

    Returns:
        `QualityGateResult` confirmando se houve acréscimo exato de +59px por borda (+118px por eixo).
    """
    path = Path(image_path)
    if not path.is_file():
        return QualityGateResult(
            stage="bleed",
            passed=False,
            details=f"Arquivo expandido não encontrado para inspeção de sangria: {path}",
            file_checked=path,
        )

    if (
        not isinstance(original_size, (tuple, list))
        or len(original_size) != 2
        or int(original_size[0]) <= 0
        or int(original_size[1]) <= 0
    ):
        return QualityGateResult(
            stage="bleed",
            passed=False,
            details=f"Tamanho original inválido informado para verify_bleed_gate: {original_size}",
            file_checked=path,
        )

    orig_w, orig_h = int(original_size[0]), int(original_size[1])
    expected_w = orig_w + 2 * BLEED_5MM_PX  # +59px esquerda e +59px direita (+118px)
    expected_h = orig_h + 2 * BLEED_5MM_PX  # +59px topo e +59px base (+118px)

    try:
        with Image.open(path) as verify_img:
            verify_img.verify()
        with Image.open(path) as img:
            rgb_img = img.convert("RGB")
            width, height = rgb_img.size
            stat = ImageStat.Stat(rgb_img)
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        return QualityGateResult(
            stage="bleed",
            passed=False,
            details=f"Imagem expandida corrompida ou inválida em '{path.name}': {exc}",
            file_checked=path,
        )

    errors: List[str] = []

    if width != expected_w or height != expected_h:
        delta_w = width - orig_w
        delta_h = height - orig_h
        errors.append(
            f"Sangria incorreta: esperado {expected_w}x{expected_h}px "
            f"(original {orig_w}x{orig_h}px + {BLEED_5MM_PX}px/borda = +{2 * BLEED_5MM_PX}px/eixo), "
            f"obtido {width}x{height}px (delta={delta_w:+d}x{delta_h:+d}px)."
        )

    mean_std_dev = sum(stat.stddev) / len(stat.stddev) if stat.stddev else 0.0
    if mean_std_dev < PosterImageValidator.MIN_STD_DEV_THRESHOLD:
        errors.append(
            f"Imagem expandida monocromática ou vazia (desvio padrão RGB: {mean_std_dev:.2f})."
        )

    trimmed_img = PosterImageValidator.trim_black_borders(rgb_img)
    if trimmed_img.size != rgb_img.size:
        errors.append(
            f"Barras pretas detectadas na área de sangria: dimensão útil reduzida para "
            f"{trimmed_img.width}x{trimmed_img.height}px."
        )

    if errors:
        return QualityGateResult(
            stage="bleed",
            passed=False,
            details=" | ".join(errors),
            file_checked=path,
        )

    return QualityGateResult(
        stage="bleed",
        passed=True,
        details=(
            f"Sangria de 5mm (+{BLEED_5MM_PX}px por borda) confirmada: "
            f"{orig_w}x{orig_h}px -> {width}x{height}px sem barras pretas."
        ),
        file_checked=path,
    )


def verify_sheet_gate(
    pdf_path: Union[str, Path],
    expected_pages: int,
) -> QualityGateResult:
    """Avalia o Quality Gate de Folha de Impressão PDF via PyMuPDF (`fitz`).

    Verifica a integridade do documento PDF, o número exato de páginas (`expected_pages`)
    e as dimensões físicas de cada página.

    Args:
        pdf_path: Caminho do arquivo PDF da folha de impressão.
        expected_pages: Quantidade exata de páginas esperada (ex: 1 para pôster, 2 para folha duplex TCG).

    Returns:
        `QualityGateResult` com o parecer técnico da folha PDF.
    """
    path = Path(pdf_path)
    if not path.is_file():
        return QualityGateResult(
            stage="sheet",
            passed=False,
            details=f"Arquivo PDF de folha de impressão não encontrado: {path}",
            file_checked=path,
        )

    if expected_pages < 1:
        return QualityGateResult(
            stage="sheet",
            passed=False,
            details=f"Número esperado de páginas inválido: {expected_pages} (mínimo 1).",
            file_checked=path,
        )

    if path.stat().st_size == 0:
        return QualityGateResult(
            stage="sheet",
            passed=False,
            details=f"Arquivo PDF está vazio (0 bytes): {path}",
            file_checked=path,
        )

    try:
        with fitz.open(path) as doc:
            page_count = doc.page_count
            page_rects = [(p.rect.width, p.rect.height) for p in doc]
    except Exception as exc:
        return QualityGateResult(
            stage="sheet",
            passed=False,
            details=f"Falha ao abrir ou inspecionar PDF via PyMuPDF: {exc}",
            file_checked=path,
        )

    errors: List[str] = []

    if page_count != expected_pages:
        errors.append(
            f"Quantidade de páginas divergente: esperado {expected_pages}, encontrado {page_count}."
        )

    page_summaries: List[str] = []
    for idx, (w_pt, h_pt) in enumerate(page_rects, start=1):
        w_mm = round((w_pt * 25.4) / 72.0, 1)
        h_mm = round((h_pt * 25.4) / 72.0, 1)
        page_summaries.append(f"pág.{idx}={w_mm}x{h_mm}mm ({w_pt:.1f}x{h_pt:.1f}pt)")
        if w_pt < MIN_SHEET_DIMENSION_PT or h_pt < MIN_SHEET_DIMENSION_PT:
            errors.append(
                f"Página {idx} com dimensões físicas abaixo do mínimo de folha gráfica: "
                f"{w_mm}x{h_mm}mm ({w_pt:.1f}x{h_pt:.1f}pt)."
            )

    if errors:
        return QualityGateResult(
            stage="sheet",
            passed=False,
            details=" | ".join(errors),
            file_checked=path,
        )

    return QualityGateResult(
        stage="sheet",
        passed=True,
        details=(
            f"Folha PDF aprovada com {page_count} página(s): "
            + ", ".join(page_summaries)
        ),
        file_checked=path,
    )


def verify_mug_gate(
    preview_path: Union[str, Path],
    transfer_path: Union[str, Path],
) -> QualityGateResult:
    """Avalia o Quality Gate de Caneca 11oz (2598x1122px a 300 DPI e espelhamento horizontal).

    Args:
        preview_path: Caminho da imagem de prévia visual (orientação normal).
        transfer_path: Caminho da imagem de transfer térmico (espelhada horizontalmente).

    Returns:
        `QualityGateResult` validando resolução 2598x1122px e espelhamento horizontal exato.
    """
    p_path = Path(preview_path)
    t_path = Path(transfer_path)

    if not p_path.is_file():
        return QualityGateResult(
            stage="mug",
            passed=False,
            details=f"Arquivo de prévia da caneca não encontrado: {p_path}",
            file_checked=p_path,
        )

    if not t_path.is_file():
        return QualityGateResult(
            stage="mug",
            passed=False,
            details=f"Arquivo de transfer da caneca não encontrado: {t_path}",
            file_checked=t_path,
        )

    try:
        with Image.open(p_path) as vp:
            vp.verify()
        with Image.open(t_path) as vt:
            vt.verify()
        with Image.open(p_path) as p_img, Image.open(t_path) as t_img:
            p_dpi = p_img.info.get("dpi")
            t_dpi = t_img.info.get("dpi")
            preview_rgb = p_img.convert("RGB")
            transfer_rgb = t_img.convert("RGB")
            t_stat = ImageStat.Stat(transfer_rgb)
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        return QualityGateResult(
            stage="mug",
            passed=False,
            details=f"Falha ao decodificar imagens da caneca: {exc}",
            file_checked=t_path,
        )

    errors: List[str] = []
    expected_size = (MUG_WIDTH_PX, MUG_HEIGHT_PX)  # (2598, 1122)

    if preview_rgb.size != expected_size:
        errors.append(
            f"Resolução da prévia inválida: obtido {preview_rgb.width}x{preview_rgb.height}px, "
            f"exigido {MUG_WIDTH_PX}x{MUG_HEIGHT_PX}px."
        )

    if transfer_rgb.size != expected_size:
        errors.append(
            f"Resolução do transfer inválida: obtido {transfer_rgb.width}x{transfer_rgb.height}px, "
            f"exigido {MUG_WIDTH_PX}x{MUG_HEIGHT_PX}px."
        )

    for label, dpi_val in (("prévia", p_dpi), ("transfer", t_dpi)):
        if dpi_val is not None:
            if float(dpi_val[0]) < MIN_DPI_TOLERANCE or float(dpi_val[1]) < MIN_DPI_TOLERANCE:
                errors.append(
                    f"DPI insuficiente na imagem de {label}: ({dpi_val[0]:.1f}, {dpi_val[1]:.1f}) DPI."
                )

    mean_std_dev = sum(t_stat.stddev) / len(t_stat.stddev) if t_stat.stddev else 0.0
    if mean_std_dev < PosterImageValidator.MIN_STD_DEV_THRESHOLD:
        errors.append(
            f"Arte de caneca monocromática ou vazia detectada (desvio padrão RGB: {mean_std_dev:.2f})."
        )

    # Verifica espelhamento horizontal quando ambas possuem o mesmo tamanho
    if preview_rgb.size == transfer_rgb.size:
        mirrored_preview = ImageOps.mirror(preview_rgb)
        mirror_diff = ImageChops.difference(mirrored_preview, transfer_rgb)
        mirror_stat = ImageStat.Stat(mirror_diff)
        mean_mirror_diff = (
            sum(mirror_stat.mean) / len(mirror_stat.mean) if mirror_stat.mean else 0.0
        )

        # Verifica se a imagem original não é simétrica e se o transfer ficou sem espelhar
        self_sym_diff = ImageChops.difference(preview_rgb, mirrored_preview)
        self_sym_stat = ImageStat.Stat(self_sym_diff)
        mean_self_sym = (
            sum(self_sym_stat.mean) / len(self_sym_stat.mean) if self_sym_stat.mean else 0.0
        )

        unmirrored_diff = ImageChops.difference(preview_rgb, transfer_rgb)
        unmirrored_stat = ImageStat.Stat(unmirrored_diff)
        mean_unmirrored_diff = (
            sum(unmirrored_stat.mean) / len(unmirrored_stat.mean)
            if unmirrored_stat.mean
            else 0.0
        )

        if mean_mirror_diff > 1.5:
            if mean_unmirrored_diff <= 1.5 and mean_self_sym > 1.5:
                errors.append(
                    "Transfer NÃO está espelhado horizontalmente (idêntico à prévia em orientação normal)."
                )
            else:
                errors.append(
                    f"Transfer diverge do espelhamento horizontal da prévia "
                    f"(diferença média RGB: {mean_mirror_diff:.2f})."
                )

    if errors:
        return QualityGateResult(
            stage="mug",
            passed=False,
            details=" | ".join(errors),
            file_checked=t_path,
        )

    return QualityGateResult(
        stage="mug",
        passed=True,
        details=(
            f"Arte de caneca 11oz aprovada: prévia e transfer em {MUG_WIDTH_PX}x{MUG_HEIGHT_PX}px "
            f"(220x95mm @ {DPI} DPI) com espelhamento horizontal confirmado."
        ),
        file_checked=t_path,
    )


__all__ = [
    "BLEED_5MM_PX",
    "verify_bleed_gate",
    "verify_mug_gate",
    "verify_sheet_gate",
    "verify_upscale_gate",
]
