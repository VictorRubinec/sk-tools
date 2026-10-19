"""Testes unitários para o motor de geração de prompts (Fase 2 - engine/)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.schema import CardInput
from engine import PromptBuilder


class TestPromptEngine(unittest.TestCase):
    """Suíte de testes para o PromptBuilder e os templates especializados de cartas."""

    def setUp(self) -> None:
        """Inicializa o montador de prompts para cada teste."""
        self.builder = PromptBuilder()

    def test_prompt_generation_for_all_four_standard_games(self) -> None:
        """Deve incluir palavras-chave específicas do template de cada um dos 4 jogos padrão."""
        expected_keywords = {
            "Magic": ["MTG", "mana", "caixa de texto", "fantasia"],
            "Pokemon": ["Pokémon TCG", "HP", "energia", "anime"],
            "Yu-Gi-Oh!": ["Yu-Gi-Oh!", "ATK/DEF", "monstro/efeito", "mangá shonen"],
            "One Piece": ["OP TCG", "One Piece", "Oda", "líder/personagem"],
        }

        for game, keywords in expected_keywords.items():
            with self.subTest(game=game):
                card = CardInput(
                    tipo=game,
                    estilo="Normal",
                    titulo=f"Carta Exemplar de {game}",
                )
                prompt = self.builder.build_prompt(card)
                for kw in keywords:
                    self.assertIn(
                        kw.lower(),
                        prompt.lower(),
                        f"Palavra-chave '{kw}' ausente no prompt do jogo '{game}'.",
                    )

    def test_custom_game_template_fallback(self) -> None:
        """Deve utilizar o template Custom quando o tipo de jogo for personalizado."""
        card = CardInput(
            tipo="Lorcana Custom",
            estilo="Normal",
            titulo="Feiticeiro Real",
        )
        prompt = self.builder.build_prompt(card)
        self.assertIn("Lorcana Custom", prompt)
        self.assertIn("card colecionável de alta fidelidade", prompt.lower())

    def test_style_differentiation_normal_vs_fullart(self) -> None:
        """Deve diferenciar claramente os estilos 'Normal' e 'Fullart' no prompt gerado."""
        card_normal = CardInput(
            tipo="Magic",
            estilo="Normal",
            titulo="Anjo da Guarda",
        )
        card_fullart = CardInput(
            tipo="Magic",
            estilo="Fullart",
            titulo="Anjo da Guarda",
        )

        prompt_normal = self.builder.build_prompt(card_normal)
        prompt_fullart = self.builder.build_prompt(card_fullart)

        self.assertNotEqual(prompt_normal, prompt_fullart)
        self.assertIn("janela da ilustração", prompt_normal.lower())
        self.assertIn("bordas clássicas", prompt_normal.lower())

        self.assertIn("ponta a ponta", prompt_fullart.lower())
        self.assertIn("sem bordas limitantes", prompt_fullart.lower())
        self.assertIn("cinematográfico", prompt_fullart.lower())

    def test_inclusion_of_cores_descricao_and_texto_adicional(self) -> None:
        """Deve incluir 'cores', 'descricao' e 'texto_adicional' corretamente no prompt."""
        card = CardInput(
            tipo="Yu-Gi-Oh!",
            estilo="Normal",
            titulo="Mago do Caos cibernético",
            descricao="Feiticeiro de armadura negra conjurando relâmpagos dourados.",
            texto_adicional="[Mago / Efeito] ATK/2500 DEF/2100 - Destrua 1 card no campo.",
            cores=["Trevas", "Luz"],
        )
        prompt = self.builder.build_prompt(card)

        self.assertIn("Mago do Caos cibernético", prompt)
        self.assertIn(
            "Feiticeiro de armadura negra conjurando relâmpagos dourados.", prompt
        )
        self.assertIn(
            "[Mago / Efeito] ATK/2500 DEF/2100 - Destrua 1 card no campo.", prompt
        )
        self.assertIn("Trevas, Luz", prompt)
        # Verifica também restrições negativas automáticas
        self.assertIn("sem ruídos digitais", prompt.lower())
        self.assertIn("sem dedos extras", prompt.lower())
        self.assertIn("sem texto ininteligível", prompt.lower())
        self.assertIn("sem cortes nas bordas", prompt.lower())

    def test_reference_images_present_vs_absent(self) -> None:
        """Deve incluir instruções de referência visual apenas quando 'imagens_referencia' for fornecido."""
        card_without_ref = CardInput(
            tipo="One Piece",
            estilo="Fullart",
            titulo="Roronoa Zoro",
        )
        prompt_without_ref = self.builder.build_prompt(card_without_ref)
        self.assertNotIn("[DIRETRIZES DE IMAGENS DE REFERÊNCIA]", prompt_without_ref)

        with tempfile.TemporaryDirectory() as tmp_dir:
            ref_file = Path(tmp_dir) / "zoro_ref.png"
            ref_file.write_bytes(b"\x89PNG\r\n\x1a\n")

            card_with_ref = CardInput(
                tipo="One Piece",
                estilo="Fullart",
                titulo="Roronoa Zoro",
                imagens_referencia=[str(ref_file)],
            )
            prompt_with_ref = self.builder.build_prompt(card_with_ref)
            self.assertIn("[DIRETRIZES DE IMAGENS DE REFERÊNCIA]", prompt_with_ref)
            self.assertIn("fisionomia", prompt_with_ref.lower())
            self.assertIn("imagem anexa", prompt_with_ref.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
