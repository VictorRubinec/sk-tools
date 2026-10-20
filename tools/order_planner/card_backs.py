"""Mapeamento e resolução de fundos oficiais com sangria técnica para cartas TCG (tools/order_planner/card_backs.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Final, Optional, Union

from tools.card_generator.core.config import INPUT_DIR

DEFAULT_CARD_BACKS_DIR: Final[Path] = INPUT_DIR / "card_backs"

# Mapeamento canônico de jogos para os nomes dos arquivos oficiais com sangria
OFFICIAL_CARD_BACKS_MAP: Final[Dict[str, str]] = {
    # Magic: The Gathering
    "magic": "magic.png",
    "mtg": "magic.png",
    "magic: the gathering": "magic.png",
    "magic the gathering": "magic.png",
    # Pokémon TCG
    "pokemon": "pokemon.png",
    "pokémon": "pokemon.png",
    "pokemon tcg": "pokemon.png",
    "pokémon tcg": "pokemon.png",
    "poke": "pokemon.png",
    # Yu-Gi-Oh!
    "yugioh": "yugioh.png",
    "yu-gi-oh": "yugioh.png",
    "yu-gi-oh!": "yugioh.png",
    "yu gi oh": "yugioh.png",
    "yugi": "yugioh.png",
    # One Piece
    "onepiece": "onepiece.png",
    "one piece": "onepiece.png",
    "one-piece": "onepiece.png",
    "op": "onepiece.png",
    "optcg": "onepiece.png",
    # Studio Kustom Institucional
    "studio_kustom": "studio_kustom.png",
    "studio kustom": "studio_kustom.png",
    "studiokustom": "studio_kustom.png",
    "kustom": "studio_kustom.png",
    "institucional": "studio_kustom.png",
    # Studio Kustom P&B
    "studio_kustom_pb": "studio_kustom_pb.png",
    "studio kustom pb": "studio_kustom_pb.png",
    "pb": "studio_kustom_pb.png",
    "p&b": "studio_kustom_pb.png",
    "bw": "studio_kustom_pb.png",
}

DEFAULT_FALLBACK_FILENAME: Final[str] = "studio_kustom.png"
SECONDARY_FALLBACK_FILENAME: Final[str] = "VersoPadrao.png"


def resolve_card_back_by_game(
    game_type: Optional[str] = None,
    custom_back_path: Optional[Union[str, Path]] = None,
    card_backs_dir: Optional[Union[str, Path]] = None,
) -> Path:
    """Resolve o caminho da imagem de verso (fundo) de carta com sangria técnica.

    Regras de precedência:
    1. Se `custom_back_path` for fornecido e existir em disco (ex: `fundo.jpg` na pasta do pedido), prioriza-o.
    2. Caso contrário, resolve automaticamente para o fundo oficial da marca com sangria
       (`magic.png`, `pokemon.png`, `yugioh.png`, `onepiece.png`).
    3. Fallback seguro para `studio_kustom.png` ou `VersoPadrao.png`.

    Args:
        game_type: Nome ou identificador do jogo/sistema de cartas (ex: 'Magic', 'Pokemon', 'Yu-Gi-Oh!', 'One Piece').
        custom_back_path: Caminho opcional para arquivo de verso personalizado pelo cliente.
        card_backs_dir: Diretório raiz dos fundos oficiais (padrão: `input/card_backs`).

    Returns:
        `Path` absoluto do arquivo de verso validado.
    """
    if custom_back_path is not None:
        p = Path(custom_back_path)
        if p.is_file():
            return p.resolve()

    base_dir = Path(card_backs_dir) if card_backs_dir is not None else DEFAULT_CARD_BACKS_DIR

    # Tenta resolução por game_type
    target_filename: Optional[str] = None
    if game_type and isinstance(game_type, str):
        cleaned_key = game_type.strip().lower()
        target_filename = OFFICIAL_CARD_BACKS_MAP.get(cleaned_key)
        if target_filename is None:
            for k, fname in OFFICIAL_CARD_BACKS_MAP.items():
                if k in cleaned_key:
                    target_filename = fname
                    break

    if target_filename:
        brand_path = base_dir / target_filename
        if brand_path.is_file():
            return brand_path.resolve()

    # Fallback seguro: studio_kustom.png ou VersoPadrao.png
    primary_fallback = base_dir / DEFAULT_FALLBACK_FILENAME
    if primary_fallback.is_file():
        return primary_fallback.resolve()

    secondary_fallback = base_dir / SECONDARY_FALLBACK_FILENAME
    if secondary_fallback.is_file():
        return secondary_fallback.resolve()

    # Se nenhum existir fisicamente em disco no card_backs_dir especificado,
    # retorna o caminho canônico esperado
    if target_filename:
        return (base_dir / target_filename).resolve()
    return primary_fallback.resolve()


__all__ = [
    "DEFAULT_CARD_BACKS_DIR",
    "DEFAULT_FALLBACK_FILENAME",
    "OFFICIAL_CARD_BACKS_MAP",
    "SECONDARY_FALLBACK_FILENAME",
    "resolve_card_back_by_game",
]
