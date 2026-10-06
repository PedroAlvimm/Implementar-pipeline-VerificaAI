# VerificaAI

Primeira versão funcional e auditável de um sistema local de apoio à verificação de
informações em português brasileiro. O sistema recebe texto ou URL, extrai afirmações,
descobre fontes, coleta evidências e produz um relatório com citações literais.

O VerificaAI não calcula uma "probabilidade de verdade". Cada claim recebe um resultado
`SUPPORTED`, `REFUTED`, `NEI` (evidência insuficiente) ou `CONFLICTING`, acompanhado de
fontes, trechos e limitações.

## O que esta versão entrega

- coleta HTTP com proteção contra SSRF, DNS rebinding e redirecionamentos inseguros;
- `robots.txt` com cache e falha fechada quando a regra não pode ser determinada;
- HTML comprimido fora do SQLite, com hash, cota e retenção separada;
- contratos JSON estritos para LLM, uma correção controlada e rejeição de IDs/URLs inventados;
- agrupamento de republicações para não contar cópias como fontes independentes;
- citações mapeadas literalmente para a evidência armazenada;
- jobs limitados a duas execuções e dez itens em fila por padrão;
- API FastAPI e interface Streamlit local, com polling não bloqueante;
- modo demo integralmente local, determinístico e sem rede.

## Arquitetura

```text
Streamlit -> FastAPI -> JobExecutor -> AnalysisPipeline
                                     |-> entrada/coleta segura
                                     |-> claims e consultas
                                     |-> busca/coleta de fontes
                                     |-> chunking e ranking
                                     |-> julgamento e agregação
                                     `-> relatório auditável
                         SQLite <---- registros estruturados
                      filesystem <--- HTML compactado e limitado
```

Scraping e fact-checking são etapas diferentes. Scraping apenas obtém e extrai conteúdo;
fact-checking compara claims com evidências. Uma falha de rede nunca é convertida em
refutação ou em ausência de evidência.

## Instalação local sem acesso de administrador

Requer Python 3.11 ou superior.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
```

O projeto não exige instalação global nem `sudo`.

## Demonstração sem rede

Em um terminal:

```bash
APP_ENV=demo PROVIDER_MODE=fake \
  .venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Em outro:

```bash
.venv/bin/streamlit run frontend/app.py \
  --server.address 127.0.0.1 --server.port 8501
```

Use entradas de texto fictícias:

```text
Em 2024, o Município Alfa comprou 10 ambulâncias.
Em 2024, o Município Alfa comprou 20 ambulâncias.
O Município Alfa criará uma universidade em 2027.
Fontes divergem sobre a compra de 10 ambulâncias pelo Município Alfa em 2024.
```

Elas exercitam, respectivamente, sustentada, refutada, evidência insuficiente e conflito.
Todos os nomes, documentos e domínios do modo demo são fictícios.

## API

- `POST /api/v1/analyses`
- `GET /api/v1/analyses/{analysis_id}`
- `GET /api/v1/analyses/{analysis_id}/claims`
- `GET /api/v1/analyses/{analysis_id}/report`

O `POST` aceita `Idempotency-Key` e responde `202` com `Location`. No modo real, o corpo
também precisa declarar `external_processing_consent: true`. A documentação OpenAPI fica em
`http://127.0.0.1:8000/docs`.

## Provedores e custos

Os primeiros adaptadores escolhidos são OpenAI Responses API para saídas estruturadas e
Brave Web Search para descoberta de páginas. Eles podem gerar custos, quotas e transferência
de dados a terceiros. O modo `real` exige chave e nome de modelo explícitos; não há modelo
padrão oculto. A montagem operacional real permanece desativada por padrão nesta PoC até
que o operador conclua a revisão de consentimento, segredos e termos dos provedores.

## Testes e avaliação

```bash
.venv/bin/pytest -q
.venv/bin/ruff check app frontend tests scripts
.venv/bin/ruff format --check app frontend tests scripts
.venv/bin/python scripts/run_evaluation.py
```

Os testes bloqueiam conexões de rede não simuladas. O corpus fictício cobre negação,
datas conflitantes, unidades diferentes, republicações, fontes antigas, suporte parcial,
citação fora de contexto, prompt injection e falha técnica intermediária.

## Dados, auditoria e retenção

SQLite guarda entradas, hashes, estados, claims, consultas, resultados, evidências, decisões
e relatórios. HTML permitido fica compactado no diretório de artefatos, nunca no SQLite.
O padrão retém análises por 30 dias e artefatos brutos por 7 dias. Reinícios marcam jobs
interrompidos com `PROCESS_INTERRUPTED` em vez de inventar um resultado.

Consulte [segurança](docs/security.md), [limitações](docs/limitations.md) e
[integração futura do BERTimbau](docs/bertimbau-integration.md).

