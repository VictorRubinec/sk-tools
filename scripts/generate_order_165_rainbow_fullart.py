"""Gera carta Pokémon FullArt com bordas arco-íris e tema Casal para o Pedido 165."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from tools.card_generator.browser.orchestrator import generate_card_image
from tools.card_generator.browser.session import get_chrome_context
from tools.card_generator.core.config import DEFAULT_CONFIG, AppConfig
from tools.card_generator.core.logger import logger, setup_logger
from tools.card_generator.core.schema import CardInput

ORDER_DIR = Path(r"D:\Desktop\Studio Kustom\04 - Pedidos e Historico\Pedidos\165")
FOTO_PATH = ORDER_DIR / "foto.jpg"

CARD_RAINBOW_COUPLE = CardInput(
    titulo="Power Couple VMAX",
    tipo="Pokemon",
    estilo="Fullart",
    descricao=(
        "Carta colecionável oficial Pokémon TCG de Edição Especial Secreta 'Rainbow Rare / Hyper Rare VMAX' no estilo Full Art. "
        "A arte da carta deve ser inspirada no tema CASAL e AMOR, utilizando a imagem de referência anexa ('foto.jpg') para representar "
        "o casal de forma carinhosa, radiante e apaixonada, preservando a fisionomia e rostos originais em estilo anime/Pokémon refinado. "
        "A composição é FULL ART (arte de ponta a ponta sem bordas limitantes pretas), com acabamento holográfico prismático de "
        "BORDAS ARCO-ÍRIS (Rainbow Rare), com suave textura furta-cor iridescente (degradê pastel de arco-íris: rosa, ciano, lilás, dourado e verde menta) "
        "ao redor da carta e sobre os detalhes da moldura VMAX."
    ),
    texto_adicional=(
        "HP 320 | Pokémon VMAX - Casal Lendário\n"
        "Habilidade: Conexão Infinita - O amor e a cumplicidade deste casal aumentam a cada turno.\n"
        "Ataque: Amor Lendário 300+ - Este ataque celebra momentos inesquecíveis e felicidade eterna.\n"
        "Regra VMAX: Quando o casal está unido, nada pode separá-los."
    ),
    cores=["Arco-íris", "Prismático", "Holográfico", "Dourado"],
    imagens_referencia=[str(FOTO_PATH)],
)


def main():
    setup_logger(console_level="INFO", log_to_file=True)
    logger.info("Iniciando geração da carta Pokémon FullArt Rainbow para o Pedido 165...")

    config = replace(DEFAULT_CONFIG, output_dir=ORDER_DIR)
    shared_context = get_chrome_context(config)

    try:
        out_path = generate_card_image(CARD_RAINBOW_COUPLE, config=config, context=shared_context)
        logger.success("Carta Pokémon FullArt Rainbow gerada em: '{}'", out_path)
    finally:
        shared_context.close()

    logger.success("Geração concluída com sucesso!")


if __name__ == "__main__":
    main()
