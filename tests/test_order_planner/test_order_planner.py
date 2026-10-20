"""Suíte de testes automatizados para o módulo `tools/order_planner/` e CLI `order`."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Tuple
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageOps
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cli
from tools.order_planner import (
    BLEED_5MM_PX,
    DEFAULT_CARD_BACKS_DIR,
    DEFAULT_ORDERS_ROOT,
    DOSSIE_FILENAME,
    OrderJob,
    ProductRoute,
    QualityGateResult,
    TaskQueueItem,
    build_task_queue,
    catalog_order_files,
    create_order_job,
    deduce_product_route,
    discover_orders,
    execute_order_job,
    find_order_by_id,
    infer_poster_format,
    is_cancelled_order_dir,
    is_finished_order_dir,
    normalize_product_route,
    parse_card_input_from_order,
    resolve_card_back_by_game,
    should_ignore_order_dir,
    verify_bleed_gate,
    verify_mug_gate,
    verify_sheet_gate,
    verify_upscale_gate,
)
from tools.print_sheet.pdf_builder import save_pages_to_pdf


def create_colorful_image(
    size: Tuple[int, int],
    dpi: Tuple[int, int] = (300, 300),
    add_pillarbox: bool = False,
) -> Image.Image:
    """Cria uma imagem RGB com gradiente e formas assimétricas (não-monocromática e não-simétrica)."""
    w, h = size
    img = Image.new("RGB", (w, h), color=(45, 90, 160))
    draw = ImageDraw.Draw(img)

    # Elementos assimétricos para garantir variância cromática e detecção de espelhamento
    draw.rectangle((w // 8, h // 6, w // 2, h // 2), fill=(220, 80, 50))
    draw.ellipse((w // 3, h // 3, (w * 4) // 5, (h * 4) // 5), fill=(240, 200, 60))
    draw.polygon([(w // 10, h - h // 8), (w // 3, h // 2), (w // 2, h - h // 10)], fill=(60, 190, 110))

    if add_pillarbox:
        bar_w = max(20, int(w * 0.08))
        draw.rectangle((0, 0, bar_w, h), fill=(0, 0, 0))
        draw.rectangle((w - bar_w, 0, w, h), fill=(0, 0, 0))

    img.info["dpi"] = dpi
    return img


class TestOrderPlannerSchemas(unittest.TestCase):
    """Valida os schemas Pydantic v2 em `tools/order_planner/schema.py`."""

    def test_product_route_enum_and_aliases(self) -> None:
        """Verifica todos os valores obrigatórios de ProductRoute e resolução case-insensitive."""
        self.assertEqual(ProductRoute.UPSCALE_ONLY.value, "UPSCALE_ONLY")
        self.assertEqual(ProductRoute.POSTER_FULL.value, "POSTER_FULL")
        self.assertEqual(ProductRoute.CARD_TCG.value, "CARD_TCG")
        self.assertEqual(ProductRoute.MUG_11OZ.value, "MUG_11OZ")

        self.assertEqual(normalize_product_route("upscale_only"), ProductRoute.UPSCALE_ONLY)
        self.assertEqual(normalize_product_route("poster_full"), ProductRoute.POSTER_FULL)
        self.assertEqual(normalize_product_route("card_tcg"), ProductRoute.CARD_TCG)
        self.assertEqual(normalize_product_route("mug_11oz"), ProductRoute.MUG_11OZ)
        self.assertEqual(normalize_product_route("caneca"), ProductRoute.MUG_11OZ)

        with self.assertRaises(ValueError):
            normalize_product_route("rota_inexistente")

    def test_quality_gate_result_task_queue_item_and_order_job_models(self) -> None:
        """Valida instanciação e restrições dos modelos QualityGateResult, TaskQueueItem e OrderJob."""
        gate = QualityGateResult(
            stage="upscale",
            passed=True,
            details="300 DPI confirmado sem pillarbox",
            file_checked=Path("output/poster.png"),
        )
        self.assertTrue(gate.passed)
        self.assertEqual(gate.stage, "upscale")
        self.assertEqual(gate.file_checked, Path("output/poster.png"))

        task = TaskQueueItem(
            step_number=1,
            tool_name="upscaler",
            action_description="Upscaling 300 DPI",
            status="PENDING",
            gate_criterion="verify_upscale_gate",
        )
        self.assertEqual(task.step_number, 1)
        self.assertEqual(task.tool_name, "upscaler")

        job = OrderJob(
            order_id="176",
            order_dir=Path("Pedidos/176"),
            route="card_tcg",
            customer_files=[Path("Pedidos/176/foto1.jpg"), Path("Pedidos/176/texto.txt")],
            tasks=[task],
            status="PENDING",
        )
        self.assertEqual(job.route, ProductRoute.CARD_TCG)
        self.assertEqual(len(job.customer_files), 2)
        self.assertEqual(len(job.tasks), 1)

        with self.assertRaises(ValidationError):
            TaskQueueItem(
                step_number=0,
                tool_name="upscaler",
                action_description="Inválido",
                status="PENDING",
                gate_criterion="gate",
            )


class TestOrderScanner(unittest.TestCase):
    """Testa `discover_orders` e catalogação de arquivos em `tools/order_planner/scanner.py`."""

    def test_discover_orders_ignores_ok_folders_and_catalogs_files(self) -> None:
        """Deve ignorar pastas com sufixo `- ok` e catalogar fotos, briefings e PDFs."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            # Pasta finalizada (deve ser ignorada)
            done_dir = root / "168 - ok"
            done_dir.mkdir()
            (done_dir / "foto1.jpg").write_bytes(b"fake")

            # Pedido 171: Carta TCG com foto Shopee e fundo.jpg
            dir_171 = root / "171"
            dir_171.mkdir()
            (dir_171 / "br-11134231-820lr-mudfcmzls3ya41.jpg").write_bytes(b"img")
            (dir_171 / "fundo.jpg").write_bytes(b"back")

            # Pedido 176: Carta TCG com briefing texto.txt + PDF de envio
            dir_176 = root / "176"
            dir_176.mkdir()
            (dir_176 / "foto1.jpg").write_bytes(b"img")
            (dir_176 / "texto.txt").write_text(
                'Gostaria da carta de Yugioh com o nome "Laço do amor eterno", carta de armadilha.',
                encoding="utf-8",
            )
            (dir_176 / "etiqueta_envio.pdf").write_bytes(b"%PDF-1.4")

            # Pedido 180: Caneca 11oz
            dir_180 = root / "180"
            dir_180.mkdir()
            (dir_180 / "foto_cliente.jpg").write_bytes(b"img")
            (dir_180 / "texto.txt").write_text(
                "Quero uma caneca 11oz panorâmica com tema Pokemon",
                encoding="utf-8",
            )

            orders = discover_orders(root)
            order_ids = [o.order_id for o in orders]
            self.assertEqual(order_ids, ["171", "176", "180"])
            self.assertNotIn("168 - ok", order_ids)
            self.assertTrue(is_finished_order_dir(done_dir))

            job_176 = find_order_by_id("176", orders_root=root)
            self.assertEqual(job_176.route, ProductRoute.CARD_TCG)
            cat_176 = catalog_order_files(dir_176)
            self.assertEqual(len(cat_176.photos), 1)
            self.assertEqual(len(cat_176.briefings), 1)
            self.assertEqual(len(cat_176.shipping_pdfs), 1)

            job_180 = find_order_by_id("180", orders_root=root)
            self.assertEqual(job_180.route, ProductRoute.MUG_11OZ)


