"""Schemas Pydantic para validação rigorosa de parâmetros de entrada de canecas 11oz."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Final, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tools.card_generator.core.config import BASE_DIR

STANDARD_MUG_THEMES: Final[dict[str, str]] = {
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

STANDARD_MUG_STYLES: Final[dict[str, str]] = {
    "panoramico": "Panoramico",
    "panorâmico": "Panoramico",
    "panoramic": "Panoramico",
    "dual face": "Dual Face",
    "dual_face": "Dual Face",
    "dual-face": "Dual Face",
    "dual": "Dual Face",
    "card + mensagem": "Card + Mensagem",
    "card+mensagem": "Card + Mensagem",
    "card + message": "Card + Mensagem",
    "card_plus_text": "Card + Mensagem",
    "card_plus_message": "Card + Mensagem",
    "card + texto": "Card + Mensagem",
    "card+texto": "Card + Mensagem",
    "mensagem": "Card + Mensagem",
    "text": "Card + Mensagem",
}


def slugify(text: str) -> str:
    """Converte um texto arbitrário em identificador seguro para nome de arquivo."""
    normalized = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    return slug or "mug"


class MugInput(BaseModel):
    """Modelo de entrada e validação para geração de arte de caneca 11oz via Gemini Web.

    Atributos:
        tema: Tema ou universo da caneca (ex: "Magic", "Pokemon", "Yu-Gi-Oh!", "One Piece" ou customizado).
        estilo: Estilo de layout da caneca ("Panoramico", "Dual Face", "Card + Mensagem").
        titulo: Nome ou título principal da arte da caneca.
        descricao: Descrição visual da cena ou composição artística desejada (opcional).
        mensagem: Frase, dedicatória ou texto comemorativo impresso na arte (opcional).
        cores: Cor única ou lista de cores principais da paleta da caneca (opcional).
        imagens_referencia: Lista opcional de caminhos para arquivos de referência existentes em disco.
        espelhar_transfer: Se True (padrão), gera a versão espelhada horizontalmente para sublimação.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=False,
        validate_assignment=True,
    )

    tema: str = Field(
        ...,
        description='Tema ou universo da caneca ("Magic", "Pokemon", "Yu-Gi-Oh!", "One Piece" ou customizado).',
    )
    estilo: str = Field(
        ...,
        description='Estilo de layout da caneca ("Panoramico", "Dual Face", "Card + Mensagem").',
    )
    titulo: str = Field(
        ...,
        description="Título ou identificador da arte da caneca (string não vazia).",
    )
    descricao: Optional[str] = Field(
        default=None,
        description="Descrição da cena, arte e composição visual (opcional).",
    )
    mensagem: Optional[str] = Field(
        default=None,
        description="Mensagem comemorativa, frase especial ou dedicatória (opcional).",
    )
    cores: Optional[Union[str, List[str]]] = Field(
        default=None,
        description="Cor única ou lista de cores da paleta visual da caneca (opcional).",
    )
    imagens_referencia: Optional[List[str]] = Field(
        default=None,
        description="Lista opcional de caminhos de imagens de referência existentes em disco.",
    )
    espelhar_transfer: bool = Field(
        default=True,
        description="Se True, gera a imagem espelhada horizontalmente para prensa de sublimação.",
    )

    @field_validator("tema", mode="before")
    @classmethod
    def validate_tema(cls, value: Any) -> str:
        """Valida e normaliza o tema da caneca, garantindo string não vazia."""
        if not isinstance(value, str):
            raise ValueError("O campo 'tema' deve ser uma string.")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("O campo 'tema' é obrigatório e não pode ser vazio.")
        return STANDARD_MUG_THEMES.get(cleaned.lower(), cleaned)

    @field_validator("estilo", mode="before")
    @classmethod
    def validate_estilo(cls, value: Any) -> str:
        """Valida e normaliza o estilo da caneca para 'Panoramico', 'Dual Face' ou 'Card + Mensagem'."""
        if not isinstance(value, str):
            raise ValueError("O campo 'estilo' deve ser uma string.")
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("O campo 'estilo' é obrigatório e não pode ser vazio.")

        normalized = STANDARD_MUG_STYLES.get(cleaned.lower())
        if normalized:
            return normalized

        # Se já estiver em uma das formas canônicas exatas ou variação com casing
        for canonical in ("Panoramico", "Dual Face", "Card + Mensagem"):
            if cleaned.lower() == canonical.lower():
                return canonical

        valid_options = ["Panoramico", "Dual Face", "Card + Mensagem"]
        raise ValueError(
            f"Estilo inválido '{cleaned}'. Escolha entre: {', '.join(valid_options)}."
        )

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

    @field_validator("descricao", "mensagem", mode="before")
    @classmethod
    def validate_optional_text(cls, value: Any) -> Optional[str]:
        """Valida campos opcionais de texto, removendo espaços excedentes."""
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Campos de texto opcionais devem ser strings.")
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
                stripped = item.strip()
                if not stripped:
                    raise ValueError(
                        f"O item na posição {idx} de 'cores' não pode ser vazio."
                    )
                cleaned_list.append(stripped)
            return cleaned_list
        raise ValueError("O campo 'cores' deve ser uma string ou lista de strings.")

    @field_validator("imagens_referencia", mode="before")
    @classmethod
    def validate_imagens_referencia(cls, value: Any) -> Optional[List[str]]:
        """Valida se os caminhos de 'imagens_referencia' existem em disco."""
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("O campo 'imagens_referencia' deve ser uma lista de strings.")
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
    def cores_lista(self) -> List[str]:
        """Retorna as cores normalizadas sempre como uma lista de strings."""
        if self.cores is None:
            return []
        if isinstance(self.cores, str):
            return [c.strip() for c in self.cores.split(",") if c.strip()]
        return list(self.cores)

    @property
    def slug(self) -> str:
        """Gera um slug seguro combinando tema e título para nome de arquivo."""
        return f"{slugify(self.tema)}_{slugify(self.titulo)}"


def load_mugs_from_file(file_path: Union[str, Path]) -> List[MugInput]:
    """Carrega e valida um arquivo JSON contendo uma única especificação ou lista de canecas.

    Args:
        file_path: Caminho para o arquivo JSON de entrada.

    Returns:
        Lista de instâncias validadas de `MugInput`.

    Raises:
        FileNotFoundError: Se o arquivo não existir.
        ValueError: Se o JSON for inválido ou tiver estrutura incompatível.
        pydantic.ValidationError: Se os dados de alguma caneca forem inválidos.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo de entrada de canecas não encontrado: {path}")

    raw_text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido no arquivo '{path}': {exc}") from exc

    if isinstance(payload, dict):
        return [MugInput.model_validate(payload)]
    if isinstance(payload, list):
        if not payload:
            raise ValueError(f"A lista de canecas no arquivo '{path}' está vazia.")
        return [MugInput.model_validate(item) for item in payload]

    raise ValueError(
        f"Formato JSON inesperado em '{path}': esperado objeto ou lista de objetos."
    )
