"""Templates especializados de composição visual por jogo, estilo e restrições negativas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Final, Tuple


@dataclass(frozen=True)
class GameTemplate:
    """Define as diretrizes visuais, layout e direção de arte de um card game."""

    name: str
    layout_rules: str
    art_direction: str
    color_integration_hint: str
    aspect_ratio: str = "proporção vertical de card game colecionável (aprox. 2.5:3.5 / 5:7)"


@dataclass(frozen=True)
class StyleTemplate:
    """Define o enquadramento e acabamento estético conforme o estilo da carta."""

    name: str
    framing_rules: str


GAME_TEMPLATES: Final[Dict[str, GameTemplate]] = {
    "Magic": GameTemplate(
        name="Magic: The Gathering (MTG)",
        layout_rules=(
            "Layout clássico de MTG (Magic: The Gathering), com barra de título superior, "
            "ícones de mana alinhados no canto superior direito, linha de tipo intermediária "
            "e caixa de texto de regras/flavor text bem delimitada na parte inferior."
        ),
        art_direction=(
            "Ilustração de fantasia épica e arte conceitual de altíssimo nível (estilo Wizards of the Coast), "
            "iluminação dramática, riqueza de texturas e pintura digital detalhada."
        ),
        color_integration_hint=(
            "Alinhe a moldura da carta, símbolos de mana e atmosfera cromática com as cores de mana especificadas."
        ),
    ),
    "Pokemon": GameTemplate(
        name="Pokémon TCG",
        layout_rules=(
            "Layout oficial de card Pokémon TCG, exibindo cabeçalho com estágio evolutivo, nome e HP no topo, "
            "ícones de energia/elementos alinhados com o campo de cores, ataques centralizados e rodapé de fraqueza/recuo."
        ),
        art_direction=(
            "Estilo de anime moderno vibrante ou renderização 3D dinâmica e polida, com efeitos elementais "
            "luminosos e foco expressivo na criatura/personagem."
        ),
        color_integration_hint=(
            "Integre a energia e os elementos visuais do card diretamente com as cores/tipos elementais informados."
        ),
    ),
    "Yu-Gi-Oh!": GameTemplate(
        name="Yu-Gi-Oh! Trading Card Game",
        layout_rules=(
            "Borda característica de monstro/efeito de Yu-Gi-Oh!, caixa de título com atributo esférico no canto "
            "superior direito, estrelas de nível/rank abaixo do título, janela quadrada central e caixa de texto "
            "inferior contendo linha de ATK/DEF claramente estruturada."
        ),
        art_direction=(
            "Arte em estilo mangá shonen clássico/moderno (estilo Kazuki Takahashi / Konami), traços fortes, "
            "contraste intenso, aura energética e pose imponente."
        ),
        color_integration_hint=(
            "Reflita as cores no atributo elemental, na moldura do card e nos efeitos de energia ao redor do monstro."
        ),
    ),
    "One Piece": GameTemplate(
        name="One Piece Card Game (OP TCG)",
        layout_rules=(
            "Layout característico de OP TCG (One Piece Card Game), com custo/vida no canto superior esquerdo, "
            "poder de combate no canto superior direito, faixa de contador lateral, tipografia marcante de "
            "líder/personagem na base e caixa de efeito translúcida."
        ),
        art_direction=(
            "Estilo Eiichiro Oda / Toei Animation de alta definição, linhas dinâmicas de ação em mangá/anime, "
            "cores saturadas, sombreamento cel-shaded refinado e impacto visual cinematográfico."
        ),
        color_integration_hint=(
            "Aplique a paleta do card (hexágonos de cor, faixa inferior e aura de haki/efeito) conforme as cores informadas."
        ),
    ),
    "Custom": GameTemplate(
        name="Custom Collectible Card Game (TCG)",
        layout_rules=(
            "Regras gerais de composição de card colecionável de alta fidelidade: hierarquia tipográfica clara "
            "com barra de título no topo, área nobre para a ilustração principal e caixa de texto estruturada "
            "na parte inferior para regras e descrição."
        ),
        art_direction=(
            "Ilustração digital premium para card game colecionável, acabamento profissional de estúdio, "
            "composição equilibrada, iluminação volumétrica e nitidez impecável."
        ),
        color_integration_hint=(
            "Harmonize a moldura ornamental e a paleta de iluminação da cena com as cores especificadas."
        ),
    ),
}

STYLE_TEMPLATES: Final[Dict[str, StyleTemplate]] = {
    "Normal": StyleTemplate(
        name="Normal (Standard Frame)",
        framing_rules=(
            "Enquadramento padrão respeitando rigorosamente a janela da ilustração e as bordas clássicas do card game, "
            "mantendo a separação visual nítida entre a moldura da carta, a arte contida no quadro central e a caixa de texto."
        ),
    ),
    "Fullart": StyleTemplate(
        name="Fullart (Extended Borderless Art)",
        framing_rules=(
            "Arte estendida de ponta a ponta (full-bleed / borderless), sem bordas limitantes ao redor da ilustração, "
            "com visual cinematográfico imersivo onde os elementos gráficos e a tipografia da carta se sobrepõem "
            "harmoniosamente à arte completa."
        ),
    ),
    "Alternative": StyleTemplate(
        name="Alternative Art (Special Collector Edition)",
        framing_rules=(
            "Composição artística alternativa de edição especial de colecionador, ângulo de câmera arrojado, "
            "arte expandida com acabamento especial (foil/texturizado) e integração estilizada dos elementos do card."
        ),
    ),
}

NEGATIVE_CONSTRAINTS: Final[Tuple[str, ...]] = (
    "sem ruídos digitais ou artefatos de compressão",
    "sem dedos extras, membros deformados ou anatomia distorcida",
    "sem texto ininteligível, caracteres truncados ou gibberish tipográfico",
    "sem cortes nas bordas da carta (a carta inteira deve estar visível e perfeitamente enquadrada)",
    "sem marcas d'água, assinaturas externas ou objetos de mesa fora do card",
)


def get_game_template(tipo: str) -> GameTemplate:
    """Retorna o template especializado do jogo ou o template 'Custom' como fallback."""
    if tipo in GAME_TEMPLATES:
        return GAME_TEMPLATES[tipo]
    return GameTemplate(
        name=f"{tipo} (Custom TCG)",
        layout_rules=(
            f"Design de card colecionável inspirado no universo '{tipo}', aplicando {GAME_TEMPLATES['Custom'].layout_rules.lower()}"
        ),
        art_direction=GAME_TEMPLATES["Custom"].art_direction,
        color_integration_hint=GAME_TEMPLATES["Custom"].color_integration_hint,
        aspect_ratio=GAME_TEMPLATES["Custom"].aspect_ratio,
    )


def get_style_template(estilo: str) -> StyleTemplate:
    """Retorna o template de estilo visual ou constrói um template customizado."""
    if estilo in STYLE_TEMPLATES:
        return STYLE_TEMPLATES[estilo]
    return StyleTemplate(
        name=f"{estilo} (Custom Style)",
        framing_rules=(
            f"Estilo visual '{estilo}', com composição artística de alta fidelidade, "
            "respeitando a leitura dos elementos do card e acabamento estético refinado."
        ),
    )
