# ADR 0001 — Primeiro provedor temporário de LLM

## Decisão

O primeiro adaptador real usa a Responses API da OpenAI por HTTPX, sem acoplar o
domínio ao SDK do fornecedor. `OPENAI_API_KEY` e `OPENAI_MODEL` são obrigatórios;
nenhum modelo é escolhido silenciosamente.

Toda saída usa JSON Schema estrito e ainda é validada por Pydantic. Há no máximo
uma tentativa de correção de formato, orçamento de chamadas/tokens e timeout. O
conteúdo analisado só sai da máquina após consentimento explícito. O adaptador
pode ser substituído por qualquer implementação dos mesmos protocolos.

## Consequências

- A aplicação funciona integralmente com o fake em testes e demonstrações.
- O modo real depende de credenciais, disponibilidade, preço e política do provedor.
- Chaves, cabeçalhos e texto integral não entram em logs operacionais.
