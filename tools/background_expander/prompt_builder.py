"""Cálculo de sangria (bleed 300 DPI) e construtor de prompts de outpainting (tools/background_expander)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Final, Optional, Tuple

DEFAULT_DPI: Final[int] = 300
DEFAULT_BLEED_MM: Final[float] = 5.0
MM_PER_INCH: Final[float] = 25.4


@dataclass(frozen=True)
class ExpansionModeSpec:
    """Especificação de um modo de expansão generativa de fundo (outpainting)."""

    code: str
    label: str
    description: str
    requires_horizontal_orientation: bool = False


EXPANSION_MODES: Final[Dict[str, ExpansionModeSpec]] = {
    "bleed_5mm": ExpansionModeSpec(
        code="bleed_5mm",
        label="Sangria de Segurança (Bleed 4 Bordas)",
        description=(
            "Adiciona margem generativa uniforme em todas as 4 bordas (esquerda, direita, topo e base) "
            "para segurança de corte em guilhotina e prensa térmica, mantendo a composição original intacta no centro."
        ),
        requires_horizontal_orientation=False,
    ),
    "horizontal": ExpansionModeSpec(
        code="horizontal",
        label="Expansão Panorâmica Horizontal (Poster 300x210mm)",
        description=(
            "Estende panoramicamente as laterais esquerda e direita do cenário para converter a composição "
            "em orientação horizontal (paisagem), preservando o personagem/elemento central sem cortes ou distorções."
        ),
        requires_horizontal_orientation=True,
    ),
    "caneca": ExpansionModeSpec(
        code="caneca",
        label="Expansão Panorâmica para Sublimação (Caneca/Cilíndrico)",
        description=(
            "Estende amplamente as laterais esquerda e direita do ambiente de fundo em formato panorâmico "
            "horizontal contínuo, mantendo o personagem centralizado e íntegro com margem de sangria."
        ),
        requires_horizontal_orientation=True,
    ),
    "custom": ExpansionModeSpec(
        code="custom",
        label="Expansão Generativa Customizada",
        description=(
            "Expande o cenário de fundo ao redor da arte original conforme as dimensões e proporções alvo "
            "especificadas, preservando integralmente o sujeito central."
        ),
        requires_horizontal_orientation=False,
    ),
}


def calculate_bleed_pixels(bleed_mm: float = DEFAULT_BLEED_MM, dpi: int = DEFAULT_DPI) -> int:
    """Calcula a quantidade exata de pixels correspondente à margem em milímetros para o DPI informado.

    A 300 DPI, 5.0 mm = round((5.0 / 25.4) * 300) = 59 pixels por borda.

    Args:
        bleed_mm: Margem de sangria em milímetros por borda.
        dpi: Resolução de impressão em pontos por polegada (padrão: 300).

    Returns:
        Quantidade de pixels por borda (inteiro).

    Raises:
        ValueError: Se `bleed_mm` for negativo ou `dpi` for menor ou igual a zero.
    """
    if bleed_mm < 0:
        raise ValueError("O valor de sangria ('bleed_mm') não pode ser negativo.")
    if dpi <= 0:
        raise ValueError("O valor de 'dpi' deve ser maior que zero.")
    return int(round((bleed_mm / MM_PER_INCH) * dpi))


def normalize_expansion_mode(mode: str) -> ExpansionModeSpec:
    """Normaliza e valida o modo de expansão solicitado.

    Args:
        mode: Nome do modo ('bleed_5mm', 'horizontal', 'caneca', 'custom').

    Returns:
        Instância correspondente de `ExpansionModeSpec`.

    Raises:
        ValueError: Se o modo não for reconhecido.
    """
    if not isinstance(mode, str) or not mode.strip():
        raise ValueError("O modo de expansão ('mode') deve ser uma string não vazia.")

    cleaned = mode.strip().lower().replace("-", "_")
    aliases = {
        "bleed": "bleed_5mm",
        "5mm": "bleed_5mm",
        "mug": "caneca",
        "landscape": "horizontal",
    }
    resolved_key = aliases.get(cleaned, cleaned)
    if resolved_key not in EXPANSION_MODES:
        valid_modes = ", ".join(sorted(EXPANSION_MODES.keys()))
        raise ValueError(
            f"Modo de expansão inválido: '{mode}'. Modos suportados: {valid_modes}."
        )
    return EXPANSION_MODES[resolved_key]


def calculate_expanded_dimensions(
    base_width: int,
    base_height: int,
    mode: str = "bleed_5mm",
    bleed_mm: float = DEFAULT_BLEED_MM,
    dpi: int = DEFAULT_DPI,
    custom_size: Optional[Tuple[int, int]] = None,
) -> Tuple[int, int, int]:
    """Calcula as dimensões finais (largura, altura, bleed_px_por_borda) após aplicar a expansão.

    Args:
        base_width: Largura da imagem original em pixels.
        base_height: Altura da imagem original em pixels.
        mode: Modo de expansão ('bleed_5mm', 'horizontal', 'caneca', 'custom').
        bleed_mm: Milímetros de margem por borda (padrão: 5.0 mm = 59 px a 300 DPI).
        dpi: Resolução em DPI (padrão: 300).
        custom_size: Tupla opcional `(largura_base, altura_base)` para o modo `custom`.

    Returns:
        Tupla `(target_width, target_height, bleed_px)`.
    """
    if base_width <= 0 or base_height <= 0:
        raise ValueError("As dimensões base da imagem devem ser maiores que zero.")

    spec = normalize_expansion_mode(mode)
    bleed_px = calculate_bleed_pixels(bleed_mm=bleed_mm, dpi=dpi)

    if spec.code == "custom" and custom_size is not None:
        cw, ch = custom_size
        if cw <= 0 or ch <= 0:
            raise ValueError("As dimensões customizadas devem ser maiores que zero.")
        return cw + (2 * bleed_px), ch + (2 * bleed_px), bleed_px

    if spec.requires_horizontal_orientation:
        # Converte para proporção horizontal panorâmica (mínimo 300:210 ~ 1.4286x da altura) + sangria
        panoramic_base_w = max(base_width, int(round(base_height * (300.0 / 210.0))))
        if panoramic_base_w <= base_height:
            panoramic_base_w = base_height + 200
        return panoramic_base_w + (2 * bleed_px), base_height + (2 * bleed_px), bleed_px

    # Modo padrão bleed_5mm (ou custom sem custom_size explícito)
    return base_width + (2 * bleed_px), base_height + (2 * bleed_px), bleed_px


class BackgroundExpansionPromptBuilder:
    """Constrói prompts de outpainting (expansão generativa de cenário) para o Google Gemini."""

    AI_ROLE: str = (
        "Você é um artista digital sênior especialista em outpainting (expansão generativa de cenários) "
        "e pré-impressão gráfica a 300 DPI do estúdio Studio Kustom."
    )

    def build_prompt(
        self,
        mode: str = "bleed_5mm",
        bleed_mm: float = DEFAULT_BLEED_MM,
        base_size: Optional[Tuple[int, int]] = None,
        custom_size: Optional[Tuple[int, int]] = None,
        extra_instructions: Optional[str] = None,
    ) -> str:
        """Monta o prompt estruturado de expansão de fundo para envio ao Gemini.

        Args:
            mode: Modo de expansão ('bleed_5mm', 'horizontal', 'caneca', 'custom').
            bleed_mm: Margem de sangria por borda em milímetros (padrão: 5.0).
            base_size: Dimensões `(width, height)` da imagem original, se conhecidas.
            custom_size: Dimensões alvo `(width, height)` para o modo `custom`, se aplicável.
            extra_instructions: Instruções adicionais de reforço para retentativas.

        Returns:
            Prompt textual completo e estruturado.
        """
        spec = normalize_expansion_mode(mode)
        bleed_px = calculate_bleed_pixels(bleed_mm=bleed_mm, dpi=DEFAULT_DPI)

        dimension_details = (
            f"- Margem Obrigatória de Sangria (Bleed): {bleed_mm:.1f} mm por borda "
            f"({bleed_px} px em cada uma das 4 bordas: esquerda, direita, topo e base a {DEFAULT_DPI} DPI; "
            f"+{2 * bleed_px} px no total de largura e altura)."
        )

        if base_size is not None:
            target_w, target_h, _ = calculate_expanded_dimensions(
                base_width=base_size[0],
                base_height=base_size[1],
                mode=spec.code,
                bleed_mm=bleed_mm,
                dpi=DEFAULT_DPI,
                custom_size=custom_size,
            )
            dimension_details += (
                f"\n- Dimensão Original: {base_size[0]}x{base_size[1]} px -> "
                f"Dimensão Final Expandida: {target_w}x{target_h} px."
            )

        orientation_rule = (
            "Orientação final estritamente HORIZONTAL / PANORÂMICA (largura maior que altura)."
            if spec.requires_horizontal_orientation
            else "Mantenha a orientação original da arte expandindo todas as 4 bordas uniformemente."
        )

        sections = [
            f"[PAPEL DA IA]\n{self.AI_ROLE}",
            (
                "[INSTRUÇÃO PRINCIPAL DE OUTPAINTING / EXPANSÃO DE CENÁRIO]\n"
                f"Expanda e estenda generativamente o cenário ao redor da imagem anexa aplicando o modo "
                f"'{spec.label}' ({spec.code}).\n"
                f"- Diretriz do Modo: {spec.description}\n"
                f"{dimension_details}\n"
                f"- Regra de Orientação: {orientation_rule}"
            ),
            (
                "[PRESERVAÇÃO ESTRITA DO SUJEITO E ELEMENTOS CENTRAIS]\n"
                "- Os personagens, rostos, fisionomia, poses, objetos e elementos principais da imagem anexa "
                "NÃO devem ser alterados, redesenhados, deformados ou cortados.\n"
                "- Mantenha a arte original perfeitamente íntegra no centro da composição."
            ),
            (
                "[CONTINUIDADE ORGÂNICA DO AMBIENTE DE FUNDO]\n"
                "- Apenas o ambiente de fundo (céu, chão, paredes, luzes, partículas, magia, vegetação, "
                "arquitetura e atmosfera) deve continuar organicamente até as novas bordas.\n"
                "- Garanta transição invisível de textura, perspectiva, paleta de cores e iluminação entre a "
                "área original e as novas margens expandidas."
            ),
        ]

        if extra_instructions and extra_instructions.strip():
            sections.append(
                f"[DIRETRIZES COMPLEMENTARES DE CORREÇÃO]\n{extra_instructions.strip()}"
            )

        sections.append(
            "[RESTRIÇÕES NEGATIVAS OBRIGATÓRIAS]\n"
            "Evite estritamente: sem cortes no personagem; sem barras pretas ou brancas (pillarbox/letterbox); "
            "sem molduras sólidas artificiais; sem emendas visíveis, linhas de corte ou descontinuidades de iluminação; "
            "sem deformação anatômica ou alteração do rosto original."
        )

        return "\n\n".join(sections)
