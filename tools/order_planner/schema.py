"""Schemas Pydantic v2 para planejamento de pedidos, rotas de produção e Quality Gates (tools/order_planner/schema.py)."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductRoute(str, Enum):
    """Rotas físicas homologadas de produção da Studio Kustom.

    Atributos:
        UPSCALE_ONLY: Apenas upscaling 300 DPI sem imposição em folha.
        POSTER_FULL: Upscaling -> Expansão de Fundo (5mm se necessário) -> Folha com marcas de corte.
        CARD_TCG: card_generator -> print_sheet (folha Super A4 duplex 3x3).
        MUG_11OZ: mug_artist (layout 220x95mm -> saturação +18% -> transfer espelhado).
    """

    UPSCALE_ONLY = "UPSCALE_ONLY"
    POSTER_FULL = "POSTER_FULL"
    CARD_TCG = "CARD_TCG"
    MUG_11OZ = "MUG_11OZ"

    @classmethod
    def _missing_(cls, value: object) -> Optional["ProductRoute"]:
        """Permite resolução case-insensitive e aliases (ex: 'upscale_only', 'poster', 'card', 'mug')."""
        if not isinstance(value, str):
            return None
        cleaned = value.strip().upper().replace("-", "_").replace(" ", "_")
        aliases = {
            "UPSCALE_ONLY": cls.UPSCALE_ONLY,
            "UPSCALE": cls.UPSCALE_ONLY,
            "UP": cls.UPSCALE_ONLY,
            "POSTER_FULL": cls.POSTER_FULL,
            "POSTER": cls.POSTER_FULL,
            "PÔSTER": cls.POSTER_FULL,
            "QUADRO": cls.POSTER_FULL,
            "CARD_TCG": cls.CARD_TCG,
            "CARD": cls.CARD_TCG,
            "CARDS": cls.CARD_TCG,
            "TCG": cls.CARD_TCG,
            "CARTA": cls.CARD_TCG,
            "CARTAS": cls.CARD_TCG,
            "MUG_11OZ": cls.MUG_11OZ,
            "MUG": cls.MUG_11OZ,
            "CANECA": cls.MUG_11OZ,
            "CANECA_11OZ": cls.MUG_11OZ,
            "11OZ": cls.MUG_11OZ,
        }
        return aliases.get(cleaned)


def normalize_product_route(route: Union[str, ProductRoute]) -> ProductRoute:
    """Converte e valida uma string ou `ProductRoute` para o membro canônico do Enum."""
    if isinstance(route, ProductRoute):
        return route
    if not isinstance(route, str) or not route.strip():
        raise ValueError("A rota de produção ('route') deve ser uma string não vazia.")
    try:
        return ProductRoute(route)
    except ValueError as exc:
        valid = ", ".join(r.value.lower() for r in ProductRoute)
        raise ValueError(
            f"Rota de produção inválida: '{route}'. Rotas suportadas: {valid}."
        ) from exc


class QualityGateResult(BaseModel):
    """Resultado determinístico da avaliação de um Quality Gate da esteira produtiva.

    Atributos:
        stage: Etapa avaliada (ex: 'upscale', 'bleed', 'sheet', 'mug', 'card').
        passed: Indica se o artefato foi aprovado nos critérios físicos e digitais.
        details: Detalhamento técnico da inspeção ou motivo de reprovação.
        file_checked: Caminho opcional do arquivo inspecionado em disco.
    """

    model_config = ConfigDict(
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    stage: str = Field(..., description="Nome da etapa inspecionada pelo Quality Gate.")
    passed: bool = Field(..., description="True se o artefato passou no Quality Gate.")
    details: str = Field(..., description="Descrição técnica detalhada da verificação.")
    file_checked: Optional[Path] = Field(
        default=None,
        description="Caminho do arquivo inspecionado pelo Quality Gate.",
    )

    @field_validator("stage", "details", mode="before")
    @classmethod
    def _validate_non_empty_str(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Os campos 'stage' e 'details' devem ser strings não vazias.")
        return value.strip()

    @field_validator("file_checked", mode="before")
    @classmethod
    def _validate_optional_path(cls, value: Any) -> Optional[Path]:
        if value is None:
            return None
        if isinstance(value, (str, Path)):
            cleaned = str(value).strip()
            return Path(cleaned) if cleaned else None
        raise ValueError("O campo 'file_checked' deve ser um Path, string ou None.")


class TaskQueueItem(BaseModel):
    """Item individual da fila sequencial de atividades de um pedido.

    Atributos:
        step_number: Número sequencial do passo (iniciando em 1).
        tool_name: Nome da ferramenta a ser acionada ('upscaler', 'background_expander', 'print_sheet', 'card_generator', 'mug_artist').
        action_description: Descrição clara da ação operacional desta etapa.
        status: Estado atual da tarefa ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'SKIPPED').
        gate_criterion: Critério de aceite do Quality Gate associado a esta etapa.
    """

    model_config = ConfigDict(
        validate_assignment=True,
    )

    step_number: int = Field(..., ge=1, description="Ordem sequencial da tarefa (1..N).")
    tool_name: str = Field(..., description="Identificador da ferramenta sk-tools.")
    action_description: str = Field(..., description="Descrição da atividade na fila.")
    status: str = Field(
        default="PENDING",
        description="Status de execução da tarefa ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED').",
    )
    gate_criterion: str = Field(
        ...,
        description="Critério determinístico do Quality Gate para aprovação da etapa.",
    )

    @field_validator("tool_name", "action_description", "status", "gate_criterion", mode="before")
    @classmethod
    def _validate_text_fields(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Campos textuais de TaskQueueItem não podem ser vazios.")
        return value.strip()


class OrderJob(BaseModel):
    """Representação completa de um pedido da Studio Kustom e sua fila de produção.

    Atributos:
        order_id: Identificador do pedido (ex: '176', '169').
        order_dir: Caminho do diretório do pedido em disco.
        route: Rota produtiva atribuída (`ProductRoute`).
        customer_files: Lista de arquivos do cliente detectados na pasta (fotos, briefings, PDFs).
        tasks: Fila sequencial de tarefas (`TaskQueueItem`) planejadas para o pedido.
        status: Status global do pedido ('PENDING', 'PLANNED', 'IN_PROGRESS', 'COMPLETED', 'FAILED').
    """

    model_config = ConfigDict(
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    order_id: str = Field(..., description="Número ou código identificador do pedido.")
    order_dir: Path = Field(..., description="Diretório raiz do pedido.")
    route: ProductRoute = Field(..., description="Rota de produção definida para o pedido.")
    customer_files: List[Path] = Field(
        default_factory=list,
        description="Lista de arquivos originais do cliente presentes na pasta.",
    )
    tasks: List[TaskQueueItem] = Field(
        default_factory=list,
        description="Fila sequencial de tarefas de produção e seus Quality Gates.",
    )
    status: str = Field(
        default="PENDING",
        description="Status consolidado do pedido na esteira produtiva.",
    )

    @field_validator("order_id", "status", mode="before")
    @classmethod
    def _validate_id_and_status(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Os campos 'order_id' e 'status' devem ser strings não vazias.")
        return value.strip()

    @field_validator("order_dir", mode="before")
    @classmethod
    def _validate_order_dir(cls, value: Any) -> Path:
        if isinstance(value, (str, Path)):
            cleaned = str(value).strip()
            if not cleaned:
                raise ValueError("O caminho 'order_dir' não pode ser vazio.")
            return Path(cleaned)
        raise ValueError("O campo 'order_dir' deve ser um Path ou string.")

    @field_validator("route", mode="before")
    @classmethod
    def _validate_route(cls, value: Any) -> ProductRoute:
        return normalize_product_route(value)

    @field_validator("customer_files", mode="before")
    @classmethod
    def _validate_customer_files(cls, value: Any) -> List[Path]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("O campo 'customer_files' deve ser uma lista de caminhos.")
        return [Path(p) for p in value]


__all__ = [
    "OrderJob",
    "ProductRoute",
    "QualityGateResult",
    "TaskQueueItem",
    "normalize_product_route",
]
