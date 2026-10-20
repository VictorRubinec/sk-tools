"""Marcas de corte finas (0.25mm / 3px) e cruzes de registro gráfico nos 4 cantos da folha."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, List, Optional, Tuple

from PIL import Image, ImageDraw

if TYPE_CHECKING:
    from tools.print_sheet.card_grid import CardGridImposition

CROP_LINE_WIDTH_MM: Final[float] = 0.25
CROP_LINE_WIDTH_PX: Final[int] = 3  # ~0.25mm @ 300 DPI (0.25 * 300 / 25.4 = 2.95px)
CROP_MARK_LENGTH_PX: Final[int] = 36  # ~3.0mm @ 300 DPI
CROP_MARK_OFFSET_PX: Final[int] = 12  # ~1.0mm de recuo para não invadir a sangria/arte
REGISTRATION_RADIUS_PX: Final[int] = 24  # Raio da cruz de registro (~2mm; diâmetro ~4mm)
DEFAULT_REGISTRATION_OFFSET_PX: Final[Tuple[int, int]] = (62, 106)
MARK_COLOR: Final[Tuple[int, int, int]] = (0, 0, 0)


def get_registration_centers(
    sheet_size_px: Tuple[int, int],
    corner_offset_px: Optional[Tuple[int, int]] = None,
) -> List[Tuple[int, int]]:
    """Retorna as coordenadas (cx, cy) das 4 cruzes de registro simétricas nos cantos da folha."""
    width, height = sheet_size_px
    ox, oy = corner_offset_px if corner_offset_px is not None else DEFAULT_REGISTRATION_OFFSET_PX
    ox = max(REGISTRATION_RADIUS_PX + 6, min(ox, width // 4))
    oy = max(REGISTRATION_RADIUS_PX + 6, min(oy, height // 4))
    return [
        (ox, oy),
        (width - ox, oy),
        (ox, height - oy),
        (width - ox, height - oy),
    ]


def draw_registration_crosses(
    image: Image.Image,
    corner_offset_px: Optional[Tuple[int, int]] = None,
    radius_px: int = REGISTRATION_RADIUS_PX,
    line_width_px: int = CROP_LINE_WIDTH_PX,
    color: Tuple[int, int, int] = MARK_COLOR,
) -> Image.Image:
    """Desenha cruzes de registro gráfico nos 4 cantos da folha para alinhamento duplex e guilhotina."""
    draw = ImageDraw.Draw(image)
    centers = get_registration_centers(image.size, corner_offset_px=corner_offset_px)
    circle_r = max(6, radius_px // 2)

    for cx, cy in centers:
        # Linha horizontal da cruz de registro
        draw.line(
            [(cx - radius_px, cy), (cx + radius_px, cy)],
            fill=color,
            width=line_width_px,
        )
        # Linha vertical da cruz de registro
        draw.line(
            [(cx, cy - radius_px), (cx, cy + radius_px)],
            fill=color,
            width=line_width_px,
        )
        # Anel de mira central
        draw.ellipse(
            [cx - circle_r, cy - circle_r, cx + circle_r, cy + circle_r],
            outline=color,
            width=line_width_px,
        )

    return image


def draw_grid_crop_marks(
    image: Image.Image,
    grid: CardGridImposition,
    line_width_px: int = CROP_LINE_WIDTH_PX,
    mark_length_px: int = CROP_MARK_LENGTH_PX,
    offset_px: int = CROP_MARK_OFFSET_PX,
    color: Tuple[int, int, int] = MARK_COLOR,
) -> Image.Image:
    """Desenha marcas de corte (0.25mm / 3px) nos cantos externos e nos canais de separação da grade."""
    draw = ImageDraw.Draw(image)
    sheet_w, sheet_h = image.size
    left, top, right, bottom = grid.grid_bbox_px

    xs = grid.vertical_cut_lines_px()
    ys = grid.horizontal_cut_lines_px()

    # Marcas verticais (no topo e na base da folha) alinhadas aos cantos externos e canais de colunas
    top_y1 = max(0, top - offset_px - mark_length_px)
    top_y2 = max(0, top - offset_px)
    bot_y1 = min(sheet_h - 1, bottom + offset_px)
    bot_y2 = min(sheet_h - 1, bottom + offset_px + mark_length_px)

    for x in xs:
        if top_y2 > top_y1:
            draw.line([(x, top_y1), (x, top_y2)], fill=color, width=line_width_px)
        if bot_y2 > bot_y1:
            draw.line([(x, bot_y1), (x, bot_y2)], fill=color, width=line_width_px)

    # Marcas horizontais (na esquerda e na direita da folha) alinhadas aos cantos externos e canais de linhas
    left_x1 = max(0, left - offset_px - mark_length_px)
    left_x2 = max(0, left - offset_px)
    right_x1 = min(sheet_w - 1, right + offset_px)
    right_x2 = min(sheet_w - 1, right + offset_px + mark_length_px)

    for y in ys:
        if left_x2 > left_x1:
            draw.line([(left_x1, y), (left_x2, y)], fill=color, width=line_width_px)
        if right_x2 > right_x1:
            draw.line([(right_x1, y), (right_x2, y)], fill=color, width=line_width_px)

    # Caso exista espaçamento interno (gap_px > 0) entre as cartas, desenha marcas nos cruzamentos internos
    if grid.gap_px > 0:
        half_tick = max(4, min(mark_length_px // 3, grid.gap_px // 2))
        for x in xs[1:-1]:
            for y in ys[1:-1]:
                draw.line([(x - half_tick, y), (x + half_tick, y)], fill=color, width=line_width_px)
                draw.line([(x, y - half_tick), (x, y + half_tick)], fill=color, width=line_width_px)

    return image


def draw_rect_crop_marks(
    image: Image.Image,
    bbox: Tuple[int, int, int, int],
    line_width_px: int = CROP_LINE_WIDTH_PX,
    mark_length_px: int = CROP_MARK_LENGTH_PX,
    offset_px: int = CROP_MARK_OFFSET_PX,
    color: Tuple[int, int, int] = MARK_COLOR,
) -> Image.Image:
    """Desenha marcas de corte nos 4 cantos de um retângulo único (ex: pôster centralizado na folha)."""
    draw = ImageDraw.Draw(image)
    sheet_w, sheet_h = image.size
    left, top, right, bottom = bbox

    # Se o pôster tiver margem suficiente, desenha marcas externas ao retângulo;
    # se preencher a folha inteira (margem próxima de zero), desenha marcas de canto na borda interna
    has_outer_margin_x = left >= (offset_px + 8) and (sheet_w - right) >= (offset_px + 8)
    has_outer_margin_y = top >= (offset_px + 8) and (sheet_h - bottom) >= (offset_px + 8)

    if has_outer_margin_x and has_outer_margin_y:
        for x in (left, right):
            draw.line(
                [(x, max(0, top - offset_px - mark_length_px)), (x, max(0, top - offset_px))],
                fill=color,
                width=line_width_px,
            )
            draw.line(
                [
                    (x, min(sheet_h - 1, bottom + offset_px)),
                    (x, min(sheet_h - 1, bottom + offset_px + mark_length_px)),
                ],
                fill=color,
                width=line_width_px,
            )
        for y in (top, bottom):
            draw.line(
                [(max(0, left - offset_px - mark_length_px), y), (max(0, left - offset_px), y)],
                fill=color,
                width=line_width_px,
            )
            draw.line(
                [
                    (min(sheet_w - 1, right + offset_px), y),
                    (min(sheet_w - 1, right + offset_px + mark_length_px), y),
                ],
                fill=color,
                width=line_width_px,
            )
    else:
        # Pôster sem margem externa (full-bleed): marcas de corte finas nos 4 cantos a 24px da borda
        inset = 24
        L = mark_length_px
        # Canto superior esquerdo
        draw.line([(inset, inset), (inset + L, inset)], fill=color, width=line_width_px)
        draw.line([(inset, inset), (inset, inset + L)], fill=color, width=line_width_px)
        # Canto superior direito
        draw.line([(sheet_w - 1 - inset - L, inset), (sheet_w - 1 - inset, inset)], fill=color, width=line_width_px)
        draw.line([(sheet_w - 1 - inset, inset), (sheet_w - 1 - inset, inset + L)], fill=color, width=line_width_px)
        # Canto inferior esquerdo
        draw.line([(inset, sheet_h - 1 - inset), (inset + L, sheet_h - 1 - inset)], fill=color, width=line_width_px)
        draw.line([(inset, sheet_h - 1 - inset - L), (inset, sheet_h - 1 - inset)], fill=color, width=line_width_px)
        # Canto inferior direito
        draw.line(
            [(sheet_w - 1 - inset - L, sheet_h - 1 - inset), (sheet_w - 1 - inset, sheet_h - 1 - inset)],
            fill=color,
            width=line_width_px,
        )
        draw.line(
            [(sheet_w - 1 - inset, sheet_h - 1 - inset - L), (sheet_w - 1 - inset, sheet_h - 1 - inset)],
            fill=color,
            width=line_width_px,
        )

    return image


def apply_sheet_marks(
    image: Image.Image,
    grid: Optional[CardGridImposition] = None,
    rect_bbox: Optional[Tuple[int, int, int, int]] = None,
    line_width_px: int = CROP_LINE_WIDTH_PX,
) -> Image.Image:
    """Aplica marcas de corte (grade 3x3 ou retângulo de pôster) e as 4 cruzes de registro nos cantos."""
    if grid is not None:
        draw_grid_crop_marks(image, grid=grid, line_width_px=line_width_px)
        corner_offset = (max(48, grid.margin_x_px // 2), max(48, grid.margin_y_px // 2))
        draw_registration_crosses(
            image, corner_offset_px=corner_offset, line_width_px=line_width_px
        )
    elif rect_bbox is not None:
        draw_rect_crop_marks(image, bbox=rect_bbox, line_width_px=line_width_px)
        draw_registration_crosses(image, line_width_px=line_width_px)
    else:
        draw_registration_crosses(image, line_width_px=line_width_px)

    return image