class TestParserAndRouter(unittest.TestCase):
    """Testa dedução de rotas, parser de briefing e montagem da fila de tarefas."""

    def test_deduce_routes_and_build_task_queues(self) -> None:
        """Verifica se cada rota monta exatamente a sequência de ferramentas e Quality Gates esperada."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            # 1. UPSCALE_ONLY
            d_up = base / "201"
            d_up.mkdir()
            (d_up / "foto.jpg").write_bytes(b"img")
            (d_up / "texto.txt").write_text("Pedido apenas upscale 300 DPI A3 sem folha", encoding="utf-8")
            self.assertEqual(deduce_product_route(d_up), ProductRoute.UPSCALE_ONLY)
            self.assertEqual(infer_poster_format("Pedido A3 horizontal"), "a3_h")

            q_up = build_task_queue(ProductRoute.UPSCALE_ONLY, target_format="a3_v")
            self.assertEqual(len(q_up), 1)
            self.assertEqual(q_up[0].tool_name, "upscaler")

            # 2. POSTER_FULL
            d_poster = base / "202"
            d_poster.mkdir()
            (d_poster / "foto.jpg").write_bytes(b"img")
            (d_poster / "texto.txt").write_text("Poster A3 vertical com sangria e folha de corte", encoding="utf-8")
            self.assertEqual(deduce_product_route(d_poster), ProductRoute.POSTER_FULL)

            q_poster = build_task_queue(ProductRoute.POSTER_FULL, target_format="a3_v")
            self.assertEqual([t.tool_name for t in q_poster], ["upscaler", "background_expander", "print_sheet"])

            # 3. CARD_TCG
            d_card = base / "203"
            d_card.mkdir()
            ref_photo = d_card / "foto1.jpg"
            ref_photo.write_bytes(b"img")
            (d_card / "texto.txt").write_text(
                'Gostaria da carta com o fundo de Yugioh, nome "Dragão Branco", efeito contínuo',
                encoding="utf-8",
            )
            self.assertEqual(deduce_product_route(d_card), ProductRoute.CARD_TCG)
            card_in = parse_card_input_from_order(d_card, reference_photos=[ref_photo])
            self.assertEqual(card_in.tipo, "Yu-Gi-Oh!")
            self.assertEqual(card_in.titulo, "Dragão Branco")

            q_card = build_task_queue(ProductRoute.CARD_TCG)
            self.assertEqual([t.tool_name for t in q_card], ["card_generator", "print_sheet"])

            # 4. MUG_11OZ
            q_mug = build_task_queue(ProductRoute.MUG_11OZ)
            self.assertEqual([t.tool_name for t in q_mug], ["mug_artist"])


class TestQualityGates(unittest.TestCase):
    """Testa os 4 Quality Gates determinísticos em `tools/order_planner/quality_gates.py`."""

    def test_verify_upscale_gate_approves_300dpi_and_rejects_pillarbox_or_low_res(self) -> None:
        """Valida 300 DPI, resolução mínima (2480x3543 para A4_V) e reprovação de pillarbox."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)

            valid_path = tmp_dir / "poster_ok.png"
            img_ok = create_colorful_image((2480, 3543), dpi=(300, 300), add_pillarbox=False)
            img_ok.save(valid_path, format="PNG", dpi=(300, 300))

            res_ok = verify_upscale_gate(valid_path, expected_format="a4_v")
            self.assertTrue(res_ok.passed, msg=res_ok.details)
            self.assertEqual(res_ok.stage, "upscale")

            # Com barras pretas (pillarbox) -> deve reprovar
            pillar_path = tmp_dir / "poster_pillarbox.png"
            img_pillar = create_colorful_image((2480, 3543), dpi=(300, 300), add_pillarbox=True)
            img_pillar.save(pillar_path, format="PNG", dpi=(300, 300))

            res_pillar = verify_upscale_gate(pillar_path, expected_format="a4_v")
            self.assertFalse(res_pillar.passed)
            self.assertIn("pillarbox", res_pillar.details.lower())

            # Baixa resolução -> deve reprovar
            low_path = tmp_dir / "poster_low.png"
            img_low = create_colorful_image((800, 1200), dpi=(72, 72))
            img_low.save(low_path, format="PNG", dpi=(72, 72))

            res_low = verify_upscale_gate(low_path, expected_format="a4_v")
            self.assertFalse(res_low.passed)

    def test_verify_bleed_gate_confirms_plus_59px_per_border(self) -> None:
        """Confirma que a sangria de 5mm adiciona exatamente +59px por borda (+118px por eixo)."""
        self.assertEqual(BLEED_5MM_PX, 59)
        orig_size = (2480, 3543)
        expanded_size = (2480 + 118, 3543 + 118)  # 2598 x 3661

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            bleed_ok_path = tmp_dir / "bleed_ok.png"
            img_bleed = create_colorful_image(expanded_size, dpi=(300, 300))
            img_bleed.save(bleed_ok_path, format="PNG", dpi=(300, 300))

            res_ok = verify_bleed_gate(bleed_ok_path, original_size=orig_size)
            self.assertTrue(res_ok.passed, msg=res_ok.details)
            self.assertEqual(res_ok.stage, "bleed")

            # Sem sangria (mesmo tamanho original) -> deve reprovar
            wrong_path = tmp_dir / "bleed_wrong.png"
            img_wrong = create_colorful_image(orig_size, dpi=(300, 300))
            img_wrong.save(wrong_path, format="PNG", dpi=(300, 300))

            res_fail = verify_bleed_gate(wrong_path, original_size=orig_size)
            self.assertFalse(res_fail.passed)
            self.assertIn("59px", res_fail.details)

    def test_verify_sheet_gate_checks_pdf_pages_and_size_via_pymupdf(self) -> None:
        """Verifica número de páginas e dimensões físicas do PDF com PyMuPDF (fitz)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            pdf_2p = tmp_dir / "sheet_duplex.pdf"
            page1 = create_colorful_image((2717, 3780))  # Super A4 @ 300 DPI
            page2 = create_colorful_image((2717, 3780))
            save_pages_to_pdf([page1, page2], pdf_2p, dpi=300)

            res_ok = verify_sheet_gate(pdf_2p, expected_pages=2)
            self.assertTrue(res_ok.passed, msg=res_ok.details)
            self.assertEqual(res_ok.stage, "sheet")

            # Quantidade incorreta de páginas -> deve reprovar
            res_wrong_pages = verify_sheet_gate(pdf_2p, expected_pages=1)
            self.assertFalse(res_wrong_pages.passed)

            # PDF minúsculo (fora do padrão físico) -> deve reprovar
            tiny_pdf = tmp_dir / "tiny.pdf"
            tiny_page = create_colorful_image((200, 200))
            save_pages_to_pdf([tiny_page], tiny_pdf, dpi=300)
            res_tiny = verify_sheet_gate(tiny_pdf, expected_pages=1)
            self.assertFalse(res_tiny.passed)

    def test_verify_mug_gate_checks_2598x1122_and_horizontal_mirroring(self) -> None:
        """Confirma dimensões 2598x1122px e espelhamento horizontal exato entre prévia e transfer."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            preview_path = tmp_dir / "mug_preview.png"
            transfer_path = tmp_dir / "mug_transfer.png"
            unmirrored_path = tmp_dir / "mug_unmirrored.png"

            preview_img = create_colorful_image((2598, 1122), dpi=(300, 300))
            transfer_img = ImageOps.mirror(preview_img)

            preview_img.save(preview_path, format="PNG", dpi=(300, 300))
            transfer_img.save(transfer_path, format="PNG", dpi=(300, 300))
            preview_img.save(unmirrored_path, format="PNG", dpi=(300, 300))

            res_ok = verify_mug_gate(preview_path, transfer_path)
            self.assertTrue(res_ok.passed, msg=res_ok.details)
            self.assertEqual(res_ok.stage, "mug")

            # Transfer não espelhado -> deve reprovar
            res_unmirrored = verify_mug_gate(preview_path, unmirrored_path)
            self.assertFalse(res_unmirrored.passed)
            self.assertIn("espelhado", res_unmirrored.details.lower())


