"""Montador de layouts para Caneca de Sublimação 11oz / 325ml a 300 DPI (tools/mug_artist/composer.py)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Final, List, Optional, Sequence, Tuple, Union

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from tools.mug_artist.color_engine import (
    DEFAULT_SATURATION_BOOST,
    apply_sublimation_compensation,
)

DPI: Final[int] = 300
MM_PER_INCH: Final[float] = 25.4


def mm_to_px(mm: float, dpi: int = DPI) -> int:
    """Converte milímetros para pixels inteiros na resolução especificada (padrão: 300 DPI)."""
    if mm < 0:
        raise ValueError("A medida em milímetros não pode ser negativa.")
    if dpi <= 0:
        raise ValueError("O valor de 'dpi' deve ser maior que zero.")
    return int(round((mm / MM_PER_INCH) * dpi))


# Parâmetros Físicos Rigorosos da Studio Kustom (Caneca 11oz / 325ml)
MUG_CAPACITY_OZ: Final[int] = 11
MUG_CAPACITY_ML: Final[int] = 325

MUG_WIDTH_MM: Final[float] = 220.0
MUG_HEIGHT_MM: Final[float] = 95.0

MUG_WIDTH_PX: Final[int] = mm_to_px(MUG_WIDTH_MM, DPI)    # 2598 px
MUG_HEIGHT_PX: Final[int] = mm_to_px(MUG_HEIGHT_MM, DPI)  # 1122 px
MUG_SIZE_PX: Final[Tuple[int, int]] = (MUG_WIDTH_PX, MUG_HEIGHT_PX)

# Margem de segurança da alça: 10 mm (118 px) nas bordas extremas esquerda e direita
HANDLE_MARGIN_MM: Final[float] = 10.0
HANDLE_MARGIN_PX: Final[int] = mm_to_px(HANDLE_MARGIN_MM, DPI)  # 118 px

# Centros das Faces Úteis em X (a 300 DPI)
LEFT_FACE_CENTER_X_RATIO: Final[float] = 0.25
CENTER_FACE_CENTER_X_RATIO: Final[float] = 0.50
RIGHT_FACE_CENTER_X_RATIO: Final[float] = 0.75

LEFT_FACE_CENTER_X_PX: Final[int] = int(round(MUG_WIDTH_PX * LEFT_FACE_CENTER_X_RATIO))      # 650 px
CENTER_FACE_CENTER_X_PX: Final[int] = int(round(MUG_WIDTH_PX * CENTER_FACE_CENTER_X_RATIO))  # 1299 px
RIGHT_FACE_CENTER_X_PX: Final[int] = int(MUG_WIDTH_PX * RIGHT_FACE_CENTER_X_RATIO)           # 1948 px
MUG_CENTER_Y_PX: Final[int] = MUG_HEIGHT_PX // 2                                             # 561 px


@dataclass(frozen=True)
class MugSpec:
    """Especificação física e digital da caneca de sublimação 11oz (325ml) a 300 DPI."""

    name: str = "Caneca 11oz / 325ml"
    capacity_oz: int = MUG_CAPACITY_OZ
    capacity_ml: int = MUG_CAPACITY_ML
    width_mm: float = MUG_WIDTH_MM
    height_mm: float = MUG_HEIGHT_MM
    width_px: int = MUG_WIDTH_PX
    height_px: int = MUG_HEIGHT_PX
    dpi: int = DPI
    handle_margin_mm: float = HANDLE_MARGIN_MM
    handle_margin_px: int = HANDLE_MARGIN_PX
    left_face_center_x_px: int = LEFT_FACE_CENTER_X_PX
    center_face_center_x_px: int = CENTER_FACE_CENTER_X_PX
    right_face_center_x_px: int = RIGHT_FACE_CENTER_X_PX
    center_y_px: int = MUG_CENTER_Y_PX

    @property
    def usable_left_x_px(self) -> int:
        """Início da área útil após a margem esquerda de segurança da alça (118 px)."""
        return self.handle_margin_px

    @property
    def usable_right_x_px(self) -> int:
        """Fim da área útil antes da margem direita de segurança da alça (2480 px)."""
        return self.width_px - self.handle_margin_px

    @property
    def usable_width_px(self) -> int:
        """Largura útil total descontando as duas margens de segurança da alça (2362 px)."""
        return self.width_px - (2 * self.handle_margin_px)


DEFAULT_MUG_SPEC: Final[MugSpec] = MugSpec()


@dataclass(frozen=True)
class MugLayoutModeSpec:
    """Especificação de um modo de composição de layout para caneca."""

    code: str
    label: str
    description: str


MUG_LAYOUT_MODES: Final[Dict[str, MugLayoutModeSpec]] = {
    "panoramic": MugLayoutModeSpec(
        code="panoramic",
        label="Panorâmico Contínuo (220x95mm)",
        description=(
            "Arte da carta posicionada no centro (X=1299px, oposta à alça) ou com expansão "
            "contínua em toda a faixa de 220x95mm (2598x1122px)."
        ),
    ),
    "dual_face": MugLayoutModeSpec(
        code="dual_face",
        label="Dupla Face (Esquerda + Direita)",
        description=(
            "Posiciona duas artes (ou a mesma carta duplicada) na Face Esquerda (X=650px) "
            "e na Face Direita (X=1948px), respeitando a margem de 10mm (118px) da alça."
        ),
    ),
    "card_plus_text": MugLayoutModeSpec(
        code="card_plus_text",
        label="Carta + Texto Comemorativo",
        description=(
            "Posiciona a carta na Face Esquerda (X=650px) e uma mensagem/texto comemorativo "
            "centralizado na Face Direita (X=1948px)."
        ),
    ),
}


def normalize_mug_mode(mode: str) -> MugLayoutModeSpec:
    """Normaliza e valida o modo de layout da caneca ('panoramic', 'dual_face', 'card_plus_text')."""
    if not isinstance(mode, str) or not mode.strip():
        raise ValueError("O modo de layout ('mode') deve ser uma string não vazia.")

    cleaned = mode.strip().lower().replace("-", "_")
    aliases = {
        "panoramico": "panoramic",
        "panorâmico": "panoramic",
        "pano": "panoramic",
        "center": "panoramic",
        "centro": "panoramic",
        "dual": "dual_face",
        "duas_faces": "dual_face",
        "double": "dual_face",
        "two_faces": "dual_face",
        "text": "card_plus_text",
        "card_text": "card_plus_text",
        "carta_texto": "card_plus_text",
        "mensagem": "card_plus_text",
    }
    resolved = aliases.get(cleaned, cleaned)
    if resolved not in MUG_LAYOUT_MODES:
        valid = ", ".join(sorted(MUG_LAYOUT_MODES.keys()))
        raise ValueError(
            f"Modo de layout de caneca inválido: '{mode}'. Modos suportados: {valid}."
        )
    return MUG_LAYOUT_MODES[resolved]


def mirror_for_sublimation(image: Image.Image) -> Image.Image:
    """Espelha horizontalmente a imagem via `ImageOps.mirror` para transfer correto na prensa térmica."""
    if not isinstance(image, Image.Image):
        raise TypeError("O parâmetro 'image' deve ser uma instância de PIL.Image.Image.")
    original_info = dict(image.info)
    mirrored = ImageOps.mirror(image)
    mirrored.info.update(original_info)
    return mirrored


def _load_rgb_image(image_or_path: Union[str, Path, Image.Image]) -> Image.Image:
    """Carrega um caminho de arquivo ou converte `Image.Image` para RGB."""
    if isinstance(image_or_path, Image.Image):
        return image_or_path.convert("RGB")
    path = Path(image_or_path)
    if not path.is_file():
        raise FileNotFoundError(f"Imagem para arte de caneca não encontrada: {path}")
    with Image.open(path) as img:
        return img.convert("RGB")


def _build_continuous_backdrop(
    source_img: Image.Image,
    target_size: Tuple[int, int] = MUG_SIZE_PX,
) -> Image.Image:
    """Cria um fundo contínuo atmosférico preenchendo a faixa completa de 2598x1122 px."""
    fitted = ImageOps.fit(
        source_img.convert("RGB"),
        target_size,
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    return fitted.filter(ImageFilter.GaussianBlur(radius=28))


def _fit_card_to_face(
    card_img: Image.Image,
    max_width_px: int,
    max_height_px: int,
) -> Image.Image:
    """Redimensiona proporcionalmente a arte da carta para caber na área da face sem cortes."""
    src_w, src_h = card_img.size
    if src_w <= 0 or src_h <= 0:
        raise ValueError("A imagem da carta possui dimensões inválidas.")

    scale = min(max_width_px / src_w, max_height_px / src_h)
    new_w = max(1, int(round(src_w * scale)))
    new_h = max(1, int(round(src_h * scale)))
    return card_img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def _paste_centered(
    canvas: Image.Image,
    element: Image.Image,
    center_x: int,
    center_y: int,
) -> Tuple[int, int, int, int]:
    """Cola `element` centralizado nas coordenadas `(center_x, center_y)` do `canvas` e retorna o bbox."""
    elem_w, elem_h = element.size
    left = int(round(center_x - (elem_w / 2.0)))
    top = int(round(center_y - (elem_h / 2.0)))
    canvas.paste(element, (left, top))
    return (left, top, left + elem_w, top + elem_h)


def _load_best_font(size_px: int) -> Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]:
    """Tenta carregar uma fonte TrueType legível do sistema ou retorna a fonte padrão do Pillow."""
    font_candidates = [
        "arialbd.ttf",
        "arial.ttf",
        "calibrib.ttf",
        "segoeui.ttf",
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
    ]
    for font_name in font_candidates:
        try:
            return ImageFont.truetype(font_name, size=size_px)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size_px)
    except TypeError:
        return ImageFont.load_default()


def _wrap_text_lines(text: str, max_chars_per_line: int = 22) -> List[str]:
    """Quebra o texto comemorativo em múltiplas linhas equilibradas."""
    raw_lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not raw_lines:
        return ["Studio Kustom"]

    wrapped: List[str] = []
    for raw_line in raw_lines:
        words = raw_line.split()
        if not words:
            continue
        current = words[0]
        for word in words[1:]:
            if len(current) + 1 + len(word) <= max_chars_per_line:
                current = f"{current} {word}"
            else:
                wrapped.append(current)
                current = word
        wrapped.append(current)
    return wrapped or ["Studio Kustom"]


class MugArtworkComposer:
    """Compositor de layouts para caneca de sublimação 11oz (2598x1122 px a 300 DPI)."""

    def __init__(self, spec: MugSpec = DEFAULT_MUG_SPEC) -> None:
        self.spec = spec

    def compose_panoramic(
        self,
        image: Union[str, Path, Image.Image],
        panoramic_fill: bool = False,
    ) -> Image.Image:
        """Compõe o modo `panoramic` (2598x1122 px) com a arte posicionada no centro (`X = 1299 px`).

        Se a imagem já possuir proporção panorâmica (`largura / altura >= 1.8`) ou se
        `panoramic_fill=True`, preenche toda a faixa de 2598x1122 px centrada em `(1299, 561)`.
        Caso contrário (ex: carta vertical), gera um fundo contínuo em toda a extensão
        de 2598x1122 px e posiciona a carta íntegra perfeitamente centralizada na Face Centro
        (`X = 1299 px`, `Y = 561 px`).
        """
        src = _load_rgb_image(image)
        src_w, src_h = src.size
        aspect = src_w / float(src_h)

        if panoramic_fill or aspect >= 1.8:
            canvas = ImageOps.fit(
                src,
                (self.spec.width_px, self.spec.height_px),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
        else:
            canvas = _build_continuous_backdrop(
                src, (self.spec.width_px, self.spec.height_px)
            )
            max_card_w = self.spec.usable_width_px
            max_card_h = self.spec.height_px
            fitted_card = _fit_card_to_face(src, max_card_w, max_card_h)
            _paste_centered(
                canvas,
                fitted_card,
                center_x=self.spec.center_face_center_x_px,
                center_y=self.spec.center_y_px,
            )

        canvas.info["dpi"] = (self.spec.dpi, self.spec.dpi)
        return canvas

    def compose_dual_face(
        self,
        images: Sequence[Union[str, Path, Image.Image]],
    ) -> Image.Image:
        """Compõe o modo `dual_face` posicionando artes na Face Esquerda (`X=650`) e Direita (`X=1948`).

        Se apenas 1 imagem for fornecida, ela é automaticamente duplicada nas duas faces.
        Respeita rigorosamente a margem de segurança da alça de 10 mm (`118 px`) nas bordas
        extremas esquerda e direita.
        """
        if not images:
            raise ValueError("Pelo menos uma imagem deve ser informada para o modo 'dual_face'.")

        left_src = _load_rgb_image(images[0])
        right_src = _load_rgb_image(images[1] if len(images) >= 2 else images[0])

        # Fundo contínuo combinando a atmosfera das duas faces
        half_w = self.spec.width_px // 2
        left_bg = _build_continuous_backdrop(left_src, (half_w, self.spec.height_px))
        right_bg = _build_continuous_backdrop(
            right_src, (self.spec.width_px - half_w, self.spec.height_px)
        )

        canvas = Image.new("RGB", (self.spec.width_px, self.spec.height_px))
        canvas.paste(left_bg, (0, 0))
        canvas.paste(right_bg, (half_w, 0))
        canvas = canvas.filter(ImageFilter.GaussianBlur(radius=8))

        # Largura máxima de cada face respeitando a margem de 118px da alça:
        # Face esquerda centrada em 650px -> distância até a margem da alça (118px) é 532px -> máx 1064px
        max_face_w = 2 * (self.spec.left_face_center_x_px - self.spec.handle_margin_px)
        max_face_h = self.spec.height_px

        left_card = _fit_card_to_face(left_src, max_face_w, max_face_h)
        right_card = _fit_card_to_face(right_src, max_face_w, max_face_h)

        _paste_centered(
            canvas,
            left_card,
            center_x=self.spec.left_face_center_x_px,
            center_y=self.spec.center_y_px,
        )
        _paste_centered(
            canvas,
            right_card,
            center_x=self.spec.right_face_center_x_px,
            center_y=self.spec.center_y_px,
        )

        canvas.info["dpi"] = (self.spec.dpi, self.spec.dpi)
        return canvas

    def compose_card_plus_text(
        self,
        image: Union[str, Path, Image.Image],
        text: Optional[str] = None,
    ) -> Image.Image:
        """Compõe o modo `card_plus_text`: carta na Face Esquerda (`X=650`) e texto na Face Direita (`X=1948`)."""
        card_src = _load_rgb_image(image)
        message = (text or "").strip() or "Studio Kustom"

        canvas = _build_continuous_backdrop(
            card_src, (self.spec.width_px, self.spec.height_px)
        )

        max_face_w = 2 * (self.spec.left_face_center_x_px - self.spec.handle_margin_px)
        max_face_h = self.spec.height_px

        left_card = _fit_card_to_face(card_src, max_face_w, max_face_h)
        _paste_centered(
            canvas,
            left_card,
            center_x=self.spec.left_face_center_x_px,
            center_y=self.spec.center_y_px,
        )

        # Renderiza painel e texto comemorativo centralizado na Face Direita (X = 1948 px, Y = 561 px)
        draw = ImageDraw.Draw(canvas)
        panel_w = min(860, max_face_w - 40)
        panel_h = min(720, self.spec.height_px - 200)
        panel_left = self.spec.right_face_center_x_px - (panel_w // 2)
        panel_top = self.spec.center_y_px - (panel_h // 2)
        panel_bbox = [
            panel_left,
            panel_top,
            panel_left + panel_w,
            panel_top + panel_h,
        ]

        draw.rounded_rectangle(
            panel_bbox,
            radius=28,
            fill=(20, 24, 34),
            outline=(235, 195, 95),
            width=6,
        )

        lines = _wrap_text_lines(message, max_chars_per_line=22)
        font_size = 64 if len(lines) <= 3 else 48
        font = _load_best_font(font_size)

        line_bboxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
        line_heights = [max(24, b[3] - b[1]) for b in line_bboxes]
        line_spacing = 20
        total_text_h = sum(line_heights) + line_spacing * max(0, len(lines) - 1)

        current_y = self.spec.center_y_px - (total_text_h // 2)
        for line, bbox, lh in zip(lines, line_bboxes, line_heights):
            lw = bbox[2] - bbox[0]
            tx = self.spec.right_face_center_x_px - (lw // 2)
            draw.text(
                (tx, current_y),
                line,
                fill=(255, 248, 230),
                font=font,
            )
            current_y += lh + line_spacing

        canvas.info["dpi"] = (self.spec.dpi, self.spec.dpi)
        return canvas

    def compose(
        self,
        image_or_images: Union[
            str, Path, Image.Image, Sequence[Union[str, Path, Image.Image]]
        ],
        mode: str = "panoramic",
        text: Optional[str] = None,
        apply_color_compensation: bool = True,
        saturation_boost: float = DEFAULT_SATURATION_BOOST,
    ) -> Tuple[Image.Image, Image.Image]:
        """Monta o layout da caneca e retorna `(arte_previa_visual, arte_transfer_espelhada)`.

        Args:
            image_or_images: Caminho/imagem única ou sequência de caminhos/imagens.
            mode: Modo de layout ('panoramic', 'dual_face', 'card_plus_text').
            text: Texto comemorativo opcional (usado no modo `card_plus_text`).
            apply_color_compensation: Se True, aplica a compensação de +18% de saturação para Epson L110.
            saturation_boost: Fator de saturação (padrão: 1.18).

        Returns:
            Tupla `(preview_image, mirrored_transfer_image)` em 2598x1122 px a 300 DPI.
        """
        mode_spec = normalize_mug_mode(mode)

        if isinstance(image_or_images, (str, Path, Image.Image)):
            items: List[Union[str, Path, Image.Image]] = [image_or_images]
        else:
            items = list(image_or_images)

        if not items:
            raise ValueError("Nenhuma imagem fornecida para composição da caneca.")

        if mode_spec.code == "panoramic":
            preview_img = self.compose_panoramic(items[0])
        elif mode_spec.code == "dual_face":
            preview_img = self.compose_dual_face(items)
        elif mode_spec.code == "card_plus_text":
            preview_img = self.compose_card_plus_text(items[0], text=text)
        else:  # pragma: no cover
            raise ValueError(f"Modo não suportado: {mode_spec.code}")

        if apply_color_compensation:
            preview_img = apply_sublimation_compensation(
                preview_img, saturation_boost=saturation_boost
            )

        preview_img.info["dpi"] = (self.spec.dpi, self.spec.dpi)
        transfer_img = mirror_for_sublimation(preview_img)
        transfer_img.info["dpi"] = (self.spec.dpi, self.spec.dpi)

        return preview_img, transfer_img
