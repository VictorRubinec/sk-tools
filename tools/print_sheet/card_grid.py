"""Cálculo geométrico e imposição em grade 3x3 para cartas TCG (Studio Kustom @ 300 DPI)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Final, List, Optional, Sequence, Tuple, TypeVar, Union

from PIL import Image, ImageOps

from tools.print_sheet.crop_marks import apply_sheet_marks

T = TypeVar("T")

DPI: Final[int] = 300
MM_PER_INCH: Final[float] = 25.4

# Especificações físicas da Carta TCG (63 x 88 mm @ 300 DPI -> 744 x 1039 px)
TCG_CARD_WIDTH_MM: Final[float] = 63.0
TCG_CARD_HEIGHT_MM: Final[float] = 88.0
TCG_CARD_WIDTH_PX: Final[int] = 744
TCG_CARD_HEIGHT_PX: Final[int] = 1039

# Especificações físicas do Verso com Sangria 3mm (69 x 94 mm @ 300 DPI -> 815 x 1110 px)
TCG_BLEED_MM: Final[float] = 3.0
TCG_BACK_WIDTH_MM: Final[float] = 69.0  # 63.0 + 2 * 3.0 (reduzido 1mm adicional por borda)
TCG_BACK_HEIGHT_MM: Final[float] = 94.0  # 88.0 + 2 * 3.0 (reduzido 1mm adicional por borda)
TCG_BACK_WIDTH_PX: Final[int] = 815  # mm_to_px(69.0) -> 815
TCG_BACK_HEIGHT_PX: Final[int] = 1110  # mm_to_px(94.0) -> 1110

# Calibração oficial Super A4 Studio Kustom (230 x 320 mm @ 300 DPI)
SUPER_A4_WIDTH_MM: Final[float] = 230.0
SUPER_A4_HEIGHT_MM: Final[float] = 320.0
SUPER_A4_WIDTH_PX: Final[int] = 2717  # mm_to_px(230.0) -> 2717
SUPER_A4_HEIGHT_PX: Final[int] = 3780  # mm_to_px(320.0) -> 3780
SUPER_A4_GUTTER_X_MM: Final[float] = 9.0  # 9mm horizontal (coluna esq +1mm / coluna dir -1mm)
SUPER_A4_GUTTER_Y_MM: Final[float] = 14.0
SUPER_A4_GUTTER_X_PX: Final[int] = 106  # mm_to_px(9.0) -> 106
SUPER_A4_GUTTER_Y_PX: Final[int] = 165

GRID_ROWS: Final[int] = 3
GRID_COLS: Final[int] = 3
MAX_CARDS_PER_SHEET: Final[int] = GRID_ROWS * GRID_COLS  # 9 cartas por folha


def mm_to_px(mm: float, dpi: int = DPI) -> int:
    """Converte milímetros para pixels na resolução especificada (padrão: 300 DPI)."""
    if dpi <= 0:
        raise ValueError(f"O DPI deve ser positivo. Recebido: {dpi}")
    return int(round((mm * dpi) / MM_PER_INCH))


@dataclass(frozen=True)
class PaperSpec:
    """Especificação física e em pixels (300 DPI) de uma folha de impressão Studio Kustom."""

    code: str
    label: str
    width_mm: float
    height_mm: float
    width_px: int
    height_px: int
    dpi: int = DPI

    @property
    def aspect_ratio(self) -> float:
        """Retorna a proporção altura / largura arredondada em 3 casas decimais."""
        return round(self.height_px / self.width_px, 3)

    @property
    def size_px(self) -> Tuple[int, int]:
        """Retorna a tupla (largura_px, altura_px)."""
        return (self.width_px, self.height_px)

    @property
    def size_mm(self) -> Tuple[float, float]:
        """Retorna a tupla (largura_mm, altura_mm)."""
        return (self.width_mm, self.height_mm)


PAPER_SPECS: Final[Dict[str, PaperSpec]] = {
    "SUPER_A4": PaperSpec(
        code="SUPER_A4",
        label="Super A4 Studio Kustom (230x320mm)",
        width_mm=SUPER_A4_WIDTH_MM,
        height_mm=SUPER_A4_HEIGHT_MM,
        width_px=SUPER_A4_WIDTH_PX,
        height_px=SUPER_A4_HEIGHT_PX,
        dpi=DPI,
    ),
    "A4": PaperSpec(
        code="A4",
        label="A4 Studio Kustom (210x300mm)",
        width_mm=210.0,
        height_mm=300.0,
        width_px=2480,
        height_px=3543,
        dpi=DPI,
    ),
    "A3": PaperSpec(
        code="A3",
        label="A3 Studio Kustom (300x420mm)",
        width_mm=300.0,
        height_mm=420.0,
        width_px=3543,
        height_px=4960,
        dpi=DPI,
    ),
    "A4_H": PaperSpec(
        code="A4_H",
        label="A4 Horizontal Studio Kustom (300x210mm)",
        width_mm=300.0,
        height_mm=210.0,
        width_px=3543,
        height_px=2480,
        dpi=DPI,
    ),
    "A3_H": PaperSpec(
        code="A3_H",
        label="A3 Horizontal Studio Kustom (420x300mm)",
        width_mm=420.0,
        height_mm=300.0,
        width_px=4960,
        height_px=3543,
        dpi=DPI,
    ),
}


def normalize_paper_spec(paper: str = "super_a4") -> PaperSpec:
    """Normaliza e valida o código do papel ('super_a4', 'a4', 'a3', 'a4_v', 'a4_h', 'a3_v', 'a3_h')."""
    if not isinstance(paper, str) or not paper.strip():
        raise ValueError("O formato do papel ('paper') deve ser uma string não vazia.")

    cleaned = paper.strip().upper().replace("-", "_")
    if cleaned in ("SUPER_A4", "SUPERA4", "SUPER_A4_V", "SUPER_A4_VERTICAL"):
        cleaned = "SUPER_A4"
    elif cleaned in ("A4", "A4_V", "A4_VERTICAL"):
        cleaned = "A4"
    elif cleaned in ("A3", "A3_V", "A3_VERTICAL"):
        cleaned = "A3"
    elif cleaned == "A4_HORIZONTAL":
        cleaned = "A4_H"
    elif cleaned == "A3_HORIZONTAL":
        cleaned = "A3_H"

    if cleaned not in PAPER_SPECS:
        valid = ", ".join(sorted(PAPER_SPECS.keys()))
        raise ValueError(
            f"Formato de papel inválido: '{paper}'. Formatos suportados: {valid}."
        )
    return PAPER_SPECS[cleaned]


@dataclass(frozen=True)
class CardSlot:
    """Representa o posicionamento geométrico exato de uma carta na grade de imposição."""

    index: int
    row: int
    col: int
    source_col: int
    x_px: int
    y_px: int
    width_px: int
    height_px: int
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    is_back: bool = False
    nominal_x_px: int = 0
    nominal_y_px: int = 0
    nominal_width_px: int = TCG_CARD_WIDTH_PX
    nominal_height_px: int = TCG_CARD_HEIGHT_PX
    bleed_mm: float = 0.0

    @property
    def bbox(self) -> Tuple[int, int, int, int]:
        """Retorna a bounding box em pixels (left, top, right, bottom)."""
        return (self.x_px, self.y_px, self.x_px + self.width_px, self.y_px + self.height_px)

    @property
    def center_px(self) -> Tuple[int, int]:
        """Retorna o ponto central da carta em pixels (cx, cy)."""
        return (self.x_px + self.width_px // 2, self.y_px + self.height_px // 2)

    @property
    def nominal_bbox(self) -> Tuple[int, int, int, int]:
        """Retorna a bounding box nominal de corte (63x88mm) em pixels."""
        return (
            self.nominal_x_px,
            self.nominal_y_px,
            self.nominal_x_px + self.nominal_width_px,
            self.nominal_y_px + self.nominal_height_px,
        )


def load_image_rgb(source: Union[str, Path, Image.Image]) -> Image.Image:
    """Carrega uma imagem a partir de caminho ou instância PIL e converte para RGB."""
    if isinstance(source, Image.Image):
        return source.convert("RGB")
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo de imagem não encontrado: {path}")
    with Image.open(path) as img:
        return img.convert("RGB")


class CardGridImposition:
    """Motor de imposição gráfica em grade 3x3 para cartas TCG com espelhamento duplex."""

    def __init__(
        self,
        paper: str = "super_a4",
        rows: int = GRID_ROWS,
        cols: int = GRID_COLS,
        card_width_mm: float = TCG_CARD_WIDTH_MM,
        card_height_mm: float = TCG_CARD_HEIGHT_MM,
        card_width_px: int = TCG_CARD_WIDTH_PX,
        card_height_px: int = TCG_CARD_HEIGHT_PX,
        back_width_mm: float = TCG_BACK_WIDTH_MM,
        back_height_mm: float = TCG_BACK_HEIGHT_MM,
        back_width_px: int = TCG_BACK_WIDTH_PX,
        back_height_px: int = TCG_BACK_HEIGHT_PX,
        gutter_x_mm: Optional[float] = None,
        gutter_y_mm: Optional[float] = None,
        gap_mm: Optional[float] = None,
    ) -> None:
        self.paper_spec: PaperSpec = normalize_paper_spec(paper)
        self.dpi: int = self.paper_spec.dpi
        self.rows: int = rows
        self.cols: int = cols
        self.max_cards: int = rows * cols

        self.card_width_mm: float = float(card_width_mm)
        self.card_height_mm: float = float(card_height_mm)
        self.card_width_px: int = int(card_width_px)
        self.card_height_px: int = int(card_height_px)

        self.back_width_mm: float = float(back_width_mm)
        self.back_height_mm: float = float(back_height_mm)
        self.back_width_px: int = int(back_width_px)
        self.back_height_px: int = int(back_height_px)

        # Configuração de gutters (canais de espaçamento entre cartas)
        if gutter_x_mm is not None:
            self.gutter_x_mm: float = float(gutter_x_mm)
        elif gap_mm is not None:
            self.gutter_x_mm = float(gap_mm)
        elif self.paper_spec.code == "SUPER_A4":
            self.gutter_x_mm = SUPER_A4_GUTTER_X_MM
        else:
            self.gutter_x_mm = 0.0

        if gutter_y_mm is not None:
            self.gutter_y_mm: float = float(gutter_y_mm)
        elif gap_mm is not None:
            self.gutter_y_mm = float(gap_mm)
        elif self.paper_spec.code == "SUPER_A4":
            self.gutter_y_mm = SUPER_A4_GUTTER_Y_MM
        else:
            self.gutter_y_mm = 0.0

        self.gutter_x_px: int = (
            SUPER_A4_GUTTER_X_PX
            if (self.paper_spec.code == "SUPER_A4" and self.gutter_x_mm == SUPER_A4_GUTTER_X_MM)
            else mm_to_px(self.gutter_x_mm, self.dpi)
        )
        self.gutter_y_px: int = (
            SUPER_A4_GUTTER_Y_PX
            if (self.paper_spec.code == "SUPER_A4" and self.gutter_y_mm == SUPER_A4_GUTTER_Y_MM)
            else mm_to_px(self.gutter_y_mm, self.dpi)
        )

        # Interface compatível para inspeções legadas de gap
        self.gap_mm: float = self.gutter_x_mm
        self.gap_px: int = self.gutter_x_px

        self.sheet_width_mm: float = self.paper_spec.width_mm
        self.sheet_height_mm: float = self.paper_spec.height_mm
        self.sheet_width_px: int = self.paper_spec.width_px
        self.sheet_height_px: int = self.paper_spec.height_px

        self.grid_width_mm: float = round(
            self.cols * self.card_width_mm + (self.cols - 1) * self.gutter_x_mm, 4
        )
        self.grid_height_mm: float = round(
            self.rows * self.card_height_mm + (self.rows - 1) * self.gutter_y_mm, 4
        )
        self.grid_width_px: int = (
            self.cols * self.card_width_px + (self.cols - 1) * self.gutter_x_px
        )
        self.grid_height_px: int = (
            self.rows * self.card_height_px + (self.rows - 1) * self.gutter_y_px
        )

        if self.grid_width_px > self.sheet_width_px or self.grid_height_px > self.sheet_height_px:
            raise ValueError(
                f"A grade {self.cols}x{self.rows} ({self.grid_width_px}x{self.grid_height_px}px) "
                f"excede as dimensões da folha {self.paper_spec.code} "
                f"({self.sheet_width_px}x{self.sheet_height_px}px)."
            )

        self.margin_x_mm: float = round((self.sheet_width_mm - self.grid_width_mm) / 2.0, 4)
        self.margin_y_mm: float = round((self.sheet_height_mm - self.grid_height_mm) / 2.0, 4)
        self.margin_x_px: int = (self.sheet_width_px - self.grid_width_px) // 2
        self.margin_y_px: int = (self.sheet_height_px - self.grid_height_px) // 2

    @property
    def grid_bbox_px(self) -> Tuple[int, int, int, int]:
        """Retorna a bounding box externa da grade nominal 3x3 na folha em pixels (left, top, right, bottom)."""
        return (
            self.margin_x_px,
            self.margin_y_px,
            self.margin_x_px + self.grid_width_px,
            self.margin_y_px + self.grid_height_px,
        )

    def mirror_column(self, col: int) -> int:
        """Inverte horizontalmente o índice da coluna (ex: 0 -> 2, 1 -> 1, 2 -> 0) para duplex."""
        if not (0 <= col < self.cols):
            raise ValueError(f"Índice de coluna fora do intervalo [0, {self.cols - 1}]: {col}")
        return (self.cols - 1) - col

    def mirror_row(self, row_items: Sequence[T]) -> List[T]:
        """Inverte a ordem dos elementos de uma linha para casar o verso no duplex."""
        if len(row_items) > self.cols:
            raise ValueError(
                f"A linha possui {len(row_items)} itens, mas a grade suporta no máximo {self.cols} colunas."
            )
        return list(reversed(row_items))

    def get_slot(self, index: int, is_back: bool = False) -> CardSlot:
        """Calcula o `CardSlot` para o índice linear `index` (0..8), aplicando sangria e espelhamento se `is_back=True`."""
        if not (0 <= index < self.max_cards):
            raise ValueError(
                f"Índice de carta fora do intervalo [0, {self.max_cards - 1}]: {index}"
            )
        row = index // self.cols
        source_col = index % self.cols

        if not is_back:
            actual_col = source_col
            x_px = self.margin_x_px + actual_col * (self.card_width_px + self.gutter_x_px)
            y_px = self.margin_y_px + row * (self.card_height_px + self.gutter_y_px)
            x_mm = round(self.margin_x_mm + actual_col * (self.card_width_mm + self.gutter_x_mm), 4)
            y_mm = round(self.margin_y_mm + row * (self.card_height_mm + self.gutter_y_mm), 4)

            return CardSlot(
                index=index,
                row=row,
                col=actual_col,
                source_col=source_col,
                x_px=x_px,
                y_px=y_px,
                width_px=self.card_width_px,
                height_px=self.card_height_px,
                x_mm=x_mm,
                y_mm=y_mm,
                width_mm=self.card_width_mm,
                height_mm=self.card_height_mm,
                is_back=False,
                nominal_x_px=x_px,
                nominal_y_px=y_px,
                nominal_width_px=self.card_width_px,
                nominal_height_px=self.card_height_px,
                bleed_mm=0.0,
            )

        # Verso espelhado: inverte as colunas (0 -> 2, 1 -> 1, 2 -> 0)
        actual_col = self.mirror_column(source_col)

        # Centro óptico da carta na frente
        front_x_px = self.margin_x_px + source_col * (self.card_width_px + self.gutter_x_px)
        front_y_px = self.margin_y_px + row * (self.card_height_px + self.gutter_y_px)
        front_cx = front_x_px + self.card_width_px // 2
        front_cy = front_y_px + self.card_height_px // 2

        # Centro óptico rigorosamente espelhado em X: X'_c = folha_largura - X_c, Y_c
        back_cx = self.sheet_width_px - front_cx
        back_cy = front_cy

        # Posição nominal de corte no verso (63 x 88 mm)
        nominal_x_px = back_cx - self.card_width_px // 2
        nominal_y_px = back_cy - self.card_height_px // 2

        # Posição do verso com sangria de 5mm por borda (73 x 98 mm / 862 x 1157 px)
        bleed_x_px = back_cx - self.back_width_px // 2
        bleed_y_px = back_cy - self.back_height_px // 2

        front_x_mm = self.margin_x_mm + source_col * (self.card_width_mm + self.gutter_x_mm)
        front_y_mm = self.margin_y_mm + row * (self.card_height_mm + self.gutter_y_mm)
        front_cx_mm = front_x_mm + self.card_width_mm / 2.0
        front_cy_mm = front_y_mm + self.card_height_mm / 2.0
        back_cx_mm = self.sheet_width_mm - front_cx_mm
        back_cy_mm = front_cy_mm
        bleed_x_mm = round(back_cx_mm - self.back_width_mm / 2.0, 4)
        bleed_y_mm = round(back_cy_mm - self.back_height_mm / 2.0, 4)

        return CardSlot(
            index=index,
            row=row,
            col=actual_col,
            source_col=source_col,
            x_px=bleed_x_px,
            y_px=bleed_y_px,
            width_px=self.back_width_px,
            height_px=self.back_height_px,
            x_mm=bleed_x_mm,
            y_mm=bleed_y_mm,
            width_mm=self.back_width_mm,
            height_mm=self.back_height_mm,
            is_back=True,
            nominal_x_px=nominal_x_px,
            nominal_y_px=nominal_y_px,
            nominal_width_px=self.card_width_px,
            nominal_height_px=self.card_height_px,
            bleed_mm=TCG_BLEED_MM,
        )

    def calculate_front_slots(self, num_cards: int = MAX_CARDS_PER_SHEET) -> List[CardSlot]:
        """Retorna a lista de slots da Página 1 (Frente) para `num_cards` cartas (1 a 9)."""
        if not (1 <= num_cards <= self.max_cards):
            raise ValueError(
                f"A quantidade de cartas por folha deve estar entre 1 e {self.max_cards}. Recebido: {num_cards}"
            )
        return [self.get_slot(i, is_back=False) for i in range(num_cards)]

    def calculate_back_slots(self, num_cards: int = MAX_CARDS_PER_SHEET) -> List[CardSlot]:
        """Retorna a lista de slots espelhados da Página 2 (Verso) para `num_cards` cartas (1 a 9)."""
        if not (1 <= num_cards <= self.max_cards):
            raise ValueError(
                f"A quantidade de cartas por folha deve estar entre 1 e {self.max_cards}. Recebido: {num_cards}"
            )
        return [self.get_slot(i, is_back=True) for i in range(num_cards)]

    def vertical_cut_lines_px(self) -> List[int]:
        """Retorna todas as coordenadas X (px) de corte vertical (bordas externas e canais entre colunas)."""
        xs: List[int] = []
        for col in range(self.cols):
            left_x = self.margin_x_px + col * (self.card_width_px + self.gutter_x_px)
            right_x = left_x + self.card_width_px
            if not xs or xs[-1] != left_x:
                xs.append(left_x)
            if xs[-1] != right_x:
                xs.append(right_x)
        return xs

    def horizontal_cut_lines_px(self) -> List[int]:
        """Retorna todas as coordenadas Y (px) de corte horizontal (bordas externas e canais entre linhas)."""
        ys: List[int] = []
        for row in range(self.rows):
            top_y = self.margin_y_px + row * (self.card_height_px + self.gutter_y_px)
            bottom_y = top_y + self.card_height_px
            if not ys or ys[-1] != top_y:
                ys.append(top_y)
            if ys[-1] != bottom_y:
                ys.append(bottom_y)
        return ys

    def resolve_back_images(
        self,
        front_count: int,
        back_image: Union[str, Path, Image.Image, Sequence[Union[str, Path, Image.Image]]],
    ) -> List[Union[str, Path, Image.Image]]:
        """Normaliza a entrada do verso (único compartilhado ou lista individual) para `front_count` itens."""
        if not (1 <= front_count <= self.max_cards):
            raise ValueError(
                f"A quantidade de cartas na frente deve estar entre 1 e {self.max_cards}. Recebido: {front_count}"
            )

        if isinstance(back_image, (str, Path, Image.Image)):
            return [back_image for _ in range(front_count)]

        back_list = list(back_image)
        if not back_list:
            raise ValueError("A lista de imagens de verso não pode ser vazia.")
        if len(back_list) == 1:
            return [back_list[0] for _ in range(front_count)]
        if len(back_list) != front_count:
            raise ValueError(
                f"Quantidade de versos ({len(back_list)}) incompatível com a quantidade de frentes ({front_count}). "
                "Forneça 1 verso padrão compartilhado ou exatamente 1 verso por carta."
            )
        return back_list

    def _fit_card_image(
        self,
        img: Image.Image,
        target_size: Optional[Tuple[int, int]] = None,
    ) -> Image.Image:
        """Dimensiona a imagem de carta para o tamanho exato da grade (sem recortar conteúdo)."""
        size = target_size or (self.card_width_px, self.card_height_px)
        if img.size == size:
            return img.copy()
        return img.resize(size, resample=Image.Resampling.LANCZOS)

    def _fit_back_image(self, img: Image.Image) -> Image.Image:
        """Ajusta uma imagem de verso para exatamente 73x98mm (+5mm sangria: 862x1157 px a 300 DPI)."""
        return self._fit_card_image(
            img, target_size=(self.back_width_px, self.back_height_px)
        )

    def render_front_sheet(
        self,
        front_images: Sequence[Union[str, Path, Image.Image]],
        draw_marks: bool = True,
    ) -> Image.Image:
        """Renderiza a Página 1 (Frente) com até 9 cartas nominais (63x88mm) e marcas de corte."""
        count = len(front_images)
        slots = self.calculate_front_slots(count)

        canvas = Image.new("RGB", (self.sheet_width_px, self.sheet_height_px), color=(255, 255, 255))
        for raw_img, slot in zip(front_images, slots):
            card_img = self._fit_card_image(load_image_rgb(raw_img))
            canvas.paste(card_img, (slot.x_px, slot.y_px))

        if draw_marks:
            apply_sheet_marks(canvas, grid=self)

        return canvas

    def render_back_sheet(
        self,
        back_image: Union[str, Path, Image.Image, Sequence[Union[str, Path, Image.Image]]],
        front_count: Optional[int] = None,
        draw_marks: bool = True,
    ) -> Image.Image:
        """Renderiza a Página 2 (Verso) com sangria de 5mm (73x98mm) e espelhamento horizontal (col 0 <-> 2)."""
        if front_count is None:
            if isinstance(back_image, (str, Path, Image.Image)):
                front_count = self.max_cards
            else:
                front_count = len(back_image)

        resolved_backs = self.resolve_back_images(front_count, back_image)
        slots = self.calculate_back_slots(front_count)

        canvas = Image.new("RGB", (self.sheet_width_px, self.sheet_height_px), color=(255, 255, 255))
        cached_single_img: Optional[Image.Image] = None
        if isinstance(back_image, (str, Path, Image.Image)) or (
            isinstance(back_image, Sequence) and len(back_image) == 1
        ):
            cached_single_img = self._fit_back_image(load_image_rgb(resolved_backs[0]))

        for raw_back, slot in zip(resolved_backs, slots):
            card_back_img = (
                cached_single_img
                if cached_single_img is not None
                else self._fit_back_image(load_image_rgb(raw_back))
            )
            canvas.paste(card_back_img, (slot.x_px, slot.y_px))

        if draw_marks:
            apply_sheet_marks(canvas, grid=self)

        return canvas

    def render_duplex_sheets(
        self,
        front_images: Sequence[Union[str, Path, Image.Image]],
        back_image: Union[str, Path, Image.Image, Sequence[Union[str, Path, Image.Image]]],
        draw_marks: bool = True,
    ) -> Tuple[Image.Image, Image.Image]:
        """Renderiza o par de folhas (Página 1: Frente, Página 2: Verso Espelhado) em 300 DPI."""
        front_sheet = self.render_front_sheet(front_images, draw_marks=draw_marks)
        back_sheet = self.render_back_sheet(
            back_image=back_image,
            front_count=len(front_images),
            draw_marks=draw_marks,
        )
        return front_sheet, back_sheet
