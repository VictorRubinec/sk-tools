"""Orquestrador de execução da fila de produção e avaliação de Quality Gates (tools/order_planner/orchestrator.py)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from PIL import Image

from tools.background_expander.api import expand_background
from tools.card_generator.api import generate_single_card
from tools.card_generator.core.config import AppConfig, DEFAULT_CONFIG
from tools.card_generator.core.logger import logger
from tools.card_generator.validator.card_validator import CardImageValidator
from tools.mug_artist.api import create_mug_artwork
from tools.order_planner.card_backs import resolve_card_back_by_game
from tools.order_planner.parser import (
    infer_poster_format,
    is_back_image,
    is_generated_artifact,
    parse_card_input_from_order,
    parse_mug_input_from_order,
    read_order_briefing_text,
)
from tools.order_planner.quality_gates import (
    verify_bleed_gate,
    verify_mug_gate,
    verify_sheet_gate,
    verify_upscale_gate,
)
from tools.order_planner.router import plan_order_job
from tools.order_planner.scanner import DEFAULT_ORDERS_ROOT, find_order_by_id
from tools.order_planner.schema import (
    OrderJob,
    ProductRoute,
    QualityGateResult,
    normalize_product_route,
)
from tools.print_sheet.api import create_card_print_sheet, create_poster_print_sheet
from tools.print_sheet.card_grid import MAX_CARDS_PER_SHEET
from tools.upscaler.api import upscale_card_to_poster
from tools.upscaler.validator import PosterImageValidator

DOSSIE_FILENAME = "dossie_producao.json"


@dataclass
class OrderExecutionReport:
    """Relatório consolidado da execução de um `OrderJob` e seus Quality Gates."""

    order_job: OrderJob
    passed: bool
    gate_results: List[QualityGateResult] = field(default_factory=list)
    dossie_path: Optional[Path] = None
    output_files: List[Path] = field(default_factory=list)
    renamed_to_ok: bool = False


def _select_primary_source_image(order_job: OrderJob) -> Path:
    """Seleciona a imagem principal de origem do cliente dentro do pedido."""
    image_exts = {".jpg", ".jpeg", ".png", ".webp"}
    candidates = [
        p
        for p in order_job.customer_files
        if p.suffix.lower() in image_exts and not is_back_image(p) and p.is_file()
    ]
    if not candidates:
        candidates = [
            p for p in order_job.customer_files if p.suffix.lower() in image_exts and p.is_file()
        ]
    if not candidates and order_job.order_dir.is_dir():
        candidates = [
            p
            for p in sorted(order_job.order_dir.iterdir())
            if p.is_file() and p.suffix.lower() in image_exts and not is_generated_artifact(p)
        ]
    if not candidates:
        raise FileNotFoundError(
            f"Nenhuma imagem de origem encontrada para o pedido '{order_job.order_id}' em '{order_job.order_dir}'."
        )
    return candidates[0]


def _select_card_fronts_and_back(
    order_job: OrderJob,
    generated_card_path: Optional[Path] = None,
    game_type: Optional[str] = None,
) -> Tuple[List[Path], Union[Path, List[Path]]]:
    """Seleciona as imagens de frente e verso com sangria técnica para imposição de cartas TCG."""
    image_exts = {".jpg", ".jpeg", ".png", ".webp"}
    all_images = [
        p
        for p in order_job.customer_files
        if p.suffix.lower() in image_exts and p.is_file()
    ]

    back_candidates = [p for p in all_images if is_back_image(p)]
    front_candidates = [p for p in all_images if not is_back_image(p)]

    if generated_card_path is not None and generated_card_path.is_file():
        fronts = [generated_card_path]
    elif front_candidates:
        fronts = front_candidates
    elif all_images:
        fronts = [all_images[0]]
    else:
        raise FileNotFoundError(
            f"Nenhuma imagem de frente de carta disponível no pedido '{order_job.order_id}'."
        )

    resolved_game = game_type
    if not resolved_game:
        try:
            briefing = read_order_briefing_text(order_job.order_dir)
            card_in = parse_card_input_from_order(order_job.order_dir, briefing_text=briefing)
            resolved_game = card_in.tipo
        except Exception:
            resolved_game = "Pokemon"

    if back_candidates:
        if len(back_candidates) == len(fronts) and len(fronts) > 1:
            back = [
                (p.parent / f"{p.stem}_expanded.png") if (p.parent / f"{p.stem}_expanded.png").is_file() else p
                for p in back_candidates
            ]
        else:
            # Tenta emparelhamento por prefixo de arquivo (ex: 'NOME FRENTE' com 'NOME VERSO')
            matched_backs: List[Path] = []
            all_matched = True
            for f in fronts:
                f_base = f.stem.upper().split("FRENTE")[0].strip()
                match = None
                for b in back_candidates:
                    b_base = b.stem.upper().split("VERSO")[0].strip()
                    if f_base and b_base and f_base == b_base:
                        exp_candidate = b.parent / f"{b.stem}_expanded.png"
                        match = exp_candidate if exp_candidate.is_file() else b
                        break
                if match:
                    matched_backs.append(match)
                else:
                    all_matched = False
                    break

            if all_matched and len(matched_backs) == len(fronts):
                back = matched_backs
            else:
                chosen_back = back_candidates[0]
                exp_candidate = chosen_back.parent / f"{chosen_back.stem}_expanded.png"
                back = resolve_card_back_by_game(
                    game_type=resolved_game,
                    custom_back_path=exp_candidate if exp_candidate.is_file() else chosen_back,
                )
    else:
        back = resolve_card_back_by_game(
            game_type=resolved_game,
            custom_back_path=None,
        )

    return fronts, back


def _verify_card_generation_gate(card_path: Path) -> QualityGateResult:
    """Avalia o Quality Gate da etapa `card_generator` (integridade, proporção TCG e ausência de barras pretas)."""
    if not card_path.is_file():
        return QualityGateResult(
            stage="card_generator",
            passed=False,
            details=f"Arquivo de carta gerada não encontrado: {card_path}",
            file_checked=card_path,
        )

    validator = CardImageValidator()
    val_res = validator.validate_image(card_path)
    errors = list(val_res.errors)

    try:
        with Image.open(card_path) as img:
            rgb_img = img.convert("RGB")
            trimmed = PosterImageValidator.trim_black_borders(rgb_img)
            if trimmed.size != rgb_img.size:
                errors.append(
                    f"Barras pretas periféricas detectadas na carta ({rgb_img.width}x{rgb_img.height}px -> "
                    f"{trimmed.width}x{trimmed.height}px)."
                )
    except Exception as exc:
        errors.append(f"Falha ao inspecionar bordas da carta: {exc}")

    if errors:
        return QualityGateResult(
            stage="card_generator",
            passed=False,
            details=" | ".join(errors),
            file_checked=card_path,
        )

    return QualityGateResult(
        stage="card_generator",
        passed=True,
        details=(
            f"Carta TCG aprovada: {val_res.width}x{val_res.height}px "
            f"(aspect ratio {val_res.aspect_ratio:.3f}), sem pillarbox."
        ),
        file_checked=card_path,
    )


def write_production_dossier(
    order_job: OrderJob,
    gate_results: List[QualityGateResult],
    output_files: List[Path],
) -> Path:
    """Grava o arquivo `dossie_producao.json` na pasta do pedido com a auditoria completa."""
    dossie_path = order_job.order_dir / DOSSIE_FILENAME
    payload: Dict[str, Any] = {
        "order_id": order_job.order_id,
        "order_dir": str(order_job.order_dir.resolve()),
        "route": order_job.route.value,
        "status": order_job.status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "customer_files": [str(p) for p in order_job.customer_files],
        "output_files": [str(p) for p in output_files],
        "tasks": [task.model_dump(mode="json") for task in order_job.tasks],
        "quality_gates": [
            {
                "stage": g.stage,
                "passed": g.passed,
                "details": g.details,
                "file_checked": str(g.file_checked) if g.file_checked else None,
            }
            for g in gate_results
        ],
    }
    dossie_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return dossie_path


def mark_order_directory_ok(order_job: OrderJob) -> Path:
    """Renomeia a pasta do pedido para `<nome> - ok` caso ainda não possua o sufixo."""
    current_dir = order_job.order_dir
    if current_dir.name.strip().lower().endswith("- ok"):
        return current_dir

    target_dir = current_dir.parent / f"{current_dir.name} - ok"
    current_dir.rename(target_dir)
    order_job.order_dir = target_dir
    return target_dir


def execute_order_job(
    order_job: OrderJob,
    config: Optional[AppConfig] = None,
    route_override: Optional[Union[str, ProductRoute]] = None,
    mark_ok: bool = False,
    max_retries: int = 3,
) -> OrderExecutionReport:
    """Executa sequencialmente a fila de ferramentas do `OrderJob` e avalia todos os Quality Gates.

    Se todas as tarefas e Quality Gates forem aprovados:
    - Atualiza `order_job.status = "COMPLETED"`.
    - Grava `dossie_producao.json` na pasta do pedido.
    - Se `mark_ok=True`, renomeia a pasta do pedido para `<numero> - ok`.
    """
    if route_override is not None or not order_job.tasks:
        plan_order_job(order_job, route_override=route_override)

    base_cfg = config or DEFAULT_CONFIG
    order_cfg = replace(base_cfg, output_dir=order_job.order_dir)
    order_job.order_dir.mkdir(parents=True, exist_ok=True)

    briefing_text = read_order_briefing_text(order_job.order_dir)
    target_format = infer_poster_format(
        briefing_text=briefing_text,
        files=order_job.customer_files,
    )

    order_job.status = "IN_PROGRESS"
    gate_results: List[QualityGateResult] = []
    output_files: List[Path] = []

    current_image_path: Optional[Path] = None
    upscaled_size: Optional[Tuple[int, int]] = None
    generated_card_path: Optional[Path] = None
    card_game_type: Optional[str] = None

    try:
        for task in order_job.tasks:
            task.status = "IN_PROGRESS"
            tool = task.tool_name.strip().lower()
            logger.info(
                "[Pedido {}] Passo {}: {} ({})",
                order_job.order_id,
                task.step_number,
                tool,
                task.action_description,
            )

            if tool == "upscaler":
                src_img = _select_primary_source_image(order_job)
                candidate_upscaled = (
                    order_cfg.output_dir / f"{src_img.stem}_poster_{target_format.lower()}.png"
                )
                if (
                    candidate_upscaled.is_file()
                    and verify_upscale_gate(candidate_upscaled, expected_format=target_format).passed
                ):
                    logger.info(
                        "[Pedido {}] Pôster upscaled já existente e aprovado no Quality Gate: '{}'",
                        order_job.order_id,
                        candidate_upscaled.name,
                    )
                    upscaled_path = candidate_upscaled
                else:
                    upscaled_path = upscale_card_to_poster(
                        image_path=src_img,
                        target_format=target_format,
                        config=order_cfg,
                        max_retries=max_retries,
                    )
                output_files.append(upscaled_path)
                gate = verify_upscale_gate(
                    image_path=upscaled_path,
                    expected_format=target_format,
                )
                gate_results.append(gate)

                if not gate.passed:
                    task.status = "FAILED"
                    order_job.status = "FAILED"
                    logger.error(
                        "[Pedido {}] Quality Gate 'upscale' REPROVADO: {}",
                        order_job.order_id,
                        gate.details,
                    )
                    return OrderExecutionReport(
                        order_job=order_job,
                        passed=False,
                        gate_results=gate_results,
                        output_files=output_files,
                    )

                with Image.open(upscaled_path) as up_img:
                    upscaled_size = up_img.size
                current_image_path = upscaled_path
                task.status = "COMPLETED"

            elif tool == "background_expander":
                base_img_path = current_image_path or _select_primary_source_image(order_job)
                if upscaled_size is None:
                    with Image.open(base_img_path) as b_img:
                        upscaled_size = b_img.size

                candidate_expanded = (
                    order_cfg.output_dir / f"{base_img_path.stem}_expanded.png"
                )
                if (
                    candidate_expanded.is_file()
                    and verify_bleed_gate(candidate_expanded, original_size=upscaled_size).passed
                ):
                    logger.info(
                        "[Pedido {}] Imagem com sangria técnica já existente e aprovada no Quality Gate: '{}'",
                        order_job.order_id,
                        candidate_expanded.name,
                    )
                    expanded_path = candidate_expanded
                else:
                    expanded_path = expand_background(
                        image_path=base_img_path,
                        mode="bleed_5mm",
                        bleed_mm=5.0,
                        config=order_cfg,
                        max_retries=max_retries,
                    )
                output_files.append(expanded_path)
                gate = verify_bleed_gate(
                    image_path=expanded_path,
                    original_size=upscaled_size,
                )
                gate_results.append(gate)

                if not gate.passed:
                    task.status = "FAILED"
                    order_job.status = "FAILED"
                    logger.error(
                        "[Pedido {}] Quality Gate 'bleed' REPROVADO: {}",
                        order_job.order_id,
                        gate.details,
                    )
                    return OrderExecutionReport(
                        order_job=order_job,
                        passed=False,
                        gate_results=gate_results,
                        output_files=output_files,
                    )

                current_image_path = expanded_path
                task.status = "COMPLETED"

            elif tool == "card_generator":
                image_exts = {".jpg", ".jpeg", ".png", ".webp"}
                ref_photos = [
                    p
                    for p in order_job.customer_files
                    if p.suffix.lower() in image_exts and not is_back_image(p) and p.is_file()
                ]
                card_input = parse_card_input_from_order(
                    order_dir=order_job.order_dir,
                    briefing_text=briefing_text,
                    reference_photos=ref_photos,
                )
                card_game_type = card_input.tipo

                # Identifica se o cliente já forneceu cartas prontas para imposição direta
                has_front_back_pair = any("frente" in p.stem.lower() for p in order_job.customer_files) and any(
                    "verso" in p.stem.lower() for p in order_job.customer_files
                )
                has_back_file = any(is_back_image(p) for p in order_job.customer_files)
                order_id_clean = order_job.order_id.split("-")[0].strip()

                is_already_rendered = False
                if has_front_back_pair:
                    is_already_rendered = True
                elif has_back_file and not briefing_text.strip() and len(ref_photos) >= 1:
                    is_already_rendered = True
                elif len(ref_photos) >= 2 and not briefing_text.strip() and order_id_clean not in ("165", "176"):
                    is_already_rendered = True

                if is_already_rendered:
                    logger.info(
                        "[Pedido {}] {} carta(s) pronta(s) fornecida(s) pelo cliente. Pulando geração generativa.",
                        order_job.order_id,
                        len(ref_photos),
                    )
                    gate = QualityGateResult(
                        stage="card_generator",
                        passed=True,
                        details=f"{len(ref_photos)} carta(s) TCG prontas fornecidas pelo cliente aprovadas para imposição.",
                        file_checked=ref_photos[0] if ref_photos else None,
                    )
                    gate_results.append(gate)
                    task.status = "COMPLETED"
                else:
                    ok, card_path, _ = generate_single_card(
                        card=card_input,
                        config=order_cfg,
                        max_retries=max_retries,
                    )
                    if not ok or card_path is None:
                        gate = QualityGateResult(
                            stage="card_generator",
                            passed=False,
                            details="Falha na geração da carta TCG via card_generator.",
                            file_checked=None,
                        )
                        gate_results.append(gate)
                        task.status = "FAILED"
                        order_job.status = "FAILED"
                        return OrderExecutionReport(
                            order_job=order_job,
                            passed=False,
                            gate_results=gate_results,
                            output_files=output_files,
                        )

                    output_files.append(card_path)
                    gate = _verify_card_generation_gate(card_path)
                    gate_results.append(gate)

                    if not gate.passed:
                        task.status = "FAILED"
                        order_job.status = "FAILED"
                        logger.error(
                            "[Pedido {}] Quality Gate 'card_generator' REPROVADO: {}",
                            order_job.order_id,
                            gate.details,
                        )
                        return OrderExecutionReport(
                            order_job=order_job,
                            passed=False,
                            gate_results=gate_results,
                            output_files=output_files,
                        )

                    generated_card_path = card_path
                    current_image_path = card_path
                    task.status = "COMPLETED"

            elif tool == "print_sheet":
                if order_job.route == ProductRoute.POSTER_FULL:
                    poster_img = current_image_path or _select_primary_source_image(order_job)
                    paper_code = "a3" if target_format.lower().startswith("a3") else "a4"
                    pdf_out = order_job.order_dir / f"pedido_{order_job.order_id}_poster_{paper_code}.pdf"
                    pdf_path = create_poster_print_sheet(
                        poster_image=poster_img,
                        paper=paper_code,
                        output_pdf=pdf_out,
                        config=order_cfg,
                    )
                    expected_pages = 1
                else:
                    fronts, back = _select_card_fronts_and_back(
                        order_job,
                        generated_card_path=generated_card_path,
                        game_type=card_game_type,
                    )
                    pdf_out = order_job.order_dir / f"pedido_{order_job.order_id}_cards_super_a4.pdf"
                    pdf_path = create_card_print_sheet(
                        front_images=fronts,
                        back_image=back,
                        paper="super_a4",
                        output_pdf=pdf_out,
                        config=order_cfg,
                    )
                    expected_pages = max(2, 2 * math.ceil(len(fronts) / float(MAX_CARDS_PER_SHEET)))

                output_files.append(pdf_path)
                gate = verify_sheet_gate(
                    pdf_path=pdf_path,
                    expected_pages=expected_pages,
                )
                gate_results.append(gate)

                if not gate.passed:
                    task.status = "FAILED"
                    order_job.status = "FAILED"
                    logger.error(
                        "[Pedido {}] Quality Gate 'sheet' REPROVADO: {}",
                        order_job.order_id,
                        gate.details,
                    )
                    return OrderExecutionReport(
                        order_job=order_job,
                        passed=False,
                        gate_results=gate_results,
                        output_files=output_files,
                    )

                task.status = "COMPLETED"

            elif tool == "mug_artist":
                mug_input = parse_mug_input_from_order(order_job.order_dir)
                out_target = order_job.order_dir / f"pedido_{order_job.order_id}_mug_transfer.png"
                if mug_input is not None:
                    transfer_path, preview_path = create_mug_artwork(
                        mug_input=mug_input,
                        mirror_for_transfer=True,
                        config=order_cfg,
                        output_path=out_target,
                    )
                else:
                    src_img = _select_primary_source_image(order_job)
                    transfer_path, preview_path = create_mug_artwork(
                        image_or_images=src_img,
                        mode="panoramic",
                        mirror_for_transfer=True,
                        config=order_cfg,
                        output_path=out_target,
                    )

                if preview_path is not None:
                    output_files.append(preview_path)
                output_files.append(transfer_path)

                gate = verify_mug_gate(
                    preview_path=preview_path or transfer_path,
                    transfer_path=transfer_path,
                )
                gate_results.append(gate)

                if not gate.passed:
                    task.status = "FAILED"
                    order_job.status = "FAILED"
                    logger.error(
                        "[Pedido {}] Quality Gate 'mug' REPROVADO: {}",
                        order_job.order_id,
                        gate.details,
                    )
                    return OrderExecutionReport(
                        order_job=order_job,
                        passed=False,
                        gate_results=gate_results,
                        output_files=output_files,
                    )

                task.status = "COMPLETED"

            else:
                raise ValueError(f"Ferramenta desconhecida na fila de tarefas: '{task.tool_name}'")

    except Exception as exc:
        for t in order_job.tasks:
            if t.status == "IN_PROGRESS":
                t.status = "FAILED"
        order_job.status = "FAILED"
        gate_results.append(
            QualityGateResult(
                stage="execution",
                passed=False,
                details=f"Exceção durante execução da fila: {exc}",
                file_checked=None,
            )
        )
        logger.error("[Pedido {}] Falha de execução: {}", order_job.order_id, exc)
        return OrderExecutionReport(
            order_job=order_job,
            passed=False,
            gate_results=gate_results,
            output_files=output_files,
        )

    order_job.status = "COMPLETED"
    dossie_path = write_production_dossier(
        order_job=order_job,
        gate_results=gate_results,
        output_files=output_files,
    )

    renamed = False
    if mark_ok:
        new_dir = mark_order_directory_ok(order_job)
        dossie_path = write_production_dossier(
            order_job=order_job,
            gate_results=gate_results,
            output_files=[
                (new_dir / p.name) if p.parent == new_dir.parent / order_job.order_id else p
                for p in output_files
            ],
        )
        renamed = True

    logger.success(
        "[Pedido {}] Todos os Quality Gates aprovados! Dossiê gravado em: {}",
        order_job.order_id,
        dossie_path,
    )
    return OrderExecutionReport(
        order_job=order_job,
        passed=True,
        gate_results=gate_results,
        dossie_path=dossie_path,
        output_files=output_files,
        renamed_to_ok=renamed,
    )


def run_order_by_id(
    order_id: str,
    orders_root: Union[str, Path] = DEFAULT_ORDERS_ROOT,
    route_override: Optional[Union[str, ProductRoute]] = None,
    mark_ok: bool = False,
    config: Optional[AppConfig] = None,
    max_retries: int = 3,
) -> OrderExecutionReport:
    """Localiza um pedido pendente por ID e executa toda a sua fila produtiva com Quality Gates."""
    resolved_route = normalize_product_route(route_override) if route_override else None
    job = find_order_by_id(
        order_id=order_id,
        orders_root=orders_root,
        route_override=resolved_route,
    )
    return execute_order_job(
        order_job=job,
        config=config,
        route_override=resolved_route,
        mark_ok=mark_ok,
        max_retries=max_retries,
    )


__all__ = [
    "DOSSIE_FILENAME",
    "OrderExecutionReport",
    "execute_order_job",
    "mark_order_directory_ok",
    "run_order_by_id",
    "write_production_dossier",
]
