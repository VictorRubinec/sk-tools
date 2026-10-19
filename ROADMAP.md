# ROADMAP | Studio Kustom Automation Suite (`sk-tools`)

Este documento estabelece o roteiro de evolução técnica das ferramentas da Studio Kustom, integrando as necessidades comerciais da oficina aos padrões de engenharia gráfica, perfil de cores e automação com IA.

---

## 1. Especificações Físicas Homologadas da Studio Kustom

> [!IMPORTANT]
> A Studio Kustom adota dimensões de papel e tolerâncias próprias de oficina que diferem das normas genéricas de mercado:
> - **Poster A4**: $210 \times 300\text{ mm}$ (diferente do padrão 210x297mm ISO).
> - **Poster A3**: $300 \times 420\text{ mm}$ (diferente do padrão 297x420mm ISO).
> - **Cartas Colecionáveis (TCG)**: $63 \times 88\text{ mm}$ (1 PDF único por folha frente e verso casado).
> - **Gabarito de Caneca (11oz / 325ml)**: $220 \times 95\text{ mm}$ (faixa panorâmica cilíndrica).
> - **Margem de Sangria de Fundo**: $5\text{ mm}$ para cada lado nas expansões generativas de cenário.

### Parque de Impressoras e Calibração de Cor (Ponto de Atenção)
1. **Konica Minolta bizhub C558 (Laser Digital CMYK)**:
   - Destino: Cartas TCG em papel Couché 300g Duplex (frente e verso).
   - Perfil de cor: CMYK Fogra39 / ISO Coated v2.
   - Ponto de atenção: Limitação de Cobertura Total de Tinta (TIC $\le 300\%$) para evitar empastamento de toner e garantir aderência perfeita da termolaminação fosca Hi-Tac.
2. **Epson SureColor T3170 (Plotter Fotográfica PrecisionCore MicroTFP)**:
   - Destino: Posters A3 ($300 \times 420\text{ mm}$) e A4 ($210 \times 300\text{ mm}$) em papel fotográfico profissional.
   - Perfil de cor: RGB de ampla gama (Adobe RGB 1998 / sRGB de alta fidelidade) com tintas UltraChrome XD2.
3. **Epson EcoTank L110 (Sublimática Modificada)**:
   - Destino: Papel transfer sublimático para canecas de cerâmica e tecidos ($200^\circ\text{C}$ na prensa).
   - Ponto de atenção: Compensação cromática de $+18\%$ na saturação digital dos canais de cor, pois as cores sublimáticas só se ativam após a prensagem térmica.

---

## 2. Ferramentas e Ordem de Desenvolvimento

### Ferramenta 1: `card-gen` (Geração de Cartas TCG) — [CONCLUÍDA / v1.1.0]
- [x] Motor de automação via Playwright com perfil Chrome persistente (`.chrome_profile`).
- [x] Injeção de fotos de referência mantendo fisionomia.
- [x] Validador Pillow de TCG (dimensões, ratio, qualidade cromática).
- [x] Pacote encapsulado em `tools/card_generator/` com 40 testes automatizados.

---

### Ferramenta 2: `upscaler` (Upscaling via IA / Gemini Web) — [PRÓXIMO PASSO]
- **Técnica**: Utiliza a **mesma técnica validada na geração de cartas** (automação do Gemini Web via Playwright com perfil persistente).
- **Mecanismo**: A carta/imagem é submetida como imagem anexa ao Gemini com um prompt estruturado de redraw de alta definição e super-resolução.
- **Instruções do Prompt**:
  - Preservação estrita dos traços fisionômicos, textos e elementos visuais da carta.
  - Eliminação de artefatos de ruído digital e compressão.
  - Re-renderização no formato e aspect ratio solicitado:
    - **A4 Vertical**: $210 \times 300\text{ mm}$ ($2480 \times 3543\text{ px}$ a 300 DPI).
    - **A4 Horizontal**: $300 \times 210\text{ mm}$ ($3543 \times 2480\text{ px}$ a 300 DPI).
    - **A3 Vertical**: $300 \times 420\text{ mm}$ ($3543 \times 4960\text{ px}$ a 300 DPI).
    - **A3 Horizontal**: $420 \times 300\text{ mm}$ ($4960 \times 3543\text{ px}$ a 300 DPI).
- **Subcomando CLI**: `python cli.py upscaler --image ... --target [a4_v|a4_h|a3_v|a3_h]`

---

### Ferramenta 3: `background-expander` (Expansão de Fundo via IA)
- **Técnica**: Extensão generativa de cenário (Outpainting) via Gemini Web.
- **Especificação**: Gera obrigatoriamente **$5\text{ mm}$ para cada lado** ($5\text{ mm}$ extra no topo, base, esquerda e direita) como margem de sangria para corte e encaixe.
- **Caso de Uso**: Adaptação de cartas verticais para artes de posters horizontais e faixas de canecas sem cortes no personagem.

---

### Ferramenta 4: `print-sheet` (Gerador de Folhas de Impressão)
- **Cartas TCG**:
  - Montagem de grade $3 \times 3$ com 9 cartas por folha A4.
  - **Regra Rígida**: **1 arquivo PDF por folha frente e verso casado** (Página 1: Frente com cruzes de corte; Página 2: Verso espelhado perfeitamente para registro $\le 0.2\text{ mm}$ na Konica Minolta).
- **Posters**:
  - Enquadramento $210 \times 300\text{ mm}$ (A4) ou $300 \times 420\text{ mm}$ (A3) com linhas de corte.

---

### Ferramenta 5: `mug-artist` (Criador de Arte para Caneca)
- **Gabarito**: $220 \times 95\text{ mm}$ ($2598 \times 1122\text{ px}$ a 300 DPI).
- **Processamento**: Reutilização da expansão de fundo de $5\text{ mm}$ + compensação cromática de $+18\%$ para sublimação térmica da Epson L110.

---

### Ferramenta 6: `production-manager` (Gerenciador de Produção)
- **Objetivo**: Sistema inteligente para guiar o operador na montagem rápida e à prova de falhas de novos pedidos.
- **Mecanismo**: Formulários e questionários interativos guiados (perguntas de triagem: tipo de jogo, estilo, foto, títulos, destino do produto) gerando o `card.json` validado automaticamente.
- **Rastreio de Status**: Acompanhamento do ciclo produtivo (Pendente $\to$ Gerado $\to$ Aprovado $\to$ Impresso $\to$ Finalizado).

---

## 3. Espaço para Futuras Ideias e Expansões

1. **Simulador de Mockup 3D Interativo (Three.js)**:
   - Pré-visualização 3D da carta com efeito Foil/Holográfico e da caneca giratória para aprovação do cliente.
2. **Auditor Automático de OCR**:
   - Conferência pós-geração comparando texto da imagem com o pedido original.
3. **Gerador Automático de Etiquetas de Envio**:
   - Integração com Shopee/Correios para etiquetas dos pedidos prontos.
4. **Calculadora de Custo de Insumos por Pedido**:
   - Rateio de toner, papel couché 300g, película Hi-Tac e embalagens.
