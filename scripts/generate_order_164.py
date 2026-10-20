"""Gera as 2 cartas do Pedido 164 via Gemini com as fotos e descrições fornecidas."""

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

ORDER_DIR = Path(r"D:\Desktop\Studio Kustom\04 - Pedidos e Historico\Pedidos\164")

CARD_1 = CardInput(
    titulo="Criatura Lendária - Humano",
    tipo="Magic",
    estilo="Normal",
    descricao=(
        "Carta colecionável temática estilo Magic: The Gathering. "
        "Utilize a imagem de referência anexa ('foto1.jpg') como a arte da janela de ilustração central "
        "da carta mantendo a foto intacta sem distorção anatômica. "
        "Crie a moldura autêntica de Magic ao redor com bordas elegantes, caixa de texto legível e acabamento premium."
    ),
    texto_adicional=(
        "Quando entra em campo, você ganha +100 de felicidade e um beijo meu. "
        "Enquanto estivermos longe, recebe uma mensagem de saudade por turno. "
        "Fraqueza: quando eu estou perto explodimos de ódio ou de amor.\n"
        "\"Mesmo a distância, você continua sendo a minha melhor jogada.\"\n"
        "EDIÇÃO ESPECIAL 2/2 - CRIADO COM AMOR"
    ),
    imagens_referencia=[str(ORDER_DIR / "foto1.jpg")],
)

CARD_2 = CardInput(
    titulo="Parceiro de Todas as Jornadas",
    tipo="Magic",
    estilo="Normal",
    descricao=(
        "Carta colecionável temática estilo Magic: The Gathering. "
        "Utilize a imagem de referência anexa ('foto2.jpg') como a arte da janela de ilustração central "
        "da carta mantendo a foto intacta sem distorção anatômica. "
        "Crie a moldura autêntica de Magic ao redor com bordas elegantes, caixa de texto legível e acabamento premium."
    ),
    texto_adicional=(
        "Companheirismo Infinito: Mesmo de longe, você sempre está presente. Com uma mensagem, uma risada ou um simples 'eu te amo', você torna tudo mais leve.\n"
        "Aventureiro da Vida Real: Você topa os planos malucos, coleciona memórias e transforma o extraordinário em algo especial.\n"
        "\"Não importa a distância, o caos ou o tempo, você sempre será o meu lugar seguro.\"\n"
        "EDIÇÃO ESPECIAL 2/2 - CRIADO COM AMOR"
    ),
    imagens_referencia=[str(ORDER_DIR / "foto2.jpg")],
)


def main():
    setup_logger(console_level="INFO", log_to_file=True)
    logger.info("Iniciando geração das 2 cartas do Pedido 164...")

    config = replace(DEFAULT_CONFIG, output_dir=ORDER_DIR)
    shared_context = get_chrome_context(config)

    cards = [("Carta 1 (foto1 + desc1)", CARD_1), ("Carta 2 (foto2 + desc2)", CARD_2)]

    try:
        for idx, (label, card_input) in enumerate(cards, start=1):
            logger.info("[{}/2] Gerando {}...", idx, label)
            out_path = generate_card_image(card_input, config=config, context=shared_context)
            logger.success("[{}/2] {} gerada em: '{}'", idx, label, out_path)
    finally:
        shared_context.close()

    logger.success("Geração do Pedido 164 concluída!")


if __name__ == "__main__":
    main()