class TestOrderOrchestratorAndCLI(unittest.TestCase):
    """Testa a execução simulada da esteira completa, gravação de dossiê, `--mark-ok` e CLI `order`."""

    def test_execute_poster_full_and_upscale_only_routes_and_mark_ok(self) -> None:
        """Simula execução da esteira POSTER_FULL e UPSCALE_ONLY gerando dossie_producao.json e `- ok`."""
        with tempfile.TemporaryDirectory() as tmp:
            orders_root = Path(tmp)
            order_dir = orders_root / "175"
            order_dir.mkdir()

            src_photo = order_dir / "foto1.jpg"
            create_colorful_image((800, 1100)).save(src_photo, format="JPEG", dpi=(300, 300))
            (order_dir / "texto.txt").write_text("Poster A4 vertical com sangria", encoding="utf-8")

            def fake_upscale(image_path: Path, target_format: str, config=None, max_retries: int = 3) -> Path:
                out = (config.output_dir if config else order_dir) / "upscaled_a4_v.png"
                create_colorful_image((2480, 3543)).save(out, format="PNG", dpi=(300, 300))
                return out

            def fake_expand(
                image_path: Path,
                mode: str = "bleed_5mm",
                bleed_mm: float = 5.0,
                preserve_frame: bool = False,
                config=None,
                max_retries: int = 3,
            ) -> Path:
                out = (config.output_dir if config else order_dir) / "expanded_bleed.png"
                create_colorful_image((2480 + 118, 3543 + 118)).save(out, format="PNG", dpi=(300, 300))
                return out

            with (
                patch("tools.order_planner.orchestrator.upscale_card_to_poster", side_effect=fake_upscale),
                patch("tools.order_planner.orchestrator.expand_background", side_effect=fake_expand),
            ):
                # 1. Testa CLI --scan e --plan
                self.assertEqual(cli.main(["order", "--scan", "--orders-root", str(orders_root), "--no-file-log"]), 0)
                self.assertEqual(
                    cli.main(["pedidos", "--plan", "--id", "175", "--orders-root", str(orders_root), "--no-file-log"]),
                    0,
                )

                # 2. Testa CLI --run com --route upscale_only (sem --mark-ok)
                exit_up = cli.main(
                    [
                        "order",
                        "--run",
                        "--id",
                        "175",
                        "--route",
                        "upscale_only",
                        "--orders-root",
                        str(orders_root),
                        "--no-file-log",
                    ]
                )
                self.assertEqual(exit_up, 0)
                dossie_file = order_dir / DOSSIE_FILENAME
                self.assertTrue(dossie_file.is_file())
                dossie_data = json.loads(dossie_file.read_text(encoding="utf-8"))
                self.assertEqual(dossie_data["route"], "UPSCALE_ONLY")
                self.assertEqual(len(dossie_data["quality_gates"]), 1)

                # 3. Testa CLI --run na rota completa POSTER_FULL com --mark-ok
                exit_full = cli.main(
                    [
                        "planner",
                        "--run",
                        "--id",
                        "175",
                        "--mark-ok",
                        "--orders-root",
                        str(orders_root),
                        "--no-file-log",
                    ]
                )
                self.assertEqual(exit_full, 0)

                renamed_dir = orders_root / "175 - ok"
                self.assertTrue(renamed_dir.is_dir())
                self.assertTrue((renamed_dir / DOSSIE_FILENAME).is_file())
                final_dossie = json.loads((renamed_dir / DOSSIE_FILENAME).read_text(encoding="utf-8"))
                self.assertEqual(final_dossie["route"], "POSTER_FULL")
                self.assertEqual(final_dossie["status"], "COMPLETED")
                self.assertEqual(len(final_dossie["quality_gates"]), 3)

    def test_execute_card_tcg_and_mug_11oz_routes(self) -> None:
        """Simula a execução completa das rotas CARD_TCG e MUG_11OZ passando pelos Quality Gates."""
        with tempfile.TemporaryDirectory() as tmp:
            orders_root = Path(tmp)

            # Pedido 176: CARD_TCG
            card_dir = orders_root / "176"
            card_dir.mkdir()
            ref_img = card_dir / "br-11134231-test.jpg"
            create_colorful_image((744, 1039)).save(ref_img, format="JPEG", dpi=(300, 300))
            (card_dir / "texto.txt").write_text(
                'Gostaria da carta de Yugioh com o nome "Laço do amor eterno", armadilha.',
                encoding="utf-8",
            )

            def fake_generate_card(card, config=None, max_retries: int = 3):
                out = (config.output_dir if config else card_dir) / "carta_gerada.png"
                create_colorful_image((744, 1039)).save(out, format="PNG", dpi=(300, 300))
                return True, out, None

            with patch("tools.order_planner.orchestrator.generate_single_card", side_effect=fake_generate_card):
                job_card = find_order_by_id("176", orders_root=orders_root)
                report_card = execute_order_job(job_card, mark_ok=False)
                self.assertTrue(report_card.passed)
                self.assertEqual(report_card.order_job.status, "COMPLETED")
                self.assertEqual(len(report_card.gate_results), 2)
                self.assertTrue((card_dir / DOSSIE_FILENAME).is_file())

            # Pedido 190: MUG_11OZ (execução real local com MugArtworkComposer)
            mug_dir = orders_root / "190"
            mug_dir.mkdir()
            mug_photo = mug_dir / "foto1.jpg"
            create_colorful_image((744, 1039)).save(mug_photo, format="JPEG", dpi=(300, 300))
            (mug_dir / "texto.txt").write_text("Caneca 11oz sublimação", encoding="utf-8")

            job_mug = create_order_job(
                order_id="190",
                order_dir=mug_dir,
                customer_files=[mug_photo, mug_dir / "texto.txt"],
            )
            self.assertEqual(job_mug.route, ProductRoute.MUG_11OZ)
            report_mug = execute_order_job(job_mug, mark_ok=True)
            self.assertTrue(report_mug.passed)
            self.assertTrue(report_mug.renamed_to_ok)
            self.assertTrue((orders_root / "190 - ok" / DOSSIE_FILENAME).is_file())

    def test_gate_failure_stops_queue_and_prevents_mark_ok(self) -> None:
        """Se um Quality Gate reprovar, a fila deve parar, status=FAILED e a pasta não deve virar `- ok`."""
        with tempfile.TemporaryDirectory() as tmp:
            orders_root = Path(tmp)
            order_dir = orders_root / "199"
            order_dir.mkdir()
            src_photo = order_dir / "foto1.jpg"
            create_colorful_image((600, 800)).save(src_photo, format="JPEG", dpi=(300, 300))

            # Upscaler retorna imagem com pillarbox que reprovará no verify_upscale_gate
            def bad_upscale(image_path: Path, target_format: str, config=None, max_retries: int = 3) -> Path:
                out = (config.output_dir if config else order_dir) / "bad_upscale.png"
                create_colorful_image((2480, 3543), add_pillarbox=True).save(out, format="PNG", dpi=(300, 300))
                return out

            with patch("tools.order_planner.orchestrator.upscale_card_to_poster", side_effect=bad_upscale):
                exit_code = cli.main(
                    [
                        "order",
                        "--run",
                        "--id",
                        "199",
                        "--mark-ok",
                        "--orders-root",
                        str(orders_root),
                        "--no-file-log",
                    ]
                )
                self.assertEqual(exit_code, 1)
                self.assertTrue(order_dir.is_dir())
                self.assertFalse((orders_root / "199 - ok").exists())
                self.assertFalse((order_dir / DOSSIE_FILENAME).exists())

    def test_cli_order_error_validation(self) -> None:
        """Verifica códigos de erro da CLI `order` para argumentos inválidos ou ausentes."""
        with tempfile.TemporaryDirectory() as tmp:
            # Sem --scan / --plan / --run -> exit code 2
            self.assertEqual(cli.main(["order", "--orders-root", tmp, "--no-file-log"]), 2)
            # --plan sem --id -> exit code 2
            self.assertEqual(cli.main(["order", "--plan", "--orders-root", tmp, "--no-file-log"]), 2)
            # --route inválido -> exit code 2
            self.assertEqual(
                cli.main(["order", "--scan", "--route", "invalida", "--orders-root", tmp, "--no-file-log"]),
                2,
            )
            # Pedido inexistente -> exit code 1
            self.assertEqual(
                cli.main(["order", "--plan", "--id", "9999", "--orders-root", tmp, "--no-file-log"]),
                1,
            )


