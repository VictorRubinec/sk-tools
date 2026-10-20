"""Fachada Pública (API) do módulo de planejamento e esteira de pedidos (tools/order_planner/api.py)."""

from __future__ import annotations

from tools.order_planner.card_backs import (
    DEFAULT_CARD_BACKS_DIR,
    resolve_card_back_by_game,
)
from tools.order_planner.orchestrator import (
    DOSSIE_FILENAME,
    OrderExecutionReport,
    execute_order_job,
    mark_order_directory_ok,
    run_order_by_id,
    write_production_dossier,
)
from tools.order_planner.parser import (
    ParsedOrderContext,
    deduce_product_route,
    infer_poster_format,
    parse_card_input_from_order,
    parse_mug_input_from_order,
    read_order_briefing_text,
)
from tools.order_planner.quality_gates import (
    BLEED_5MM_PX,
    verify_bleed_gate,
    verify_mug_gate,
    verify_sheet_gate,
    verify_upscale_gate,
)
from tools.order_planner.router import (
    build_task_queue,
    create_order_job,
    plan_order_job,
)
from tools.order_planner.scanner import (
    DEFAULT_ORDERS_ROOT,
    OrderFileCatalog,
    catalog_order_files,
    discover_orders,
    find_order_by_id,
    is_cancelled_order_dir,
    is_finished_order_dir,
    should_ignore_order_dir,
)
from tools.order_planner.schema import (
    OrderJob,
    ProductRoute,
    QualityGateResult,
    TaskQueueItem,
    normalize_product_route,
)

__all__ = [
    "BLEED_5MM_PX",
    "DEFAULT_CARD_BACKS_DIR",
    "DEFAULT_ORDERS_ROOT",
    "DOSSIE_FILENAME",
    "OrderExecutionReport",
    "OrderFileCatalog",
    "OrderJob",
    "ParsedOrderContext",
    "ProductRoute",
    "QualityGateResult",
    "TaskQueueItem",
    "build_task_queue",
    "catalog_order_files",
    "create_order_job",
    "deduce_product_route",
    "discover_orders",
    "execute_order_job",
    "find_order_by_id",
    "infer_poster_format",
    "is_cancelled_order_dir",
    "is_finished_order_dir",
    "mark_order_directory_ok",
    "normalize_product_route",
    "parse_card_input_from_order",
    "parse_mug_input_from_order",
    "plan_order_job",
    "read_order_briefing_text",
    "resolve_card_back_by_game",
    "run_order_by_id",
    "should_ignore_order_dir",
    "verify_bleed_gate",
    "verify_mug_gate",
    "verify_sheet_gate",
    "verify_upscale_gate",
    "write_production_dossier",
]
