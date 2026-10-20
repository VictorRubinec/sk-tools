"""Scanner de diretórios de pedidos e catalogador de arquivos do cliente (tools/order_planner/scanner.py)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

from tools.order_planner.parser import is_generated_artifact
from tools.order_planner.router import create_order_job
from tools.order_planner.schema import OrderJob, ProductRoute

DEFAULT_ORDERS_ROOT: Path = Path(r"D:\Desktop\Studio Kustom\04 - Pedidos e Historico\Pedidos")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
BRIEFING_EXTENSIONS = {".txt", ".json"}
PDF_EXTENSIONS = {".pdf"}


@dataclass
class OrderFileCatalog:
    """Catálogo classificado dos arquivos presentes na pasta de um pedido."""

    photos: List[Path] = field(default_factory=list)
    briefings: List[Path] = field(default_factory=list)
    shipping_pdfs: List[Path] = field(default_factory=list)

    @property
    def all_files(self) -> List[Path]:
        """Retorna todos os arquivos catalogados do cliente na ordem: fotos, briefings e PDFs."""
        return [*self.photos, *self.briefings, *self.shipping_pdfs]


def is_finished_order_dir(folder: Union[str, Path]) -> bool:
    """Retorna True se o nome da pasta possuir o sufixo `- ok` (pedido já finalizado)."""
    name = Path(folder).name.strip().lower()
    return bool(re.search(r"-\s*ok$", name))


def is_cancelled_order_dir(folder: Union[str, Path]) -> bool:
    """Retorna True se o nome da pasta possuir o sufixo `- cancelado` ou `- c` (pedido cancelado)."""
    name = Path(folder).name.strip().lower()
    return bool(re.search(r"-\s*(?:cancelado|c)$", name))


def should_ignore_order_dir(folder: Union[str, Path]) -> bool:
    """Retorna True se o diretório do pedido deve ser ignorado (finalizado com `- ok` ou cancelado com `- cancelado` / `- c`)."""
    return is_finished_order_dir(folder) or is_cancelled_order_dir(folder)


def catalog_order_files(order_dir: Union[str, Path]) -> OrderFileCatalog:
    """Cataloga os arquivos do cliente presentes na pasta do pedido (fotos, briefings e PDFs).

    Reconhece fotos do cliente (`foto*.jpg`, `br-11134231*.jpg`, `.png`, `.webp`),
    arquivos de briefing (`texto.txt`, `.txt`, `.json`) e PDFs de envio (`.pdf`),
    ignorando artefatos gerados anteriormente pela própria esteira (`dossie_producao.json`, `*_sheet_*.pdf`, etc.).
    """
    dir_path = Path(order_dir)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"Diretório do pedido não encontrado: {dir_path}")

    catalog = OrderFileCatalog()
    for item in sorted(dir_path.iterdir()):
        if not item.is_file() or item.name.startswith("."):
            continue
        if is_generated_artifact(item):
            continue

        suffix = item.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            catalog.photos.append(item)
        elif suffix in BRIEFING_EXTENSIONS:
            catalog.briefings.append(item)
        elif suffix in PDF_EXTENSIONS:
            catalog.shipping_pdfs.append(item)

    return catalog


def discover_orders(
    orders_root: Union[str, Path] = DEFAULT_ORDERS_ROOT,
    route_override: Optional[Union[str, ProductRoute]] = None,
) -> List[OrderJob]:
    """Varre a pasta raiz de pedidos, ignora pastas `- ok` e retorna a lista planejada de `OrderJob`.

    Args:
        orders_root: Caminho raiz dos pedidos (padrão: `D:\\Desktop\\Studio Kustom\\04 - Pedidos e Historico\\Pedidos`).
        route_override: Rota explícita opcional para forçar em todos os pedidos descobertos.

    Returns:
        Lista de `OrderJob` pendentes ordenados por identificador.
    """
    root_path = Path(orders_root)
    if not root_path.is_dir():
        raise FileNotFoundError(f"Diretório raiz de pedidos não encontrado: {root_path}")

    jobs: List[OrderJob] = []
    for entry in sorted(root_path.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if should_ignore_order_dir(entry):
            continue

        catalog = catalog_order_files(entry)
        job = create_order_job(
            order_id=entry.name,
            order_dir=entry,
            customer_files=catalog.all_files,
            route_override=route_override,
        )
        jobs.append(job)

    return jobs


def find_order_by_id(
    order_id: str,
    orders_root: Union[str, Path] = DEFAULT_ORDERS_ROOT,
    route_override: Optional[Union[str, ProductRoute]] = None,
) -> OrderJob:
    """Localiza um pedido pendente pelo seu `order_id` dentro de `orders_root`.

    Aceita correspondência exata do nome da pasta (ex: `'176'`, `'115 - c'`) ou
    pelo prefixo numérico do pedido (ex: `'115'` para `'115 - c'`).
    """
    target = str(order_id).strip()
    if not target:
        raise ValueError("O identificador do pedido ('order_id') não pode ser vazio.")

    jobs = discover_orders(orders_root=orders_root, route_override=route_override)
    target_lower = target.lower()

    for job in jobs:
        if job.order_id.lower() == target_lower:
            return job

    for job in jobs:
        prefix = job.order_id.split("-")[0].strip().lower()
        if prefix == target_lower or (
            prefix.isdigit() and target_lower.isdigit() and int(prefix) == int(target_lower)
        ):
            return job

    raise FileNotFoundError(
        f"Pedido pendente '{order_id}' não encontrado em '{orders_root}'."
    )


__all__ = [
    "DEFAULT_ORDERS_ROOT",
    "OrderFileCatalog",
    "catalog_order_files",
    "discover_orders",
    "find_order_by_id",
    "is_cancelled_order_dir",
    "is_finished_order_dir",
    "should_ignore_order_dir",
]