class TestCardBacksResolution(unittest.TestCase):
    """Testa a resolução de fundos oficiais por marca e regras de precedência/fallback."""

    def test_resolve_official_brands(self) -> None:
        """Verifica a resolução automática dos 4 jogos oficiais para os arquivos com sangria."""
        magic_back = resolve_card_back_by_game("Magic")
        self.assertEqual(magic_back.name, "magic.png")
        self.assertTrue(magic_back.is_file())

        pokemon_back = resolve_card_back_by_game("Pokemon")
        self.assertEqual(pokemon_back.name, "pokemon.png")
        self.assertTrue(pokemon_back.is_file())

        yugioh_back = resolve_card_back_by_game("Yu-Gi-Oh!")
        self.assertEqual(yugioh_back.name, "yugioh.png")
        self.assertTrue(yugioh_back.is_file())

        onepiece_back = resolve_card_back_by_game("One Piece")
        self.assertEqual(onepiece_back.name, "onepiece.png")
        self.assertTrue(onepiece_back.is_file())

    def test_resolve_custom_back_prioritization(self) -> None:
        """Se o cliente fornecer um arquivo de verso existente (ex: fundo.jpg), ele deve ser priorizado."""
        with tempfile.TemporaryDirectory() as tmp:
            custom_back = Path(tmp) / "fundo.jpg"
            create_colorful_image((815, 1110)).save(custom_back, format="JPEG")

            resolved = resolve_card_back_by_game(game_type="Pokemon", custom_back_path=custom_back)
            self.assertEqual(resolved, custom_back.resolve())

            # Se o arquivo customizado não existir, faz fallback para o jogo
            non_existent = Path(tmp) / "fundo_inexistente.jpg"
            fallback_resolved = resolve_card_back_by_game(game_type="Magic", custom_back_path=non_existent)
            self.assertEqual(fallback_resolved.name, "magic.png")

    def test_resolve_fallback_institutional_and_pb(self) -> None:
        """Jogos não reconhecidos devem fazer fallback para studio_kustom.png e suportar versão P&B."""
        fallback_back = resolve_card_back_by_game("Jogo Desconhecido")
        self.assertEqual(fallback_back.name, "studio_kustom.png")
        self.assertTrue(fallback_back.is_file())

        pb_back = resolve_card_back_by_game("pb")
        self.assertEqual(pb_back.name, "studio_kustom_pb.png")
        self.assertTrue(pb_back.is_file())


