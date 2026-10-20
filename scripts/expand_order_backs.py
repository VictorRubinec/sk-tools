"""Script de automação para expansão de fundos dos pedidos 163, 164, 167, 169 e 171."""

from __future__ import annotations

import sys
from pathlib import Path

# Adiciona o diretório raiz ao path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from tools.background_expander.orchestrator import run_background_expansion_orchestration
from tools.background_expander.validator import ExpandedImageValidator
from tools.card_generator.browser.session import get_chrome_context
from tools.card_generator.core.config import AppConfig, DEFAULT_CONFIG
from tools.card_generator.core.logger import logger, setup_logger


from dataclasses import replace

TARGET_ORDERS_AND_FILES = [
    ("163", ["VersoPadrão.png"]),
    ("164", ["fundo.jpg"]),
    ("167", [
        "BARONESS VERSO.jpg",
        "BRIGHT VERSO.png",
        "COBRA EEL VERSO.jpg",
        "COVER GIRL VERSO.jpg",
        "GELEIA VERSO.png",
        "HYDRO-VIPER VERSO.jpg",
        "LOTSA VERSO.png",
        "SCARLETT VERSO.jpg",
    ]),
    ("169", ["fundo.jpg"]),
    ("171", ["fundo.jpg"]),
]

ORDERS_ROOT = Path(r"D:\Desktop\Studio Kustom\04 - Pedidos e Historico\Pedidos")


def main() -> int:
    setup_logger(console_level="INFO", log_to_file=True)
    logger.info("Iniciando expansão de fundos dos pedidos: 163, 164, 167, 169, 171...")

    validator = ExpandedImageValidator()
    config = DEFAULT_CONFIG
    shared_context = get_chrome_context(config)

    total_files = sum(len(files) for _, files in TARGET_ORDERS_AND_FILES)
    processed = 0
    succeeded = 0
    failed = 0

    try:
        for order_id, filenames in TARGET_ORDERS_AND_FILES:
            order_dir = ORDERS_ROOT / order_id
            if not order_dir.is_dir():
                logger.error("[Pedido {}] Diretório não encontrado: {}", order_id, order_dir)
                failed += len(filenames)
                continue

            order_cfg = replace(config, output_dir=order_dir)

            for filename in filenames:
                processed += 1
                source_file = order_dir / filename
                if not source_file.is_file():
                    logger.error("[Pedido {}] Arquivo de fundo não encontrado: {}", order_id, source_file)
                    failed += 1
                    continue

                expanded_target = order_dir / f"{source_file.stem}_expanded.png"
                if expanded_target.is_file():
                    # Verifica se já está válido
                    with Image.open(source_file) as s_img:
                        s_size = s_img.size
                    val = validator.validate_expanded_image(
                        expanded_target,
                        base_size=s_size,
                        mode="bleed_5mm",
                        bleed_mm=5.0,
                        allow_black_borders=True,
                    )
                    if val.is_valid:
                        logger.success(
                            "[{}/{}] [Pedido {}] Fundo já expandido e válido: '{}'",
                            processed,
                            total_files,
                            order_id,
                            expanded_target.name,
                        )
                        succeeded += 1
                        continue

                logger.info(
                    "[{}/{}] [Pedido {}] Expandindo fundo: '{}' (sangria 5mm + preserve_frame)...",
                    processed,
                    total_files,
                    order_id,
                    source_file.name,
                )

                try:
                    result_path = run_background_expansion_orchestration(
                        image_path=source_file,
                        mode="bleed_5mm",
                        bleed_mm=5.0,
                        preserve_frame=True,
                        config=order_cfg,
                        context=shared_context,
                        max_retries=3,
                    )
                    logger.success(
                        "[{}/{}] [Pedido {}] Fundo expandido com sucesso: '{}'",
                        processed,
                        total_files,
                        order_id,
                        result_path.name,
                    )
                    succeeded += 1
                except Exception as exc:
                    logger.error(
                        "[{}/{}] [Pedido {}] Falha ao expandir fundo '{}': {}",
                        processed,
                        total_files,
                        order_id,
                        source_file.name,
                        exc,
                    )
                    failed += 1

    finally:
        shared_context.close()

    logger.info(
        "Expansão concluída: {} processado(s), {} sucesso(s), {} falha(s).",
        processed,
        succeeded,
        failed,
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    from PIL import Image
    sys.exit(main())
