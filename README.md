# sk-tools | Studio Kustom Automation Suite

Suite unificada e modular de engenharia gráfica e automação com inteligência artificial da **Studio Kustom**. Projetada para eliminar retrabalho artesanal, inconsistências de layout e quebras de registro na fabricação de cartas colecionáveis (TCG), pôsteres de alta definição e canecas para sublimação.

---

## 1. Arquitetura do Sistema (Modular Toolbox / Facade Pattern)

O `sk-tools` opera sob o padrão **Modular Toolbox**, onde cada ferramenta reside em seu próprio pacote independente dentro de `tools/`, expondo uma API pública estável (`api.py`) e conectando-se a uma CLI unificada com subcomandos especializados:

```text
sk-tools/
├── cli.py                          # Ponto de entrada unificado da CLI (subcomandos)
├── requirements.txt                # Dependências congeladas (Playwright, Pillow, Pydantic v2, ReportLab)
├── README.md                       # Documentação técnica do ecossistema
│
├── tools/                          # Ferramentas independentes da Studio Kustom
│   ├── card_generator/             # [v1.1.0] Geração de cartas TCG via Gemini Web + Playwright
│   │   ├── api.py                  # Fachada pública (generate_single_card, generate_batch)
│   │   ├── core/                   # Schema Pydantic (CardInput), config, runner com retentativas
│   │   ├── engine/                 # Templates de jogos (Magic, Pokémon, Yu-Gi-Oh!, One Piece) e prompts
│   │   ├── browser/                # Automação Playwright Chromium com perfil persistente (.chrome_profile)
│   │   └── validator/              # Validador de conformidade física e gráfica (Pillow)
│   │
│   ├── upscaler/                   # [v1.2.0] Super-resolução e redraw de posters 300 DPI via Gemini Web
│   │   ├── api.py                  # Fachada pública (upscale_card_to_poster)
│   │   ├── prompt_builder.py       # Especificações de posters (A4_V, A4_H, A3_V, A3_H) e prompt de redraw
│   │   ├── validator.py            # Validação Pillow, remoção de pillarbox/letterbox e conformação Lanczos
│   │   └── orchestrator.py         # Orquestração ponta a ponta com Gemini e download nativo
│   │
│   ├── background_expander/        # [v1.3.0] Expansão generativa de fundo (outpainting) com 5mm de sangria
│   │   ├── api.py                  # Fachada pública (expand_background)
│   │   ├── prompt_builder.py       # Modos de outpainting (bleed_5mm, horizontal, caneca, custom)
│   │   ├── validator.py            # Validação de integridade, auto-trim de barras e 5mm de sangria real (59px @ 300 DPI)
│   │   └── orchestrator.py         # Orquestração persistente no Gemini Web
│   │
│   ├── print_sheet/                # [v1.4.0] Imposição gráfica e montador PDF duplex Super A4 (230x320mm)
│   │   ├── api.py                  # Fachada pública (create_card_print_sheet, create_poster_print_sheet)
│   │   ├── card_grid.py            # Geometria Super A4 3x3 (calhas 12mm/14mm, espelhamento duplex pixel a pixel)
│   │   ├── crop_marks.py           # Marcas de corte contínuas de 0.25mm e cruzes de registro com mira circular
│   │   └── pdf_builder.py          # Compilador PDF vetorial multipágina 300 DPI (Pág 1: Frente / Pág 2: Verso)
│   │
│   ├── mug_artist/                 # [v1.5.0] Criador generativo de arte para canecas 11oz (220x95mm @ 300 DPI)
│   │   ├── api.py                  # Fachada pública (create_mug_artwork, load_mugs_from_file)
│   │   ├── schema.py               # Schema Pydantic v2 (MugInput) para ingestão JSON ou inline
│   │   ├── prompt_builder.py       # Prompt 2D flat wrap com restrição negativa anti-mockup 3D
│   │   ├── color_engine.py         # Compensação cromática para Epson L110 (+18% de saturação)
│   │   ├── composer.py             # Montador de layout local (Panorâmico, Dual Face, Card + Mensagem)
│   │   └── orchestrator.py         # Orquestrador dual (Gemini generativo ou composição local)
│   │
│   └── order_planner/              # [EM PLANEJAMENTO v1.6.0] Orquestrador e triagem de pedidos de clientes
│
├── input/                          # Arquivos de dados de entrada (sample_cards.json, sample_mugs.json, etc.)
├── output/                         # Diretório de artefatos gerados (PNGs, PDFs duplex, prévias e transfers)
├── scripts/                        # Scripts utilitários de suporte e autenticação
└── tests/                          # Suíte automatizada com 103 testes e 52 subtestes (100% de aprovação)
    ├── test_card_generator/
    ├── test_upscaler/
    ├── test_background_expander/
    ├── test_print_sheet/
    └── test_mug_artist/
```

