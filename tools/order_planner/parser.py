"""Parser de briefings (.txt / .json) e analisador semântico de pedidos da Studio Kustom (tools/order_planner/parser.py)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Union

from tools.card_generator.core.schema import CardInput
from tools.mug_artist.schema import MugInput
from tools.order_planner.schema import ProductRoute, normalize_product_route

GENERATED_FILE_PATTERNS = (
    "_upscaled",
    "_poster_",
    "_expanded",
    "_bleed",
    "_sheet_",
    "_mug_preview",
    "_mug_transfer",
    "_mug_panoramic",
    "_mug_dual_face",
    "_mug_card_plus_text",
    "dossie_producao",
)

BACK_IMAGE_KEYWORDS = ("fundo", "fundos", "back", "verso", "versopadrao", "versopadrão")


@dataclass
class ParsedOrderContext:
    """Contexto extraído a partir dos arquivos e textos de briefing de um pedido."""

    order_dir: Path
    route: ProductRoute
    briefing_text: str = ""
    target_format: str = "a3_v"
    needs_bleed: bool = True
    photos: List[Path] = field(default_factory=list)
    back_images: List[Path] = field(default_factory=list)
    briefing_files: List[Path] = field(default_factory=list)
    shipping_pdfs: List[Path] = field(default_factory=list)


def is_generated_artifact(file_path: Path) -> bool:
    """Identifica se um arquivo foi gerado previamente pela esteira sk-tools."""
    name_lower = file_path.name.lower()
    if name_lower == "dossie_producao.json":
        return True
    return any(pattern in name_lower for pattern in GENERATED_FILE_PATTERNS)


def is_back_image(file_path: Path) -> bool:
    """Verifica se o arquivo de imagem representa o verso/fundo de uma carta TCG."""
    stem_lower = file_path.stem.lower()
    for kw in BACK_IMAGE_KEYWORDS:
        if stem_lower == kw or f" {kw}" in stem_lower or f"_{kw}" in stem_lower or stem_lower.startswith(kw):
            return True
    return False


def read_order_briefing_text(order_dir: Union[str, Path]) -> str:
    """Lê e concatena os textos de briefing (`texto.txt`, `*.txt`, `*.json`) presentes na pasta do pedido."""
    dir_path = Path(order_dir)
    if not dir_path.is_dir():
        return ""

    chunks: List[str] = []
    for item in sorted(dir_path.iterdir()):
        if not item.is_file() or is_generated_artifact(item):
            continue
        suffix = item.suffix.lower()
        if suffix in (".txt", ".json"):
            try:
                content = item.read_text(encoding="utf-8").strip()
            except UnicodeDecodeError:
                content = item.read_text(encoding="latin-1", errors="ignore").strip()
            if content:
                chunks.append(content)
    return "\n\n".join(chunks)


def infer_poster_format(
    briefing_text: str = "",
    files: Optional[Sequence[Path]] = None,
) -> str:
    """Deduz o código de formato de pôster ('a3_v', 'a3_h', 'a4_v', 'a4_h') a partir do briefing, imagens e nomes de arquivo.

    Regra de padronização: Todo pedido da rota POSTER_FULL assume como padrão o formato A3
    (A3_V por padrão; se a largura for maior que a altura, como no pedido 178, assume A3_H).
    """
    combined = (briefing_text or "").lower()
    if files:
        filenames = " ".join(Path(f).name.lower() for f in files)
        combined = f"{combined} {filenames}".strip()

    is_horizontal = any(
        kw in combined for kw in ("a4_h", "a3_h", "horizontal", "paisagem", "landscape", "300x210", "420x300")
    )
    is_explicit_vertical = any(
        kw in combined for kw in ("a4_v", "a3_v", "vertical", "retrato", "portrait", "210x300", "300x420")
    )

    # Se a orientação não foi indicada explicitamente em texto, inspeciona dimensões reais da imagem
    if not is_horizontal and not is_explicit_vertical and files:
        for f in files:
            f_path = Path(f)
            if (
                f_path.is_file()
                and f_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
                and not is_generated_artifact(f_path)
            ):
                try:
                    from PIL import Image

                    with Image.open(f_path) as img:
                        if img.width > img.height:
                            is_horizontal = True
                            break
                except Exception:
                    pass

    is_explicit_a4 = any(re.search(rf"\b{re.escape(kw)}\b", combined) for kw in ("a4", "a4_v", "a4_h", "210x297"))
    is_explicit_a3 = any(re.search(rf"\b{re.escape(kw)}\b", combined) for kw in ("a3", "a3_v", "a3_h", "300x420", "420x300"))

    if is_explicit_a4 and not is_explicit_a3:
        return "a4_h" if is_horizontal else "a4_v"
    # Padrão Studio Kustom: A3
    return "a3_h" if is_horizontal else "a3_v"


def deduce_product_route(
    order_dir: Union[str, Path],
    briefing_text: Optional[str] = None,
    customer_files: Optional[Sequence[Path]] = None,
    route_override: Optional[Union[str, ProductRoute]] = None,
) -> ProductRoute:
    """Analisa o texto do briefing e os arquivos da pasta para deduzir a `ProductRoute`.

    Ordem de precedência determinística:
    1. `route_override` explícito (ex: `--route upscale_only`).
    2. Briefing JSON estruturado com chave `route` ou formato específico (`MugInput` / `CardInput`).
    3. Indicadores de `MUG_11OZ` (caneca, mug, 11oz, 325ml, sublimação).
    4. Indicadores explícitos de `UPSCALE_ONLY` (apenas upscale, só upscale, upscale_only, sem folha).
    5. Indicadores de `POSTER_FULL` (poster, pôster, quadro, a3, a4, 210x300, 300x420).
    6. Indicadores de `CARD_TCG` (carta, card, tcg, yugioh, pokemon, magic, one piece, frente/verso, fundo.jpg).
    7. Heurística por arquivos presentes na pasta (se houver `fundo.jpg`/`verso` ou briefing de carta -> `CARD_TCG`;
       se houver apenas foto única sem verso e sem briefing -> `POSTER_FULL`).
    """
    if route_override is not None:
        return normalize_product_route(route_override)

    dir_path = Path(order_dir)
    text = briefing_text if briefing_text is not None else read_order_briefing_text(dir_path)
    text_lower = text.lower()

    files_list: List[Path]
    if customer_files is not None:
        files_list = [Path(p) for p in customer_files]
    elif dir_path.is_dir():
        files_list = [p for p in sorted(dir_path.iterdir()) if p.is_file()]
    else:
        files_list = []

    filenames_lower = " ".join(p.name.lower() for p in files_list)
    combined = f"{text_lower} {filenames_lower}".strip()

    # Verifica se há JSON estruturado indicando rota, caneca ou carta
    for f_path in files_list:
        if f_path.suffix.lower() == ".json" and not is_generated_artifact(f_path) and f_path.is_file():
            try:
                payload = json.loads(f_path.read_text(encoding="utf-8"))
                first_item = payload[0] if isinstance(payload, list) and payload else payload
                if isinstance(first_item, dict):
                    if "route" in first_item:
                        return normalize_product_route(str(first_item["route"]))
                    if "tema" in first_item or "espelhar_transfer" in first_item:
                        return ProductRoute.MUG_11OZ
                    if "tipo" in first_item and "titulo" in first_item:
                        return ProductRoute.CARD_TCG
            except Exception:
                pass

    # 1. Rota MUG_11OZ
    mug_keywords = (
        "caneca",
        "mug",
        "11oz",
        "325ml",
        "sublimacao",
        "sublimação",
        "220x95",
        "2598x1122",
    )
    if any(kw in combined for kw in mug_keywords):
        return ProductRoute.MUG_11OZ

    # 2. Rota UPSCALE_ONLY (explícita no texto ou nome de arquivo sem folha)
    upscale_only_keywords = (
        "upscale_only",
        "apenas upscale",
        "apenas upscaling",
        "somente upscale",
        "somente upscaling",
        "só upscale",
        "so upscale",
        "sem folha",
        "sem imposição",
        "sem imposicao",
        "apenas ampliar",
    )
    if any(kw in combined for kw in upscale_only_keywords):
        return ProductRoute.UPSCALE_ONLY

    # Regras específicas de pedidos reais Studio Kustom:
    dir_name = dir_path.name.strip().lower()
    order_id_num = dir_name.split("-")[0].strip()

    # Regra do Pedido 174: Mapear explicitamente para "Magic" (CARD_TCG)
    # Regra do Pedido 165 (Pokémon): Detectar foto.jpg e mapear como CARD_TCG
    if order_id_num in ("174", "165"):
        return ProductRoute.CARD_TCG

    # 3. Rota POSTER_FULL vs CARD_TCG
    card_keywords = (
        "carta",
        "cartas",
        "card",
        "cards",
        "tcg",
        "yugioh",
        "yu-gi-oh",
        "pokemon",
        "pokémon",
        "magic",
        "mtg",
        "one piece",
        "onepiece",
        "armadilha",
        "feitiço",
        "feitico",
        "monstro",
        "super a4",
        "super_a4",
        "3x3",
        "duplex",
    )
    has_back_file = any(is_back_image(p) for p in files_list)
    has_front_back_pair = any("frente" in p.stem.lower() for p in files_list) and any(
        "verso" in p.stem.lower() for p in files_list
    )

    if has_back_file or has_front_back_pair or any(kw in text_lower for kw in card_keywords):
        return ProductRoute.CARD_TCG

    poster_keywords = (
        "poster",
        "pôster",
        "quadro",
        "a3_v",
        "a3_h",
        "a4_v",
        "a4_h",
        "210x300",
        "300x420",
        "a3",
        "a4",
    )
    if any(re.search(rf"\b{re.escape(kw)}\b", combined) for kw in poster_keywords) or (
        "poster_" in filenames_lower
    ):
        return ProductRoute.POSTER_FULL

    if any(kw in filenames_lower for kw in card_keywords):
        return ProductRoute.CARD_TCG

    # Se houver múltiplas imagens de cartas (>= 4 imagens) ou texto de briefing genérico -> CARD_TCG
    image_files = [
        p
        for p in files_list
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} and not is_generated_artifact(p)
    ]
    if text_lower or len(image_files) >= 4:
        return ProductRoute.CARD_TCG

    # Caso padrão para fotos isoladas sem verso e sem briefing de carta: POSTER_FULL
    return ProductRoute.POSTER_FULL


def parse_card_input_from_order(
    order_dir: Union[str, Path],
    briefing_text: Optional[str] = None,
    reference_photos: Optional[Sequence[Path]] = None,
) -> CardInput:
    """Extrai um `CardInput` validado a partir de um JSON ou texto livre (`texto.txt`) do pedido."""
    dir_path = Path(order_dir)
    order_id_num = dir_path.name.split("-")[0].strip().lower()

    # 1. Tenta carregar diretamente de um arquivo .json na pasta, se existir
    if dir_path.is_dir():
        for item in sorted(dir_path.iterdir()):
            if item.is_file() and item.suffix.lower() == ".json" and not is_generated_artifact(item):
                try:
                    raw = json.loads(item.read_text(encoding="utf-8"))
                    first = raw[0] if isinstance(raw, list) and raw else raw
                    if isinstance(first, dict) and "titulo" in first:
                        return CardInput.model_validate(first)
                except Exception:
                    pass

    text = briefing_text if briefing_text is not None else read_order_briefing_text(dir_path)
    text_lower = text.lower()

    # Identifica se há foto.jpg na pasta ou nas fotos de referência (Regra Pedido 165 / Pokémon)
    foto_file: Optional[Path] = None
    if reference_photos:
        for p in reference_photos:
            p_obj = Path(p)
            if p_obj.is_file() and p_obj.name.lower() in ("foto.jpg", "foto.jpeg", "foto.png"):
                foto_file = p_obj
                break
    if foto_file is None and dir_path.is_dir():
        for item in sorted(dir_path.iterdir()):
            if (
                item.is_file()
                and item.name.lower() in ("foto.jpg", "foto.jpeg", "foto.png")
                and not is_generated_artifact(item)
            ):
                foto_file = item
                break

    # Deduz jogo/tipo
    # Regra do Pedido 174: Mapear explicitamente para "Magic"
    if order_id_num == "174" or any(k in text_lower for k in ("magic", "mtg", "mana", "planeswalker")):
        tipo = "Magic"
    elif any(k in text_lower for k in ("yugioh", "yu-gi-oh", "armadilha", "magia", "turno")):
        tipo = "Yu-Gi-Oh!"
    elif any(k in text_lower for k in ("one piece", "onepiece", "bounty", "pirata")):
        tipo = "One Piece"
    elif order_id_num == "165" or foto_file is not None or any(k in text_lower for k in ("pokemon", "pokémon", "pikachu")):
        tipo = "Pokemon"
    else:
        tipo = "Pokemon"

    # Deduz estilo
    if any(k in text_lower for k in ("fullart", "full art", "full-art")):
        estilo = "Fullart"
    elif any(k in text_lower for k in ("alternative", "alternativa")):
        estilo = "Alternative"
    else:
        estilo = "Normal"

    # Extrai título entre aspas ou primeira linha útil
    if order_id_num == "174" and not text.strip():
        titulo = f"Carta Magic Pedido {dir_path.name}"
    elif (order_id_num == "165" or foto_file is not None) and not text.strip():
        titulo = f"Carta Pokémon Pedido {dir_path.name}"
    else:
        titulo = f"Carta Pedido {dir_path.name}"
        quote_match = re.search(r'[“"«]([^”"»\n]{2,80})[”"»]', text)
        if quote_match:
            titulo = quote_match.group(1).strip()
        elif text.strip():
            first_line = text.strip().splitlines()[0].strip()
            if len(first_line) <= 60:
                titulo = first_line

    # Regra do Pedido 165 (Pokémon): Preservação da foto original sem deformação
    is_order_165_or_foto = order_id_num == "165" or (foto_file is not None and tipo == "Pokemon")
    if is_order_165_or_foto:
        preservation_clause = "com preservação da foto original sem deformação"
        if not text.strip():
            descricao = f"Arte da carta Pokémon do pedido {dir_path.name} {preservation_clause}."
        elif "sem deforma" not in text_lower and "preserva" not in text_lower:
            descricao = f"{text.strip()} ({preservation_clause})"
        else:
            descricao = text.strip()
    elif order_id_num == "174" and not text.strip():
        descricao = f"Arte personalizada da carta Magic: The Gathering do pedido {dir_path.name}"
    else:
        descricao = text.strip() if text.strip() else f"Arte personalizada do pedido {dir_path.name}"

    # Monta referências de imagem priorizando foto.jpg
    valid_refs: Optional[List[str]] = None
    existing_refs: List[Path] = []
    if reference_photos:
        existing_refs = [Path(p).resolve() for p in reference_photos if Path(p).is_file()]
    elif dir_path.is_dir():
        image_exts = {".jpg", ".jpeg", ".png", ".webp"}
        existing_refs = [
            p.resolve()
            for p in sorted(dir_path.iterdir())
            if p.is_file() and p.suffix.lower() in image_exts and not is_generated_artifact(p) and not is_back_image(p)
        ]

    if foto_file is not None and foto_file.is_file():
        foto_res = foto_file.resolve()
        ordered = [str(foto_res)] + [str(p) for p in existing_refs if p != foto_res]
        valid_refs = ordered if ordered else None
    elif existing_refs:
        valid_refs = [str(p) for p in existing_refs]

    return CardInput(
        tipo=tipo,
        estilo=estilo,
        titulo=titulo,
        descricao=descricao,
        imagens_referencia=valid_refs,
    )


def parse_mug_input_from_order(
    order_dir: Union[str, Path],
    briefing_text: Optional[str] = None,
    reference_photos: Optional[Sequence[Path]] = None,
) -> Optional[MugInput]:
    """Tenta carregar um `MugInput` se houver arquivo JSON de caneca na pasta do pedido."""
    dir_path = Path(order_dir)
    if dir_path.is_dir():
        for item in sorted(dir_path.iterdir()):
            if item.is_file() and item.suffix.lower() == ".json" and not is_generated_artifact(item):
                try:
                    raw = json.loads(item.read_text(encoding="utf-8"))
                    first = raw[0] if isinstance(raw, list) and raw else raw
                    if isinstance(first, dict) and ("tema" in first or "espelhar_transfer" in first):
                        return MugInput.model_validate(first)
                except Exception:
                    pass
    return None


__all__ = [
    "BACK_IMAGE_KEYWORDS",
    "GENERATED_FILE_PATTERNS",
    "ParsedOrderContext",
    "deduce_product_route",
    "infer_poster_format",
    "is_back_image",
    "is_generated_artifact",
    "parse_card_input_from_order",
    "parse_mug_input_from_order",
    "read_order_briefing_text",
]
