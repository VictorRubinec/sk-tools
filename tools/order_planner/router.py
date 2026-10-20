"""Roteador de produção e construtor da fila de atividades com Quality Gates (tools/order_planner/router.py)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Union

from tools.order_planner.parser import deduce_product_route, infer_poster_format, read_order_briefing_text
from tools.order_planner.schema import (
    OrderJob,
    ProductRoute,
    TaskQueueItem,
    normalize_product_route,
)


def build_task_queue(
    route: Union[str, ProductRoute],
    target_format: str = "a3_v",
) -> List[TaskQueueItem]:
    """Constrói a fila sequencial de tarefas (`TaskQueueItem`) e seus Quality Gates para a rota informada.

    Args:
        route: Rota de produção (`ProductRoute` ou string equivalente).
        target_format: Formato de pôster aplicável às rotas `UPSCALE_ONLY` e `POSTER_FULL` (padrão: 'a3_v').

    Returns:
        Lista ordenada de `TaskQueueItem` com `step_number` sequencial (1..N).
    """
    resolved_route = normalize_product_route(route)
    fmt_upper = (target_format or "a3_v").strip().upper()

    if resolved_route == ProductRoute.UPSCALE_ONLY:
        return [
            TaskQueueItem(
                step_number=1,
                tool_name="upscaler",
                action_description=f"Upscaling 300 DPI ({fmt_upper}) sem imposição em folha",
                status="PENDING",
                gate_criterion=(
                    f"verify_upscale_gate: 300 DPI, resolução mínima ({fmt_upper}), sem pillarbox"
                ),
            ),
        ]

    if resolved_route == ProductRoute.POSTER_FULL:
        paper_code = "A3" if fmt_upper.startswith("A3") else "A4"
        return [
            TaskQueueItem(
                step_number=1,
                tool_name="upscaler",
                action_description=f"Upscaling da arte para pôster {fmt_upper} a 300 DPI",
                status="PENDING",
                gate_criterion=(
                    f"verify_upscale_gate: 300 DPI, resolução mínima ({fmt_upper}), sem pillarbox"
                ),
            ),
            TaskQueueItem(
                step_number=2,
                tool_name="background_expander",
                action_description="Expansão de fundo de 5mm (+59px por borda a 300 DPI)",
                status="PENDING",
                gate_criterion="verify_bleed_gate: confirma +59px por borda (+118px por eixo)",
            ),
            TaskQueueItem(
                step_number=3,
                tool_name="print_sheet",
                action_description=f"Imposição em folha {paper_code} com marcas de corte e registro",
                status="PENDING",
                gate_criterion="verify_sheet_gate: PDF válido com 1 página e dimensões da folha",
            ),
        ]

    if resolved_route == ProductRoute.CARD_TCG:
        return [
            TaskQueueItem(
                step_number=1,
                tool_name="card_generator",
                action_description="Geração e validação de carta(s) TCG a 300 DPI",
                status="PENDING",
                gate_criterion="verify_upscale_gate / card_validator: 300 DPI, sem pillarbox",
            ),
            TaskQueueItem(
                step_number=2,
                tool_name="print_sheet",
                action_description="Imposição em folha Super A4 duplex 3x3 (frente e verso espelhado)",
                status="PENDING",
                gate_criterion="verify_sheet_gate: PDF Super A4 duplex com páginas frente/verso",
            ),
        ]

    if resolved_route == ProductRoute.MUG_11OZ:
        return [
            TaskQueueItem(
                step_number=1,
                tool_name="mug_artist",
                action_description=(
                    "Composição de arte de caneca 11oz (layout 220x95mm -> saturação +18% -> transfer espelhado)"
                ),
                status="PENDING",
                gate_criterion="verify_mug_gate: 2598x1122px a 300 DPI e espelhamento horizontal",
            ),
        ]

    raise ValueError(f"Rota não suportada: {resolved_route}")  # pragma: no cover


def plan_order_job(
    order_job: OrderJob,
    route_override: Optional[Union[str, ProductRoute]] = None,
) -> OrderJob:
    """Deduz ou aplica `route_override` em um `OrderJob` e popula sua fila de tarefas (`tasks`)."""
    briefing_text = read_order_briefing_text(order_job.order_dir)
    resolved_route = (
        normalize_product_route(route_override)
        if route_override is not None
        else deduce_product_route(
            order_dir=order_job.order_dir,
            briefing_text=briefing_text,
            customer_files=order_job.customer_files,
        )
    )
    target_format = infer_poster_format(
        briefing_text=briefing_text,
        files=order_job.customer_files,
    )
    tasks = build_task_queue(route=resolved_route, target_format=target_format)
    order_job.route = resolved_route
    order_job.tasks = tasks
    return order_job


def create_order_job(
    order_id: str,
    order_dir: Union[str, Path],
    customer_files: Optional[Sequence[Path]] = None,
    route_override: Optional[Union[str, ProductRoute]] = None,
) -> OrderJob:
    """Cria uma instância planejada de `OrderJob` a partir do diretório e lista de arquivos."""
    dir_path = Path(order_dir)
    files_list = [Path(f) for f in (customer_files or [])]
    briefing_text = read_order_briefing_text(dir_path)
    route = deduce_product_route(
        order_dir=dir_path,
        briefing_text=briefing_text,
        customer_files=files_list,
        route_override=route_override,
    )
    target_format = infer_poster_format(briefing_text=briefing_text, files=files_list)
    tasks = build_task_queue(route=route, target_format=target_format)
    return OrderJob(
        order_id=str(order_id).strip(),
        order_dir=dir_path,
        route=route,
        customer_files=files_list,
        tasks=tasks,
        status="PENDING",
    )


__all__ = [
    "build_task_queue",
    "create_order_job",
    "plan_order_job",
]