---

## 2. Ferramentas Homologadas

### 🎴 Ferramenta 1: `card-gen` (Geração de Cartas TCG)
- **Comando CLI**: `card-gen` (aliases: `cards`, `card`).
- **Capacidades**:
  - Geração autêntica de cartas de **Magic: The Gathering**, **Pokémon TCG**, **Yu-Gi-Oh!**, **One Piece** e sistemas customizados.
  - Suporte a estilos `Normal` (moldura clássica) e `Fullart` (arte estendida sem cortes).
  - Anexo de fotos reais de clientes como imagens de referência visual mantendo fisionomia.
  - Validação técnica rigorosa com Pillow: integridade física, resolução mínima ($512\times700\text{ px}$), orientação vertical, aspect ratio canônico de TCG ($1.25$ a $1.65$) e bloqueio de imagens monocromáticas/vazias.
  - Loop automático de retentativas com reforço semântico de prompt e descarte de arquivos reprovados.

```powershell
# Processamento em lote a partir de JSON
python cli.py card-gen --input input/sample_cards.json --retries 3

# Processamento de carta inline
python cli.py card-gen --card '{"tipo": "Magic", "estilo": "Normal", "titulo": "Mago Cósmico"}'

# Verificação de status da sessão no Gemini Web
python cli.py --check-session
```

---

### 🖼️ Ferramenta 2: `upscale` (Super-Resolução de Pôsteres A4/A3 a 300 DPI)
- **Comando CLI**: `upscale` (aliases: `poster`, `up`).
- **Capacidades**:
  - Redesenho de alta definição e super-resolução via prompt de redraw estruturado no Gemini Web.
  - Formatos físicos proprietários da Studio Kustom a 300 DPI:
    - **A4 Vertical**: $210 \times 300\text{ mm} \implies 2480 \times 3543\text{ px}$ ($\text{ratio} \approx 1.429$).
    - **A4 Horizontal**: $300 \times 210\text{ mm} \implies 3543 \times 2480\text{ px}$ ($\text{ratio} \approx 0.700$).
    - **A3 Vertical**: $300 \times 420\text{ mm} \implies 3543 \times 4960\text{ px}$ ($\text{ratio} \approx 1.400$).
    - **A3 Horizontal**: $420 \times 300\text{ mm} \implies 4960 \times 3543\text{ px}$ ($\text{ratio} \approx 0.714$).
  - Detecção e eliminação automática de barras pretas periféricas (*pillarbox* e *letterbox*).
  - Conformação dimensional fina com interpolação Lanczos a 300 DPI.

```powershell
# Upscaling de carta para Poster A4 Vertical
python cli.py upscale --image output/sua_carta.png --target a4_v

# Upscaling para Poster A3 Horizontal
python cli.py upscale -i output/sua_carta.png -t a3_h
```

---

### 🌄 Ferramenta 3: `expand` (Expansão Generativa de Fundo com Sangria)
- **Comando CLI**: `expand` (aliases: `outpaint`, `bg`).
- **Capacidades**:
  - Outpainting generativo contínuo via Gemini Web mantendo personagens e elementos centrais intactos.
  - Sangria de segurança física calculada matematicamente a 300 DPI:
    $$5\text{ mm} \text{ a } 300\text{ DPI} = \frac{5 \times 300}{25.4} \approx 59.05 \implies 59\text{ px por borda} \ (+118\text{ px no total})$$
  - Modos suportados:
    - `bleed_5mm`: Adiciona 5mm de sangria nas 4 bordas para corte em guilhotina industrial.
    - `horizontal`: Expansão panorâmica para posters horizontais ($300 \times 210\text{ mm}$).
    - `caneca`: Expansão horizontal ampla para faixa de sublimação.
    - `custom`: Expansão com margem arbitrária em milímetros.
  - Suporte à flag `--preserve-frame` para manter bordas e molduras de TCGs intocadas.

