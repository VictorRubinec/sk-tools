# sk-tools | Studio Kustom Automation Suite

Suite modular de automação para produção gráfica e personalizada da Studio Kustom.

---

## 1. Visão Geral da Arquitetura

O `sk-tools` foi projetado sob o padrão **Modular Toolbox (Facade Pattern)**, onde cada ferramenta reside em seu próprio pacote independente dentro de `tools/`, expondo uma API pública estável e conectando-se a uma CLI unificada.

```text
sk-tools/
├── cli.py                          # Ponto de entrada unificado da CLI (subcomandos)
├── requirements.txt                # Dependências congeladas
├── README.md                       # Documentação técnica do ecossistema
├── ROADMAP.md                      # Roteiro estratégico e técnico das ferramentas
│
├── tools/                          # Ferramentas independentes da Studio Kustom
│   ├── card_generator/             # [HOMOLOGADA / BLINDADA v1.1.0] Geração de cartas TCG
│   │   ├── api.py                  # Fachada pública (generate_single_card, generate_batch)
│   │   ├── core/                   # Schema Pydantic, config e runner com retry
│   │   ├── engine/                 # Matriz de templates e prompt builder
│   │   ├── browser/                # Automação Playwright com sessão persistente
│   │   └── validator/              # Validador de conformidade técnica e TCG (Pillow)
│   └── (novas ferramentas...)
│
├── input/                          # Arquivos de dados de entrada (JSONs e referências)
├── output/                         # Diretório de artefatos gerados
├── scripts/                        # Scripts utilitários de suporte e sessão
└── tests/                          # Suíte de testes automatizados (40 testes de regressão)
    └── test_card_generator/
```

---

## 2. Ferramentas Homologadas

### Ferramenta 1: `card-gen` (Geração de Cartas TCG via Gemini Web)
- **Status**: Estável, encapsulada e congelada na tag `v1.1.0-encapsulated`.
- **Capacidades**:
  - Geração autêntica de cartas de **Magic: The Gathering**, **Pokémon TCG**, **Yu-Gi-Oh!**, **One Piece** e sistemas customizados.
  - Suporte a estilos `Normal` (moldura clássica) e `Fullart` (arte estendida sem cortes).
  - Anexo de fotos reais de clientes como imagens de referência visual mantendo fisionomia.
  - Conexão persistente com Chrome autenticado no Google Gemini (`.chrome_profile`).
  - Monitoramento de streaming, detecção de resposta e extração de bytes (Base64, HTTP e DOM).
  - Validação técnica rigorosa com Pillow: integridade física, resolução mínima ($512\times700\text{ px}$), orientação vertical, aspect ratio canônico de TCG ($1.25$ a $1.65$) e bloqueio de imagens monocromáticas/vazias.
  - Loop automático de retentativas com reforço semântico de prompt e descarte de arquivos reprovados.

#### Como Executar
```powershell
# Autenticação única inicial
python scripts/setup_session.py

# Processamento em lote
python cli.py card-gen --input input/pedidos_reais.json --retries 3

# Processamento de carta avulsa inline
python cli.py card-gen --card '{"tipo": "Magic", "estilo": "Normal", "titulo": "Mago Cósmico"}'

# Verificação de status da sessão
python cli.py card-gen --check-session
```

---

## 3. Garantia de Não-Regressão e Governança

Para assegurar que novas ferramentas não quebrem o gerador de cartas:
1. **Regra de Ouro**: Nenhuma alteração é aceita se a suíte de testes quebrar:
   ```powershell
   python -m unittest discover -s tests -v
   ```
2. **Isolamento**: Nenhuma nova ferramenta deve importar módulos internos de `tools/card_generator/browser/` ou `core/`. Toda interação deve ocorrer estritamente através de `tools.card_generator.api`.
