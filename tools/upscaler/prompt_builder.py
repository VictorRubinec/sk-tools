"""Especificações físicas (300 DPI) e construtor de prompts de redraw/super-resolução para posters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Final, Optional


@dataclass(frozen=True)
class PosterFormatSpec:
    """Especificação física e digital rigorosa de um formato de poster da Studio Kustom (300 DPI)."""

    code: str
    label: str
    width_mm: int
    height_mm: int
    width_px: int
    height_px: int
    orientation: str  # "vertical" ou "horizontal"
    dpi: int = 300

    @property
    def aspect_ratio(self) -> float:
        """Retorna a razão altura / largura arredondada em 3 casas decimais."""
        return round(self.height_px / self.width_px, 3)


POSTER_FORMATS: Final[Dict[str, PosterFormatSpec]] = {
    "A4_V": PosterFormatSpec(
        code="A4_V",
        label="A4 Vertical",
        width_mm=210,
        height_mm=300,
        width_px=2480,
        height_px=3543,
        orientation="vertical",
    ),
    "A4_H": PosterFormatSpec(
        code="A4_H",
        label="A4 Horizontal",
        width_mm=300,
        height_mm=210,
        width_px=3543,
        height_px=2480,
        orientation="horizontal",
    ),
    "A3_V": PosterFormatSpec(
        code="A3_V",
        label="A3 Vertical",
        width_mm=300,
        height_mm=420,
        width_px=3543,
        height_px=4960,
        orientation="vertical",
    ),
    "A3_H": PosterFormatSpec(
        code="A3_H",
        label="A3 Horizontal",
        width_mm=420,
        height_mm=300,
        width_px=4960,
        height_px=3543,
        orientation="horizontal",
    ),
}


def normalize_target_format(target_format: str) -> PosterFormatSpec:
    """Normaliza e valida o código do formato alvo ('a4_v', 'a4_h', 'a3_v', 'a3_h').

    Args:
        target_format: String identificadora do formato.

    Returns:
        Instância correspondente de `PosterFormatSpec`.

    Raises:
        ValueError: Se o formato informado não for suportado.
    """
    if not isinstance(target_format, str) or not target_format.strip():
        raise ValueError("O formato alvo ('target_format') deve ser uma string não vazia.")

    normalized = target_format.strip().upper().replace("-", "_")
    if normalized not in POSTER_FORMATS:
        valid_keys = ", ".join(sorted(POSTER_FORMATS.keys()))
        raise ValueError(
            f"Formato de poster inválido: '{target_format}'. Formatos suportados: {valid_keys}."
        )
    return POSTER_FORMATS[normalized]


class UpscalePromptBuilder:
    """Constrói prompts de redraw e super-resolução para conversão em poster no Gemini."""

    AI_ROLE: str = (
        "Você é um artista digital sênior especialista em restauração, redraw de altíssima definição "
        "e super-resolução para impressão fine-art (300 DPI) do estúdio Studio Kustom."
    )

    def build_prompt(
        self,
        target_format: str,
        extra_instructions: Optional[str] = None,
    ) -> str:
        """Gera o prompt estruturado de upscale/redraw para o formato de poster desejado.

        Args:
            target_format: Código do formato ('A4_V', 'A4_H', 'A3_V', 'A3_H').
            extra_instructions: Instruções complementares opcionais (ex: reforço em retentativas).

        Returns:
            Texto completo do prompt para envio ao Google Gemini junto à imagem original anexa.
        """
        spec = normalize_target_format(target_format)

        orientation_desc = (
            "estritamente VERTICAL (retrato, altura maior que largura)"
            if spec.orientation == "vertical"
            else "estritamente HORIZONTAL (paisagem, largura maior que altura)"
        )

        sections = [
            f"[PAPEL DA IA]\n{self.AI_ROLE}",
            (
                "[INSTRUÇÃO PRINCIPAL DE REDRAW E SUPER-RESOLUÇÃO]\n"
                f"Realize o redraw e upscaling de altíssima fidelidade da imagem anexa para o formato "
                f"de poster '{spec.label}' ({spec.code}), projetado para impressão em {spec.dpi} DPI "
                f"({spec.width_mm}x{spec.height_mm} mm / {spec.width_px}x{spec.height_px} px, "
                f"aspect ratio altura/largura ~{spec.aspect_ratio:.3f})."
            ),
            (
                "[PRESERVAÇÃO DE FISIONOMIA E ELEMENTOS ORIGINAIS]\n"
                "- Preserve estritamente a fisionomia dos rostos, expressões faciais, anatomia, poses, "
                "vestimentas, tipografia e todos os elementos visuais da ilustração original anexa.\n"
                "- Não altere a identidade visual do personagem nem substitua os elementos centrais da carta/arte."
            ),
            (
                "[QUALIDADE DE ESTÚDIO E RECONSTRUÇÃO DE TRAÇOS]\n"
                "- Reconstrua traços nítidos, contornos precisos e microtexturas de altíssima definição.\n"
                "- Aplique acabamento de pintura de estúdio profissional com iluminação e gradação suaves.\n"
                "- Remova integralmente ruídos digitais, serrilhados (aliasing), borrões e artefatos de compressão."
            ),
            (
                "[ENQUADRAMENTO E PROPORÇÃO DO POSTER]\n"
                f"- Formato Físico Alvo: {spec.label} ({spec.width_mm} x {spec.height_mm} mm a {spec.dpi} DPI).\n"
                f"- Resolução Alvo: {spec.width_px} x {spec.height_px} pixels (orientação {orientation_desc}).\n"
                "- Adapte o enquadramento de forma harmoniosa para preencher integralmente a área do poster, "
                "sem cortes abruptos em personagens, bordas ou elementos importantes."
            ),
        ]

        if extra_instructions and extra_instructions.strip():
            sections.append(
                f"[DIRETRIZES COMPLEMENTARES DE CORREÇÃO]\n{extra_instructions.strip()}"
            )

        sections.append(
            "[RESTRIÇÕES NEGATIVAS OBRIGATÓRIAS]\n"
            "Evite estritamente: sem perda de semelhança facial; sem ruídos digitais ou pixelização; "
            "sem dedos ou membros deformados; sem textos ilegíveis ou distorcidos; "
            "sem bordas brancas externas ou cortes indevidos na composição."
        )

        return "\n\n".join(sections)
