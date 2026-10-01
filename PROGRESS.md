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
