"""Montador estruturado de prompts para geração de cartas no Google Gemini."""

from __future__ import annotations

from typing import List

from core.schema import CardInput
from engine.templates import (
    NEGATIVE_CONSTRAINTS,
    get_game_template,
    get_style_template,
)


class PromptBuilder:
    """Constrói prompts detalhados e estruturados a partir de uma instância de `CardInput`."""

    AI_ROLE: str = (
        "Você é um ilustrador sênior e designer gráfico especialista em Trading Card Games (TCG), "
        "capaz de criar cartas colecionáveis completas com layout autêntico, tipografia nítida "
        "e direção de arte impecável."
    )

    def build_prompt(self, card: CardInput) -> str:
        """Gera o prompt final concatenando todas as seções estruturadas da carta.

        Args:
            card: Objeto `CardInput` validado contendo os metadados da carta.

        Returns:
            Prompt textual completo pronto para envio ao gerador de imagens do Gemini.
        """
        if not isinstance(card, CardInput):
            raise TypeError(
                f"Esperado objeto do tipo 'CardInput', recebido '{type(card).__name__}'."
            )

        game_tpl = get_game_template(card.tipo)
        style_tpl = get_style_template(card.estilo)

        sections: List[str] = [
            self._build_role_section(),
            self._build_main_instruction_section(card, game_tpl.name, game_tpl.aspect_ratio),
            self._build_card_details_section(card, game_tpl.color_integration_hint),
            self._build_visual_style_section(
                game_tpl.layout_rules,
                game_tpl.art_direction,
                style_tpl.name,
                style_tpl.framing_rules,
            ),
        ]

        if card.imagens_referencia:
            sections.append(self._build_reference_images_section(card.imagens_referencia))

        sections.append(self._build_negative_constraints_section())

        return "\n\n".join(sections)

    def _build_role_section(self) -> str:
        """Retorna a definição do papel da IA."""
        return f"[PAPEL DA IA]\n{self.AI_ROLE}"

    def _build_main_instruction_section(
        self, card: CardInput, game_name: str, aspect_ratio: str
    ) -> str:
        """Retorna a instrução principal de geração da carta."""
        return (
            "[INSTRUÇÃO PRINCIPAL]\n"
            f"Gere a imagem de uma carta completa de '{game_name}' no estilo '{card.estilo}', "
            f"em {aspect_ratio}, apresentando o título exato \"{card.titulo}\"."
        )

    def _build_card_details_section(
        self, card: CardInput, color_integration_hint: str
    ) -> str:
        """Monta os detalhes específicos da carta (Título, Descrição, Cores, Regras)."""
        lines: List[str] = [
            "[DETALHES DA CARTA]",
            f"- Jogo / Sistema: {card.tipo}",
            f"- Título da Carta: \"{card.titulo}\"",
        ]

        if card.descricao:
            lines.append(f"- Descrição da Cena / Ilustração: {card.descricao}")
        else:
            lines.append(
                f"- Descrição da Cena / Ilustração: Representação visual épica e temática condizente com o título \"{card.titulo}\"."
            )

        if card.cores_lista:
            cores_formatadas = ", ".join(card.cores_lista)
            lines.append(
                f"- Cores / Elementos ({cores_formatadas}): {color_integration_hint}"
            )

        if card.texto_adicional:
            lines.append(
                f"- Texto de Regras / Atributos / Flavor Text na Caixa de Texto: \"{card.texto_adicional}\""
            )

        return "\n".join(lines)

    def _build_visual_style_section(
        self,
        layout_rules: str,
        art_direction: str,
        style_name: str,
        framing_rules: str,
    ) -> str:
        """Monta a seção de layout do jogo, direção de arte e estilo de enquadramento."""
        return (
            "[ESTILO VISUAL E LAYOUT]\n"
            f"- Estrutura e Layout do Card: {layout_rules}\n"
            f"- Direção de Arte: {art_direction}\n"
            f"- Acabamento e Enquadramento ({style_name}): {framing_rules}"
        )

    def _build_reference_images_section(self, reference_paths: List[str]) -> str:
        """Monta instruções explícitas sobre o uso das imagens de referência anexadas."""
        qtd = len(reference_paths)
        plural = "imagem anexa" if qtd == 1 else f"{qtd} imagens anexas"
        return (
            "[DIRETRIZES DE IMAGENS DE REFERÊNCIA]\n"
            f"Utilize {plural} como referência visual obrigatória. "
            "Preserve fielmente a fisionomia, traços faciais, vestimentas, paleta de cores "
            "e elementos-chave do personagem/objeto presente nas imagens de referência anexadas, "
            "adaptando-os de forma coesa ao estilo artístico e iluminação da carta."
        )

    def _build_negative_constraints_section(self) -> str:
        """Monta o bloco de restrições negativas automáticas."""
        joined_constraints = "; ".join(NEGATIVE_CONSTRAINTS)
        return (
            "[RESTRIÇÕES NEGATIVAS OBRIGATÓRIAS]\n"
            f"Evite estritamente: {joined_constraints}."
        )
