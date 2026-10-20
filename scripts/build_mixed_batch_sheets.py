"""Monta e compila as 12 folhas Super A4 duplex com imposição mista das 105 cartas."""

from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from tools.print_sheet.pdf_builder import build_card_sheet_pdf
from tools.card_generator.core.logger import logger, setup_logger

ROOT = Path(r"D:\Desktop\Studio Kustom\04 - Pedidos e Historico\Pedidos")
BACKS_DIR = Path("input/card_backs")


def gather_cards_and_backs() -> tuple[list[Path], list[Path], dict[str, tuple[list[Path], list[Path]]]]:
    orders: dict[str, tuple[list[Path], list[Path]]] = {}

    # 1. Pedido 163: 77 cartas
    p163 = ROOT / "163"
    f_163 = sorted([
        p for p in p163.iterdir()
        if p.suffix.lower() in (".png", ".jpg")
        and not p.name.startswith(("Verso", "pedido_"))
        and not p.name.endswith("_expanded.png")
    ])
    b_163 = [p163 / "VersoPadrão_expanded.png"] * len(f_163)
    orders["163"] = (f_163, b_163)

    # 2. Pedido 164: 2 cartas
    p164 = ROOT / "164"
    f_164 = [
        p164 / "magic_criatura_lendaria_humano.png",
        p164 / "magic_parceiro_de_todas_as_jornadas.png",
    ]
    b_164 = [p164 / "fundo_expanded.png"] * len(f_164)
    orders["164"] = (f_164, b_164)

    # 3. Pedido 165: 8 cartas (2x cada uma das 4 cartas)
    p165 = ROOT / "165"
    c1 = p165 / "carta1_63x88_300dpi.png"
    c2 = p165 / "carta2_63x88_300dpi.png"
    c3 = p165 / "carta3_63x88_300dpi.png"
    cr = p165 / "pokemon_power_couple_vmax_upscaled_300dpi.png"
    f_165 = [c1, c1, c2, c2, c3, c3, cr, cr]
    b_165 = [BACKS_DIR / "pokemon.png"] * len(f_165)
    orders["165"] = (f_165, b_165)

    # 4. Pedido 167: 10 cartas com versos expandidos pareados 1:1
    p167 = ROOT / "167"
    pairs_167 = [
        (p167 / "BARONESS FRENTE 01.jpg", p167 / "BARONESS VERSO_expanded.png"),
        (p167 / "BARONESS FRENTE 02.jpg", p167 / "BARONESS VERSO_expanded.png"),
        (p167 / "BRIGHT FRENTE.png", p167 / "BRIGHT VERSO_expanded.png"),
        (p167 / "COBRA EEL FRENTE.jpg", p167 / "COBRA EEL VERSO_expanded.png"),
        (p167 / "COVER GIRL FRENTE.jpg", p167 / "COVER GIRL VERSO_expanded.png"),
        (p167 / "GELEIA FRENTE.png", p167 / "GELEIA VERSO_expanded.png"),
        (p167 / "HYDRO-VIPER FRENTE.jpg", p167 / "HYDRO-VIPER VERSO_expanded.png"),
        (p167 / "LOTSA FRENTE.png", p167 / "LOTSA VERSO_expanded.png"),
        (p167 / "SCARLETT FRENTE 01.jpg", p167 / "SCARLETT VERSO_expanded.png"),
        (p167 / "SCARLETT FRENTE 02.jpg", p167 / "SCARLETT VERSO_expanded.png"),
    ]
    f_167 = [f for f, _ in pairs_167]
    b_167 = [b for _, b in pairs_167]
    orders["167"] = (f_167, b_167)

    # 5. Pedido 169: 3 cartas
    p169 = ROOT / "169"
    f_169 = [
        p169 / "1_upscaled_300dpi.png",
        p169 / "2_upscaled_300dpi.png",
        p169 / "3_upscaled_300dpi.png",
    ]
    b_169 = [p169 / "fundo_expanded.png"] * len(f_169)
    orders["169"] = (f_169, b_169)

    # 6. Pedido 171: 1 carta
    p171 = ROOT / "171"
    f_171 = [p171 / "br-11134231-820lr-mudfcmzls3ya41_upscaled_300dpi.png"]
    b_171 = [p171 / "fundo_expanded.png"] * len(f_171)
    orders["171"] = (f_171, b_171)

    # 7. Pedido 174: 3 cartas Magic
    p174 = ROOT / "174"
    f_174 = [
        p174 / "br-11134231-820lk-mudj9e8jf6yo90_upscaled_300dpi.png",
        p174 / "br-11134231-820lu-mudj9e8jglj4f9_upscaled_300dpi.png",
        p174 / "Captura de tela 2026-10-19 103159_upscaled_300dpi.png",
    ]
    b_174 = [BACKS_DIR / "magic.png"] * len(f_174)
    orders["174"] = (f_174, b_174)

    # 8. Pedido 176: 1 carta Yu-Gi-Oh!
    p176 = ROOT / "176"
    f_176 = [p176 / "yu_gi_oh_laco_do_amor_eterno.png"]
    b_176 = [BACKS_DIR / "yugioh.png"] * len(f_176)
    orders["176"] = (f_176, b_176)

    fronts: list[Path] = []
    backs: list[Path] = []
    for f_list, b_list in orders.values():
        fronts.extend(f_list)
        backs.extend(b_list)

    return fronts, backs, orders


def main():
    setup_logger(console_level="INFO", log_to_file=True)
    logger.info("Iniciando compilação do lote consolidado de folhas mistas Super A4...")

    fronts, backs, orders = gather_cards_and_backs()
    logger.info("Total de cartas a impor: {} frentes e {} versos.", len(fronts), len(backs))
    assert len(fronts) == len(backs) == 105, f"Esperado 105 cartas, obtido {len(fronts)}"

    # 1. Gera o PDF Consolidado Geral da Produção (12 folhas / 24 páginas duplex)
    output_master_pdf = ROOT / "impressao_lote_completo_105_cartas_super_a4.pdf"
    logger.info("Gerando Master PDF com fundos expandidos: '{}'...", output_master_pdf.name)

    pdf_path = build_card_sheet_pdf(
        front_images=fronts,
        back_image=backs,
        paper="super_a4",
        output_pdf=output_master_pdf,
        draw_marks=True,
    )
    logger.success("Master PDF gerado com sucesso em: '{}'", pdf_path)

    # 2. Gera/Atualiza os PDFs individuais de todos os pedidos usando os fundos expandidos corretos
    for oid, (f_list, b_list) in orders.items():
        out_ind = ROOT / oid / f"pedido_{oid}_cards_super_a4.pdf"
        build_card_sheet_pdf(
            front_images=f_list,
            back_image=b_list,
            paper="super_a4",
            output_pdf=out_ind,
            draw_marks=True,
        )
        logger.success("[Pedido {}] PDF individual atualizado: '{}'", oid, out_ind.name)

    logger.success("Todos os PDFs de produção foram compilados com sucesso!")


if __name__ == "__main__":
    main()