```powershell
# Adicionar sangria técnica de 5mm para guilhotina
python cli.py expand --image output/carta.png --mode bleed_5mm

# Expansão panorâmica com preservação de moldura
python cli.py expand -i output/carta.png -m horizontal --preserve-frame
```

---

### 📄 Ferramenta 4: `sheet` (Imposição Gráfica e PDF Duplex Super A4)
- **Comando CLI**: `sheet` (aliases: `print-sheet`, `folha`, `imposition`).
- **Capacidades**:
  - Geometria calibrada para papel **Super A4 ($230 \times 320\text{ mm} \implies 2717 \times 3780\text{ px}$ a 300 DPI)**.
  - Grade 3x3 com 9 cartas por folha ($63 \times 88\text{ mm}$ cada):
    - Calhas de separação: **12 mm horizontal** e **14 mm vertical**.
    - Margens simétricas centralizadas: $13.5\text{ mm}$ lateral e $15.0\text{ mm}$ vertical.
  - **Espelhamento Duplex Óptico para Konica Minolta C558**:
    - Página 1: Frente das cartas (Col 0, Col 1, Col 2).
    - Página 2: Verso espelhado no eixo vertical (Col 2 $\leftrightarrow$ Col 0, Col 1 fixo).
    - Sangria traseira de $5\text{ mm}$ automática para absorver variação de tração mecânica duplex ($\le 0.2\text{ mm}$).
  - Marcas de corte contínuas de $0.25\text{ mm}$ ($3\text{ px}$) e cruzes de registro com mira circular nos 4 cantos.
  - Montagem de pôsteres individuais em folha A4/A3 com cruzes de corte.

```powershell
# Gerar folha duplex Super A4 a partir de uma pasta de cartas
python cli.py sheet --cards-dir output/minhas_cartas/ --back output/VersoPadrao.png --paper super_a4

# Montar folha a partir de lista explícita de cartas
python cli.py sheet --cards c1.png c2.png c3.png --back verso.png -o output/folha_duplex.pdf

# Montar folha de pôster com marcas de corte
python cli.py sheet --poster output/poster_a4.png --paper a4 -o output/poster_imprimir.pdf
```

---

### ☕ Ferramenta 5: `mug` (Criador de Arte para Caneca de Sublimação 11oz)
- **Comando CLI**: `mug` (aliases: `caneca`, `mug-art`).
- **Capacidades**:
  - Padrão físico rigoroso da Studio Kustom para **Caneca 11oz (325ml) a 300 DPI**:
    - Dimensões: **$220 \times 95\text{ mm} \implies 2598 \times 1122\text{ px}$**.
    - Centros úteis: Face Esquerda ($X=650\text{ px}$), Face Centro ($X=1299\text{ px}$), Face Direita ($X=1948\text{ px}$).
    - Margem de segurança da alça: $10\text{ mm}$ ($118\text{ px}$) nas pontas laterais.
  - **Geração Orientada a Parâmetros JSON (`MugInput`)**:
    - Acionamento direto do Google Gemini Web com fotos de clientes anexadas.
    - `MugPromptBuilder` com **restrição negativa estrita anti-mockup 3D** (exige faixa retangular plana 2D aberta, proibindo xícaras 3D com alça, café ou mesas).
    - Suporte a 3 estilos de composição: `Panoramico`, `Dual Face` e `Card + Mensagem`.
  - **Compensação Cromática para Prensa Térmica**:
    - Aplicação de **+18% de saturação** na versão de impressão para a impressora **Epson L110 Sublimática**.
  - **Exportação Dual Obrigatória**:
    - `_preview.png`: Imagem em orientação normal para aprovação do cliente.
    - `_transfer.png`: Imagem espelhada horizontalmente (`ImageOps.mirror`) pronta para prensagem a 200°C.
  - Modo clássico preservado via Pillow para montagem puramente local de cartas pré-existentes.

