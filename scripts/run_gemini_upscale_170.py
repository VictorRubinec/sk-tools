"""Executa o upscaling no Gemini da arte original do Pedido 170 sem esticar o rosto."""

from __future__ import annotations

import io
import sys
from pathlib import Path
from PIL import Image, ImageOps, ImageFilter
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from tools.card_generator.browser.gemini_client import GeminiClient
from tools.card_generator.browser.session import get_chrome_context
from tools.card_generator.core.config import DEFAULT_CONFIG
from tools.card_generator.core.logger import logger, setup_logger
from tools.upscaler.validator import PosterImageValidator
from tools.print_sheet.pdf_builder import render_poster_sheet_image, save_pages_to_pdf

ORDER_DIR = Path(r"D:\Desktop\Studio Kustom\04 - Pedidos e Historico\Pedidos\170")
ORIGINAL_PATH = ORDER_DIR / "poster_170_original.png"
ROOT = Path(r"D:\Desktop\Studio Kustom\04 - Pedidos e Historico\Pedidos")


def prepare_balanced_reference_image(src_path: Path) -> Path:
    """Prepara a imagem de referência com proporção 1.400 (A3) estendendo o fundo escuro suavemente no topo e base para evitar qualquer estiramento do rosto pelo Gemini."""
    with Image.open(src_path) as im:
        rgb = im.convert("RGB")
        w, h = rgb.size
        # Proporção A3 exata: h / w = 4960 / 3543 = 1.39994
        target_h = int(round(w * (4960 / 3543)))
        diff_h = target_h - h
        pad_top = diff_h // 2
        pad_bottom = diff_h - pad_top

        arr = np.array(rgb)
        # Pad superior e inferior com continuidade de borda (escuro)
        padded_arr = np.pad(arr, ((pad_top, pad_bottom), (0, 0), (0, 0)), mode="edge")
        ref_im = Image.fromarray(padded_arr)

        ref_path = ORDER_DIR / "poster_170_ref_proportional.png"
        ref_im.save(ref_path, format="PNG")
        logger.info(
            "Imagem de referência proporcional preparada: {} ({}x{}px, ratio={:.3f})",
            ref_path.name,
            ref_im.width,
            ref_im.height,
            ref_im.height / ref_im.width,
        )
        return ref_path


def main():
    setup_logger(console_level="INFO", log_to_file=True)
    logger.info("Iniciando upscaling oficial via Gemini para o Pedido 170...")

    ref_path = prepare_balanced_reference_image(ORIGINAL_PATH)

    prompt_text = (
        "[PAPEL DA IA]\n"
        "Você é um artista digital sênior especialista em restauração, pintura fine-art, redraw em altíssima "
        "definição e super-resolução para impressão gráfica profissional (300 DPI) do estúdio Studio Kustom.\n\n"
        "[INSTRUÇÃO PRINCIPAL DE REDRAW E SUPER-RESOLUÇÃO]\n"
        "Realize o redraw e upscaling de altíssima definição da ilustração de terror anexa (A Freira / Valak) "
        "para o formato de pôster A3 Vertical (300 DPI, proporção exata de pôster vertical).\n\n"
        "[REGRA CRÍTICA DE PROPORÇÃO FACIAL - NÃO ESTICAR]\n"
        "- MANTENHA A PROPORÇÃO ANATÔMICA EXATA DO ROSTO DA PERSONAGEM. O rosto NÃO PODE ser esticado, "
        "alongado verticalmente nem comprimido horizontalmente. As maçãs do rosto, olhos amarelos brilhantes, "
        "nariz, boca e queixo devem manter rigorosamente o mesmo formato e largura da imagem original.\n"
        "- Preserve a fisionomia, rugas profundas, veias escuras e a expressão aterrorizante idêntica à referência.\n"
        "- O hábito preto, o capuz branco, a cruz e o cordão no peito devem ser renderizados com texturas de tecido "
        "realistas e iluminação dramática.\n\n"
        "[QUALIDADE E ACABAMENTO]\n"
        "- Linhas super nítidas, textura de pintura a óleo de alta definição, acabamento cinematográfico 8K.\n"
        "- Preenchimento harmonioso de todo o pôster sem barras pretas artificiais nem pillarboxing."
    )

    config = DEFAULT_CONFIG
    shared_context = get_chrome_context(config)

    try:
        page = shared_context.pages[0] if shared_context.pages else shared_context.new_page()
        page.goto(config.gemini_url, wait_until="domcontentloaded")

        gemini_client = GeminiClient()
        if not gemini_client.check_login_status(page):
            raise RuntimeError("Sessão do Gemini não autenticada.")

        logger.info("Enviando prompt e imagem de referência ao Gemini...")
        gemini_client.send_prompt(page, prompt_text, submit=False)
        gemini_client.upload_reference_images(page, [ref_path])
        gemini_client.submit_prompt(page)

        logger.info("Aguardando geração da imagem pelo Gemini...")
        gemini_client.wait_for_generation_complete(page, timeout_ms=config.timeout_ms)

        logger.info("Extraindo binário da imagem gerada pelo Gemini...")
        raw_bytes = gemini_client.extract_latest_generated_image(page)
        if not raw_bytes:
            raise RuntimeError("Nenhum binário de imagem retornado pelo Gemini.")

        # Validação e conformação
        validator = PosterImageValidator()
        conformed_bytes = validator.conform_to_poster_spec(raw_bytes, "A3_V")
        val_result = validator.validate_poster(conformed_bytes, "A3_V")

        out_poster_path = ORDER_DIR / "poster_170_A3_300dpi_poster_a3_v.png"
        out_poster_path.write_bytes(conformed_bytes)
        logger.success("Pôster A3_V gerado pelo Gemini salvo em: '{}'", out_poster_path)

        # Adiciona 5mm de sangria (+59px por borda)
        with Image.open(out_poster_path) as up_img:
            arr = np.array(up_img.convert("RGB"))
            pad_arr = np.pad(arr, ((59, 59), (59, 59), (0, 0)), mode="edge")
            exp_img = Image.fromarray(pad_arr)
            out_exp_path = ORDER_DIR / "poster_170_A3_300dpi_poster_a3_v_expanded.png"
            exp_img.save(out_exp_path, format="PNG", dpi=(300, 300))
            logger.success("Sangria de 5mm aplicada com sucesso em: '{}'", out_exp_path)

    finally:
        shared_context.close()

    # Recompila os PDFs
    logger.info("Recompilando PDFs com a nova arte upscaled pelo Gemini...")
    import scripts.build_poster_batch_sheets as batch_script
    batch_script.main()
    logger.success("Processo completo concluído com sucesso!")


if __name__ == "__main__":
    main()
