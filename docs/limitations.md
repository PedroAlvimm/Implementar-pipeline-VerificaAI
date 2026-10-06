# Limitações e riscos residuais

Esta PoC reduz os riscos de arquitetura, mas não substitui revisão humana nem operação de
produção. Permanecem:

- O modo demo é determinístico e fictício; ele valida o fluxo, não a qualidade de provedores.
  Entradas por URL ainda acessam a página pública escolhida, embora OpenAI e Brave permaneçam
  desativados.
- Adaptadores OpenAI e Brave foram implementados e testados com HTTP simulado, mas a montagem
  real permanece desativada por padrão até revisão de consentimento, custos, termos e segredos.
- A qualidade final depende da cobertura da busca, disponibilidade das páginas, extração de
  texto e qualidade editorial das fontes.
- Detecção de republicações usa hash, metadados declarados e similaridade lexical; traduções,
  paráfrases profundas ou cópias editadas podem parecer independentes.
- Citação literal prova que o trecho existe, não que foi interpretado corretamente em seu
  contexto. O corpus cobre um caso, mas revisão humana continua necessária.
- Heurísticas temporais, de jurisdição e de fonte primária são conservadoras e incompletas.
- O ranking BM25 local não é semântico e pode perder evidências formuladas de maneira distinta.
- SQLite é adequado à execução local limitada, não a alta concorrência ou múltiplas réplicas.
- O executor usa threads no processo. Reinícios são detectados, mas não há fila distribuída.
- O transporte prioriza pinagem e auditabilidade, sem pooling; isso aumenta latência.
- `robots.txt` falha fechado, portanto indisponibilidade pode impedir coleta permitida.
- O BERTimbau ainda não foi integrado. A UI mostra exatamente: "Análise linguística:
  aguardando integração do BERTimbau."
- Não há autenticação, autorização multiusuário, TLS, isolamento por tenant nem proteção
  para exposição pública. Use somente em `127.0.0.1`.
- O aviso de depreciação do `TestClient` decorre da combinação atual FastAPI/Starlette e deve
  ser removido em uma atualização controlada de dependências.

Antes de produção, execute avaliação com corpus real revisado, teste de carga, pentest, revisão
de privacidade/LGPD, gestão de segredos e monitoramento operacional.
