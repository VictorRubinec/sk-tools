"""Montador de Prompts estruturados para geração de arte de caneca via Gemini Web (tools/mug_artist)."""

from __future__ import annotations

from typing import Final

from tools.mug_artist.schema import MugInput

CRITICAL_NEGATIVE_CONSTRAINT: Final[str] = (
    "NÃO gere um mockup 3D de xícara ou caneca cerâmica, não mostre a alça em perspectiva, "
    "não desenhe café ou fundo de mesa/estúdio. A imagem DEVE ser estritamente o layout gráfico "
    "retangular plano desdobrado (2D flat wrap) pronto para impressão e prensa térmica"
)


class MugPromptBuilder:
    """Construtor de prompts técnicos e artísticos para geração de artes de caneca 11oz."""

    def __init__(self) -> None:
        pass

    def build_prompt(self, mug: MugInput) -> str:
        """Monta o prompt estruturado com especificações físicas, direção de arte e constraints.

        Args:
            mug: Instância validada de `MugInput`.

        Returns:
            String contendo o prompt completo formatado para o Google Gemini.
        """
        sections: list[str] = []

        # 1. Papel da IA
        sections.append(
            "# PAPEL E ESPECIALIDADE DA IA\n"
            "Você é um Designer Gráfico Sênior e Ilustrador Profissional do Studio Kustom, "
            "especializado na criação de artes digitais de alta fidelidade para estamparia por sublimação "
            "em canecas de cerâmica de 11oz (325ml)."
        )

        # 2. Instrução Principal
        sections.append(
            "# INSTRUÇÃO PRINCIPAL DE LAYOUT E FORMATO\n"
            "Crie uma arte gráfica em faixa retangular plana 2D contínua de 220x95mm "
            "(proporção panorâmica ~2.31:1, resolução ultra HD a 300 DPI).\n"
            "A imagem gerada representa a estampa desdobrada e aberta no plano horizontal, "
            "perfeita para envelopamento da caneca de ponta a ponta, preservando apenas as margens "
            "de segurança nas extremidades laterais próximas à alça."
        )

        # 3. Detalhes da Caneca
        detalhes: list[str] = [
            f"- **Tema / Universo**: {mug.tema}",
            f"- **Título da Arte**: {mug.titulo}",
        ]
        if mug.descricao:
            detalhes.append(f"- **Descrição da Cena / Composição**: {mug.descricao}")
        if mug.mensagem:
            detalhes.append(f"- **Mensagem Comemorativa / Texto**: \"{mug.mensagem}\"")
        if mug.cores:
            cores_str = ", ".join(mug.cores_lista)
            detalhes.append(f"- **Paleta Cromática Sugerida**: {cores_str}")

        sections.append("# DETALHES DA CANECA\n" + "\n".join(detalhes))

        # 4. Direção de Arte conforme o layout (Panorâmico, Dual Face ou Card + Mensagem)
        estilo_lower = mug.estilo.lower()
        if "panoram" in estilo_lower:
            layout_instructions = (
                "**Layout Panorâmico Contínuo (220mm horizontal)**:\n"
                "- A ilustração deve fluir horizontalmente cobrindo toda a faixa retangular contínua de 220x95mm.\n"
                "- A cena deve possuir uma atmosfera expansiva e rica, com o sujeito principal harmonizado no centro "
                "ou com transição épica entre a Face 1 (esquerda), Centro e Face 2 (direita).\n"
                "- Evite cortes abruptos; iluminação, partículas e elementos de cenário devem preencher suavemente o horizonte."
            )
        elif "dual" in estilo_lower:
            layout_instructions = (
                "**Layout Dual Face (Duas Faces com Centro Conector)**:\n"
                "- A arte possui dois focos visuais principais: Face Esquerda (centro visual em ~25% da largura, ~650px) "
                "e Face Direita (centro visual em ~75% da largura, ~1948px).\n"
                "- Ambas as faces devem apresentar elementos gráficos expressivos e complementares do tema "
                "(ex: dois personagens, evolução, frente e verso comemorativo).\n"
                "- O centro (50% da largura) atua como uma transição contínua, harmônica e texturizada que conecta as duas faces."
            )
        else:
            # Card + Mensagem
            layout_instructions = (
                "**Layout Card + Mensagem (Arte na Face Esquerda + Mensagem na Face Direita)**:\n"
                "- Face Esquerda (~25% a 35% da largura): Destaque para a ilustração temática principal "
                "(personagem, casal, carta colecionável ou criatura em pose de ação).\n"
                "- Face Direita (~65% a 75% da largura): Destaque para a mensagem comemorativa com tipografia elegante, "
                "ornamentada e legível, combinando com o universo visual do tema.\n"
                "- Fundo contínuo de 220mm: Textura de fundo, efeitos luminosos e partículas místicas que unem visualmente "
                "a arte à esquerda e o painel de texto à direita em uma peça gráfica coesa."
            )

        sections.append("# DIREÇÃO DE ARTE CONFORME O LAYOUT\n" + layout_instructions)

        # 5. Imagens de Referência
        if mug.imagens_referencia:
            sections.append(
                "# IMAGENS ANEXAS DE REFERÊNCIA\n"
                "- Foram fornecidas imagens de referência anexadas.\n"
                "- Preserve fielmente os traços fisionômicos, anatomia, características dos personagens, vestimentas, "
                "esquema de cores e detalhes visuais presentes nas imagens de referência, adaptando-os com maestria ao tema solicitado."
            )

        # 6. Restrição Negativa Crucial (Anti-Mockup 3D)
        sections.append(
            "# RESTRIÇÃO NEGATIVA CRUCIAL (OBRIGATÓRIO)\n"
            f"> [!IMPORTANT]\n"
            f"> {CRITICAL_NEGATIVE_CONSTRAINT}.\n\n"
            "- Não renderize sombras de superfície de mesa, reflexos de bancada, fundo de cozinha ou profundidade de campo 3D.\n"
            "- A imagem inteira deve ser preenchida de ponta a ponta pela arte gráfica vetorial/digital plana, sem bordas pretas adicionais."
        )

        return "\n\n".join(sections)
