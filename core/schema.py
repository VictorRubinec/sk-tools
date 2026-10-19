"""Schemas Pydantic para validação rigorosa de dados de entrada de cartas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.config import BASE_DIR

STANDARD_CARD_TYPES: Final[dict[str, str]] = {
    "magic": "Magic",
    "mtg": "Magic",
    "pokemon": "Pokemon",
    "pokémon": "Pokemon",
    "yu-gi-oh!": "Yu-Gi-Oh!",
    "yu-gi-oh": "Yu-Gi-Oh!",
    "yugioh": "Yu-Gi-Oh!",
    "one piece": "One Piece",
    "onepiece": "One Piece",
}

STANDARD_CARD_STYLES: Final[dict[str, str]] = {
    "normal": "Normal",
    "fullart": "Fullart",
    "full art": "Fullart",
    "full-art": "Fullart",
    "alternative": "Alternative",
}


class CardInput(BaseModel):
    """Modelo de entrada e validação para geração e processamento de uma carta.

    Atributos:
        tipo: Jogo ou sistema da carta (ex: "Magic", "Pokemon", "Yu-Gi-Oh!",
            "One Piece" ou tipo customizado não vazio).
        estilo: Estilo visual da carta (ex: "Normal", "Fullart", "Alternative"
            ou estilo customizado não vazio).
        titulo: Nome ou título principal da carta (obrigatório, não vazio).
        descricao: Descrição visual da cena/arte ou efeito da carta (opcional).
        texto_adicional: Textos extras como flavor text, regras ou atributos (opcional).
        cores: Cor única (string) ou lista de cores associadas à carta (opcional).
        imagens_referencia: Lista de caminhos para arquivos de imagem de referência (opcional).
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=False,
        validate_assignment=True,
    )

    tipo: str = Field(
        ...,
        description='Tipo de jogo da carta ("Magic", "Pokemon", "Yu-Gi-Oh!", "One Piece" ou customizado).',
    )
    estilo: str = Field(
        ...,
        description='Estilo da carta (ex: "Normal", "Fullart", "Alternative").',
    )
    titulo: str = Field(
        ...,
        description="Título da carta (string não vazia).",
    )
    descricao: Optional[str] = Field(
        default=None,
        description="Descrição da arte ou efeito da carta (opcional).",
    )
    texto_adicional: Optional[str] = Field(
        default=None,
        description="Texto adicional, flavor text ou observações da carta (opcional).",
    )
    cores: Optional[Union[str, List[str]]] = Field(
        default=None,
        description="Cor ou lista de cores da carta (opcional).",
    )
    imagens_referencia: Optional[List[str]] = Field(
        default=None,
        description="Lista opcional de caminhos de imagens de referência existentes em disco.",
    )

    @field_validator("tipo", mode="before")
    @classmethod
    def validate_tipo(cls, value: Any) -> str:
        """Valida e normaliza o campo 'tipo', garantindo string não vazia."""
        if not isinstance(value, str):
            raise ValueError("O campo 'tipo' deve ser uma string.")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("O campo 'tipo' é obrigatório e não pode ser vazio.")
        return STANDARD_CARD_TYPES.get(cleaned.lower(), cleaned)

    @field_validator("estilo", mode="before")
    @classmethod
    def validate_estilo(cls, value: Any) -> str:
        """Valida e normaliza o campo 'estilo', garantindo string não vazia."""
        if not isinstance(value, str):
            raise ValueError("O campo 'estilo' deve ser uma string.")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("O campo 'estilo' é obrigatório e não pode ser vazio.")
        return STANDARD_CARD_STYLES.get(cleaned.lower(), cleaned)

    @field_validator("titulo", mode="before")
    @classmethod
    def validate_titulo(cls, value: Any) -> str:
        """Valida que o título é uma string não vazia."""
        if not isinstance(value, str):
            raise ValueError("O campo 'titulo' deve ser uma string.")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("O campo 'titulo' é obrigatório e não pode ser vazio.")
        return cleaned

    @field_validator("descricao", "texto_adicional", mode="before")
    @classmethod
    def validate_optional_text(cls, value: Any) -> Optional[str]:
        """Valida campos opcionais de texto, removendo espaços excedentes."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Os campos opcionais de texto devem ser strings.")
        cleaned = value.strip()
        return cleaned if cleaned else None

    @field_validator("cores", mode="before")
    @classmethod
    def validate_cores(cls, value: Any) -> Optional[Union[str, List[str]]]:
        """Valida que 'cores' seja None, uma string não vazia ou lista de strings não vazias."""
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                raise ValueError("O campo 'cores' não pode ser uma string vazia.")
            return cleaned
        if isinstance(value, list):
            if not value:
                raise ValueError("A lista em 'cores' não pode estar vazia.")
            cleaned_list: List[str] = []
            for idx, item in enumerate(value):
                if not isinstance(item, str):
                    raise ValueError(
                        f"O item na posição {idx} de 'cores' deve ser uma string."
                    )
                stripped_item = item.strip()
                if not stripped_item:
                    raise ValueError(
                        f"O item na posição {idx} de 'cores' não pode ser vazio."
                    )
                cleaned_list.append(stripped_item)
            return cleaned_list
        raise ValueError(
            "O campo 'cores' deve ser uma string ou uma lista de strings."
        )

    @field_validator("imagens_referencia", mode="before")
    @classmethod
    def validate_imagens_referencia(cls, value: Any) -> Optional[List[str]]:
        """Valida se os caminhos de 'imagens_referencia' são strings válidas e existem em disco."""
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError(
                "O campo 'imagens_referencia' deve ser uma lista de strings."
            )
        if not value:
            return None

        validated_paths: List[str] = []
        for idx, item in enumerate(value):
            if not isinstance(item, str):
                raise ValueError(
                    f"O caminho na posição {idx} de 'imagens_referencia' deve ser uma string."
                )
            cleaned = item.strip()
            if not cleaned:
                raise ValueError(
                    f"O caminho na posição {idx} de 'imagens_referencia' não pode ser vazio."
                )

            candidate = Path(cleaned)
            resolved = candidate if candidate.is_file() else (BASE_DIR / candidate)
            if not resolved.is_file():
                raise ValueError(
                    f"Arquivo de imagem de referência não encontrado em disco: '{cleaned}'"
                )
            validated_paths.append(cleaned)

        return validated_paths

    @property
    def is_standard_type(self) -> bool:
        """Indica se o tipo da carta pertence à lista de jogos padrão."""
        return self.tipo in set(STANDARD_CARD_TYPES.values())

    @property
    def cores_lista(self) -> List[str]:
        """Retorna as cores normalizadas sempre como uma lista de strings."""
        if self.cores is None:
            return []
        if isinstance(self.cores, str):
            return [c.strip() for c in self.cores.split(",") if c.strip()]
        return list(self.cores)


def load_cards_from_file(file_path: Union[str, Path]) -> List[CardInput]:
    """Carrega e valida um arquivo JSON contendo um único objeto ou lista de cartas.

    Args:
        file_path: Caminho para o arquivo JSON de entrada.

    Returns:
        Lista de instâncias validadas de `CardInput`.

    Raises:
        FileNotFoundError: Se o arquivo não existir.
        ValueError: Se o JSON for inválido ou tiver estrutura incompatível.
        pydantic.ValidationError: Se os dados de alguma carta forem inválidos.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo de entrada não encontrado: {path}")

    raw_text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido no arquivo '{path}': {exc}") from exc

    if isinstance(payload, dict):
        return [CardInput.model_validate(payload)]
    if isinstance(payload, list):
        if not payload:
            raise ValueError(f"A lista de cartas no arquivo '{path}' está vazia.")
        return [CardInput.model_validate(item) for item in payload]

    raise ValueError(
        f"Formato JSON inesperado em '{path}': esperado objeto ou lista de objetos."
    )