```powershell
# Geração generativa em lote a partir de arquivo JSON
python cli.py mug --input input/sample_mugs_upscaling_auto.json

# Geração generativa inline
python cli.py mug --mug '{"tema": "Dia dos Professores", "estilo": "Card + Mensagem", "titulo": "Pro Glacy", "mensagem": "Feliz dia dos professores! ❤️", "imagens_referencia": ["foto.jpg"]}'

# Montagem local clássica a partir de cartas existentes
python cli.py mug --images carta1.png carta2.png --mode dual_face
```

---

## 3. Especificações Físicas Homologadas da Studio Kustom

| Produto / Substrato | Dimensões Físicas | Resolução 300 DPI | Equipamento Destino | Perfil / Tratamento de Cor |
| :--- | :--- | :--- | :--- | :--- |
| **Carta TCG Individual** | $63 \times 88\text{ mm}$ | $744 \times 1039\text{ px}$ | Konica Minolta C558 | Couché 300g Duplex, TIC $\le 300\%$ |
| **Folha Duplex Super A4** | $230 \times 320\text{ mm}$ | $2717 \times 3780\text{ px}$ | Konica Minolta C558 | Grade 3x3, calhas 12/14mm, verso espelhado |
| **Pôster A4 Kustom** | $210 \times 300\text{ mm}$ | $2480 \times 3543\text{ px}$ | Epson SureColor T3170 | Papel Fotográfico, UltraChrome XD2 |
| **Pôster A3 Kustom** | $300 \times 420\text{ mm}$ | $3543 \times 4960\text{ px}$ | Epson SureColor T3170 | Papel Fotográfico, UltraChrome XD2 |
| **Faixa Caneca 11oz** | $220 \times 95\text{ mm}$ | $2598 \times 1122\text{ px}$ | Epson L110 Sublimática | Transfer Espelhado, Saturação +18%, Prensa 200°C |

---

## 4. Garantia de Qualidade e Suíte de Testes

A integridade do ecossistema é garantida por uma bateria de **103 testes automatizados e 52 subtestes**:

```powershell
# Executar a suíte completa de regressão
pytest tests/ -v

# Executar testes de um módulo específico
pytest tests/test_card_generator/ -v
pytest tests/test_upscaler/ -v
pytest tests/test_background_expander/ -v
pytest tests/test_print_sheet/ -v
pytest tests/test_mug_artist/ -v
```

---

## 5. Próximo Módulo no Roteiro: Gerenciamento e Planejamento de Pedidos (`order_planner`)

Com as 5 ferramentas gráficas homologadas e operacionais, a última etapa de automação da Studio Kustom é o **Planejador e Orquestrador de Pedidos**, operando com arquitetura híbrida (Agente Cognitivo de Triagem + Fila de Atividades com Quality Gates):

### Rotas de Produção Suportadas:
1. **Rota 1 (Apenas Upscaling)**: `upscaler` isolado para redesenho a 300 DPI (A4/A3) com entrega direta da imagem sem folha de corte.
2. **Rota 2 (Pôster Completo)**: `upscaling` &rarr; `fundo (sangria 5mm se tiver)` &rarr; `folha PDF` (com marcas de corte para Epson SureColor T3170).
3. **Rota 3 (Carta TCG)**: `card_generator` &rarr; `folha Super A4 (230x320mm)` duplex casada (para Konica Minolta C558).
4. **Rota 4 (Caneca 11oz)**: `mug_artist` &rarr; `transfer espelhado` com compensação de +18% de saturação (para Epson L110).

### Capacidades:
- **Ingestão Automática de Pastas**: Varredura das pastas em `D:\Desktop\Studio Kustom\04 - Pedidos e Historico\Pedidos\` (ex: `164`, `165`, `176`).
- **Extração Inteligente de Briefing**: Parser cognitivo de textos brutos (`texto.txt`, prints de chat) convertendo em especificações tipadas (`CardInput`, `MugInput`, `PosterSpec`).
- **Fila de Atividades com Quality Gates**: Inspeção matemática e física (resolução, ausência de barras, proporção e sangria) entre cada transição de ferramenta.
- **Rastreamento de Status de Produção**: Gravação de `dossie_producao.json` no diretório do pedido e renomeação opcional para `<numero> - ok`.
