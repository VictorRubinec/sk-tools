"""Motor de compensação cromática para sublimação na impressora Epson L110 (tools/mug_artist/color_engine.py)."""

from __future__ import annotations

from typing import Final

from PIL import Image, ImageEnhance

DEFAULT_SATURATION_BOOST: Final[float] = 1.18


def apply_sublimation_compensation(
    image: Image.Image,
    saturation_boost: float = DEFAULT_SATURATION_BOOST,
) -> Image.Image:
    """Aplica compensação cromática para prensa térmica e tinta sublimática (Epson L110).

    Aplica o fator de saturação padrão de +18% (`1.18x`) utilizando `PIL.ImageEnhance.Color`,
    mantendo o contraste equilibrado sem estourar os highlights (altas luzes).

    Args:
        image: Imagem `PIL.Image.Image` de entrada.
        saturation_boost: Fator multiplicador de saturação cromática (padrão: `1.18`).

    Returns:
        Nova instância `PIL.Image.Image` com saturação compensada em modo RGB (ou RGBA se a
        imagem de entrada possuir canal alfa).

    Raises:
        TypeError: Se `image` não for uma instância de `PIL.Image.Image`.
        ValueError: Se `saturation_boost` for menor ou igual a zero.
    """
    if not isinstance(image, Image.Image):
        raise TypeError("O parâmetro 'image' deve ser uma instância de PIL.Image.Image.")
    if saturation_boost <= 0:
        raise ValueError("O fator 'saturation_boost' deve ser maior que zero.")

    original_info = dict(image.info)

    if image.mode == "RGBA":
        r, g, b, alpha = image.split()
        rgb_base = Image.merge("RGB", (r, g, b))
        enhancer = ImageEnhance.Color(rgb_base)
        compensated_rgb = enhancer.enhance(saturation_boost)
        cr, cg, cb = compensated_rgb.split()
        result = Image.merge("RGBA", (cr, cg, cb, alpha))
    else:
        rgb_base = image.convert("RGB")
        enhancer = ImageEnhance.Color(rgb_base)
        result = enhancer.enhance(saturation_boost)

    result.info.update(original_info)
    return result
