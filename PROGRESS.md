# Progresso do VerificaAI

## Estado inicial

- Especificação e plano aprovados.
- Implementação nativa iniciada na branch `feature/verificaai-poc`.
- O diretório inicial não continha código, testes ou configuração.

## Tarefa 1 — Fundação

Concluída.

- Criados configuração centralizada, enums, resultados tipados e logging com redação.
- Criados `RiskAnalyzer`, `DisabledRiskAnalyzer` e o adaptador vazio do BERTimbau.
- Adicionado bloqueio automático de rede não simulada nos testes.
- Decisão: o modo fake só funciona explicitamente em `test` ou `demo`.
- Decisão: o modo real exige chave e nome do modelo, sem modelo padrão oculto.
- Verificação: `9 passed`; Ruff sem erros.

## Tarefa 2 — Persistência e auditoria

Concluída.

- Criados modelos SQLAlchemy para análises e objetos auditáveis do pipeline.
- Implementadas máquina de estados, idempotência com hash e recuperação após reinício.
- Ativado WAL em bancos SQLite persistidos e chaves estrangeiras em toda conexão.
- Implementada retenção de 30 dias para análises e 7 dias para artefatos brutos.
- HTML permanece fora do SQLite; documentos guardam somente caminho, hash e metadados.
- Verificação: `26 passed`; Ruff sem erros.

## Tarefa 3 — Segurança de entrada e SSRF

Concluída.

- Validação de texto e URL com preservação de números, acentos e negação.
- Bloqueio explícito de loopback, redes privadas, link-local, multicast, reservados,
  não especificados, documentação e representações numéricas ambíguas.
- Todos os endereços A/AAAA são validados e a conexão usa o IP aprovado com Host/SNI.
- Redirecionamentos são manuais, revalidados e removem credenciais ao mudar de origem.
- `robots.txt` usa cache, respeita regras e falha fechado quando está indisponível.
- Limitação residual: o transporte local não implementa pooling; isso privilegia isolamento
  e auditabilidade na PoC, com custo de latência por conexão.
- Verificação: `62 passed`; Ruff sem erros.
