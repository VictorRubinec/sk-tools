"""Gera a carta Pokémon com template limpo/vazio e a foto.jpg para o Pedido 165."""

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

CARD_POKEMON = CardInput(
    titulo="Carta Pokemon",
    tipo="Pokemon",
    estilo="Normal",
    descricao=(
        "Carta colecionável autêntica de Pokémon TCG com a moldura e layout oficial de Pokémon. "
        "A imagem de referência anexa ('foto.jpg') DEVE ser utilizada como a foto da arte na janela de ilustração da carta, "
        "preservando fielmente a fisionomia, iluminação e enquadramento da foto sem deformação. "
        "A caixa de texto inferior de regras/habilidades deve ser VAZIA e limpa (template em branco de carta Pokémon, "
        "sem textos, letras inventadas ou alucinações de tipografia pela IA)."
    ),
    texto_adicional="",
    imagens_referencia=[str(FOTO_PATH)],
)


def main():
    setup_logger(console_level="INFO", log_to_file=True)
    logger.info("Iniciando geração da carta Pokémon vazia com a foto.jpg para o Pedido 165...")

    config = replace(DEFAULT_CONFIG, output_dir=ORDER_DIR)
    shared_context = get_chrome_context(config)

    try:
        out_path = generate_card_image(CARD_POKEMON, config=config, context=shared_context)
        logger.success("Carta Pokémon gerada em: '{}'", out_path)
    finally:
        shared_context.close()

    logger.success("Geração da carta Pokémon concluída!")


if __name__ == "__main__":
    main()
