# ROADMAP | Studio Kustom Automation Suite (`sk-tools`)

Este documento estabelece o roteiro de evolução técnica das ferramentas da Studio Kustom, integrando as necessidades comerciais da loja física aos padrões de engenharia de software e computação gráfica.

---

## 1. Ferramenta Concluída e Congelada

- [x] **Ferramenta 1: `card-gen` (Geração de Cartas TCG)**
  - Geração de cartas Magic, Pokémon, Yu-Gi-Oh!, One Piece e Custom.
  - Perfil persistente Chrome + Gemini Web + Injeção de fotos de referência.
  - Validador visual Pillow + Loop de retentativas com reforço de prompt.
  - Encapsulamento completo em `tools/card_generator/` (Tag: `v1.1.0-encapsulated`).

---

## 2. Próximas Ferramentas Planejadas

### Ferramenta 2: Upscaling de Cartas $\to$ Posters A3 / A4 (Vertical e Horizontal)
- **Objetivo**: Elevar a resolução de cartas colecionáveis geradas em baixa/média resolução para formatos gráficos de impressão física em alta definição (300 DPI).
- **Formatos Alvo**:
  - **A4 Vertical**: $210 \times 297\text{ mm}$ ($2480 \times 3508\text{ px}$ a 300 DPI).
  - **A4 Horizontal**: $297 \times 210\text{ mm}$ ($3508 \times 2480\text{ px}$ a 300 DPI).
  - **A3 Vertical**: $297 \times 420\text{ mm}$ ($3508 \times 4960\text{ px}$ a 300 DPI).
  - **A3 Horizontal**: $420 \times 297\text{ mm}$ ($4960 \times 3508\text{ px}$ a 300 DPI).
- **Capacidades Técnicas**:
  - Super-resolução neural (Real-ESRGAN / Lanczos com preservação de nitidez).
  - Remoção de ruídos e artefatos de compressão JPEG/WebP.
  - Reamostragem com perfil de cor seguro para impressão gráfica.

---

### Ferramenta 3: Expansão de Fundo (Outpainting / Canvas Extension)
- **Objetivo**: Estender panoramicamente as laterais ou topo/base de uma ilustração sem esticar ou cortar elementos principais.
- **Caso de Uso Central**:
  - Converter uma arte vertical de carta ($63 \times 88\text{ mm}$ / ratio $\approx 1.4$) em formatos panorâmicos horizontais (posters horizontais ratio $0.71$, e faixas de canecas ratio $2.2$).
- **Capacidades Técnicas**:
  - Expansão generativa de bordas via IA (Outpainting com Gemini/Inpainting local).
  - Content-aware fill inteligente com difusão harmônica de luz e ambiente.
  - Espelhamento suave com desfoque gaussiano de transição para preenchimento de bordas de segurança.

---

### Ferramenta 4: Gerador de Folhas de Impressão (Cartas e Posters A3 / A4)
- **Objetivo**: Automatizar a imposição gráfica de arquivos para envio direto à impressora física, eliminando montagem manual no Photoshop/Corel.
- **Capacidades Técnicas**:
  - **Grade de Cartas em Folha A4**: Montagem automática de até 9 cartas padrão ($63 \times 88\text{ mm}$) por folha A4 em grade $3 \times 3$.
  - **Grade de Cartas em Folha A3**: Montagem de até 18 cartas por folha A3.
  - **Posters em Folha**: Centralização com sangria ($3\text{ mm}$) e margem de segurança.
  - **Marcas de Registro e Corte**: Cruzes e linhas-guia para alinhamento em guilhotina ou refiladora.
  - **Frente e Verso Casado**: Alinhamento milimétrico espelhado para impressão dupla face precisa.
  - **Exportação**: PDF multipágina de alta fidelidade (300 DPI).

---

### Ferramenta 5: Criador de Arte para Caneca
- **Objetivo**: Gerar o gabarito curvo/panorâmico exato para sublimação ou prensagem térmica de canecas cilíndricas.
- **Especificações de Sublimação**:
  - Área total de impressão: $200 \times 95\text{ mm}$ ou $210 \times 95\text{ mm}$ (proporção aprox. $2.1:1$ a $2.2:1$).
  - Resolução a 300 DPI: aprox. $2480 \times 1122\text{ px}$.
- **Capacidades Técnicas**:
  - Distribuição visual equilibrada: arte principal na frente/verso ou vista centralizada oposta à alça.
  - Integração harmônica com a arte da carta (aproveitando o motor de expansão de fundo).
  - Exportação pronta para prensagem térmica.

---

### Ferramenta 6: Gerenciador de Pedidos e Ingestão Automática
- **Objetivo**: Conectar a esteira diretamente à pasta de pedidos da Studio Kustom (`D:\Desktop\Studio Kustom\04 - Pedidos e Historico\Pedidos`).
- **Capacidades Técnicas**:
  - Varredura de pastas de pedidos pendentes.
  - Parser inteligente de arquivos `texto.txt` e extração OCR/multimodal de imagens de descrição `desc*.jpg`.
  - Geração automática do arquivo `card.json` sem necessidade de digitação humana.
  - Atualização de status do pedido (Pendente $\to$ Gerado $\to$ Aprovado $\to$ Impresso).

---

## 3. Espaço para Futuras Ideias e Expansões

Registre aqui novas demandas e produtos que surgirem na operação da loja:

1. **Simulador e Mockup 3D (Three.js)**:
   - Visualização 3D interativa da carta com brilho holográfico/foil e mockup 3D da caneca para envio de prévia de aprovação ao cliente no WhatsApp/Shopee antes de imprimir.
2. **Auditor Automático de OCR Pós-Geração**:
   - Comparação por OCR entre o texto do pedido e o texto renderizado na carta pela IA para detectar pequenas letras trocadas antes da impressão.
3. **Gerador Automático de Etiquetas de Envio e Declarações de Conteúdo**:
   - Integração com a esteira para emitir etiquetas de frete dos pedidos prontos.
4. **Calculadora de Custo de Insumos por Pedido**:
   - Cálculo automático do custo de papel fotográfico, laminação bopp, tinta e embalagem por pedido processado.
