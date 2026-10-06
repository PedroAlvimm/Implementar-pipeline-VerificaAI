# ADR 0002 — Primeiro provedor de busca

## Decisão

O primeiro adaptador real usa o endpoint Web Search da Brave por HTTPX. A chave
`BRAVE_SEARCH_API_KEY` é enviada apenas em `X-Subscription-Token`. As consultas
usam `country=BR` e `ui_lang=pt-BR`; `search_lang` é omitido para não depender de
um locale não confirmado pelo contrato do provedor.

A busca serve somente para descobrir URLs, títulos e snippets. Respostas geradas,
vereditos ou conteúdo pré-processado pelo mecanismo não entram na decisão factual.
Timeout, quota, rate limit e resposta malformada são erros técnicos explícitos.

## Consequências

- O adaptador pode ser substituído pelo protocolo `SearchProvider`.
- A cobertura depende do índice e do plano contratado.
- Testes usam `FakeSearchProvider` e nunca acessam a internet.