class TestPosterOrientationAndFormat(unittest.TestCase):
    """Testa a padronização de pôsteres para formato A3 e dedução de orientação (A3_H vs A3_V)."""

    def test_default_format_is_a3_v(self) -> None:
        """Pôsteres sem especificações explícitas de formato devem adotar A3_V por padrão."""
        self.assertEqual(infer_poster_format(), "a3_v")
        self.assertEqual(infer_poster_format("Quadro personalizado para sala"), "a3_v")
        self.assertEqual(infer_poster_format("Pôster vertical"), "a3_v")

    def test_orientation_detection_from_image_dimensions_like_order_178(self) -> None:
        """Imagens com largura > altura (como no pedido 178) devem ser resolvidas como A3_H."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # Imagem horizontal (1280x854, como no pedido 178)
            h_img_path = tmp_path / "br-11134231-horizontal.jpg"
            create_colorful_image((1280, 854)).save(h_img_path, format="JPEG")

            fmt_h = infer_poster_format(briefing_text="", files=[h_img_path])
            self.assertEqual(fmt_h, "a3_h")

            # Imagem vertical (853x1280)
            v_img_path = tmp_path / "br-11134231-vertical.jpg"
            create_colorful_image((853, 1280)).save(v_img_path, format="JPEG")

            fmt_v = infer_poster_format(briefing_text="", files=[v_img_path])
            self.assertEqual(fmt_v, "a3_v")

    def test_orientation_from_briefing_keywords(self) -> None:
        """Palavras-chave de orientação devem prevalecer no briefing."""
        self.assertEqual(infer_poster_format("Pôster em orientação horizontal"), "a3_h")
        self.assertEqual(infer_poster_format("Paisagem landscape 420x300"), "a3_h")
        self.assertEqual(infer_poster_format("A3_H"), "a3_h")
        self.assertEqual(infer_poster_format("A3_V"), "a3_v")

    def test_explicit_a4_preservation(self) -> None:
        """Se o cliente solicitar A4 explicitamente, respeita a escolha sem forçar A3."""
        self.assertEqual(infer_poster_format("Quero no formato A4"), "a4_v")
        self.assertEqual(infer_poster_format("Quero no formato A4 horizontal"), "a4_h")


class TestRealOrdersSpecificRules(unittest.TestCase):
    """Testa regras de pedidos reais (Pedido 165 Pokémon foto.jpg, Pedido 174 Magic, Pedidos Cancelados)."""

    def test_order_165_pokemon_foto_preservation(self) -> None:
        """Pedido 165 deve ser roteado para CARD_TCG, jogo Pokemon e preservar foto.jpg sem deformação."""
        with tempfile.TemporaryDirectory() as tmp:
            order_165 = Path(tmp) / "165"
            order_165.mkdir()
            foto_jpg = order_165 / "foto.jpg"
            create_colorful_image((590, 1280)).save(foto_jpg, format="JPEG")
            shopee_img = order_165 / "br-11134231-ref.jpg"
            create_colorful_image((853, 1280)).save(shopee_img, format="JPEG")

            route = deduce_product_route(order_165, customer_files=[shopee_img, foto_jpg])
            self.assertEqual(route, ProductRoute.CARD_TCG)

            card_in = parse_card_input_from_order(order_165, reference_photos=[shopee_img, foto_jpg])
            self.assertEqual(card_in.tipo, "Pokemon")
            self.assertIn("sem deformação", card_in.descricao.lower())
            self.assertTrue(card_in.imagens_referencia is not None and len(card_in.imagens_referencia) >= 1)
            self.assertEqual(Path(card_in.imagens_referencia[0]).name, "foto.jpg")

    def test_order_174_magic_explicit_mapping(self) -> None:
        """Pedido 174 deve ser mapeado explicitamente para CARD_TCG com tipo Magic."""
        with tempfile.TemporaryDirectory() as tmp:
            order_174 = Path(tmp) / "174"
            order_174.mkdir()
            img_a = order_174 / "br-11134231-1.jpg"
            create_colorful_image((640, 870)).save(img_a, format="JPEG")
            img_b = order_174 / "br-11134231-2.jpg"
            create_colorful_image((640, 870)).save(img_b, format="JPEG")

            route = deduce_product_route(order_174, customer_files=[img_a, img_b])
            self.assertEqual(route, ProductRoute.CARD_TCG)

            card_in = parse_card_input_from_order(order_174, reference_photos=[img_a, img_b])
            self.assertEqual(card_in.tipo, "Magic")
            self.assertIn("Magic", card_in.titulo)

    def test_cancelled_orders_ignored(self) -> None:
        """Pastas com sufixo '- c' ou '- cancelado' devem ser identificadas e ignoradas no scanner."""
        self.assertTrue(is_cancelled_order_dir("115 - c"))
        self.assertTrue(is_cancelled_order_dir("115 - C"))
        self.assertTrue(is_cancelled_order_dir("120 - cancelado"))
        self.assertTrue(is_cancelled_order_dir("120 - CANCELADO"))
        self.assertFalse(is_cancelled_order_dir("176"))
        self.assertFalse(is_cancelled_order_dir("168 - ok"))

        self.assertTrue(should_ignore_order_dir("115 - c"))
        self.assertTrue(should_ignore_order_dir("168 - ok"))
        self.assertFalse(should_ignore_order_dir("176"))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "115 - c").mkdir()
            (root / "120 - cancelado").mkdir()
            (root / "168 - ok").mkdir()
            valid_order = root / "176"
            valid_order.mkdir()
            (valid_order / "foto.jpg").write_bytes(b"img")

            discovered = discover_orders(orders_root=root)
            discovered_ids = [job.order_id for job in discovered]
            self.assertEqual(discovered_ids, ["176"])
            self.assertNotIn("115 - c", discovered_ids)
            self.assertNotIn("120 - cancelado", discovered_ids)
            self.assertNotIn("168 - ok", discovered_ids)


if __name__ == "__main__":
    unittest.main()
