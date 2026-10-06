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

## Tarefa 4 — Coleta, extração e artefatos

Concluída.

- Coletor com cache limitado, rate limiting por domínio e limite de tamanho.
- Conteúdo não HTML, timeout, `robots.txt`, login, CAPTCHA e paywall têm erros distintos.
- Extração combina Trafilatura, BeautifulSoup e JSON-LD preservando o texto original.
- HTML permitido é comprimido atomicamente fora do SQLite, com SHA-256 e cota cumulativa.
- Verificação: `75 passed`; Ruff sem erros.

## Tarefa 5 — LLM, claims e consultas

Concluída.

- Contratos independentes para extração de claims e geração de consultas.
- Primeiro adaptador real usa Responses API via HTTPX e JSON Schema estrito.
- Nenhum modelo padrão é ocultado; chave, modelo e consentimento são obrigatórios.
- Saídas fora do schema recebem uma única correção e depois falham explicitamente.
- Claims sem trecho literal são rejeitadas; IDs e URLs externos ao conjunto são bloqueados.
- Orçamento de chamadas e tokens é verificado antes de cada requisição.
- Verificação: `91 passed`; Ruff sem erros.

## Tarefa 6 — Busca e independência de fontes

Concluída.

- Primeiro adaptador real usa Brave Web Search apenas para descobrir páginas.
- Resultados preservam consulta, ranking, snippet, domínio e data quando disponível.
- Domínios e caminhos de fact-checking são excluídos por configuração auditável.
- URLs são canonicalizadas e deduplicadas sem remover parâmetros funcionais.
- Cópias exatas, aproximadas e republicações declaradas recebem o mesmo grupo.
- Metadados de fonte são descritivos e não geram probabilidade de verdade.
- Verificação: `103 passed`; Ruff sem erros.

## Tarefa 7 — Chunking e ranking

Concluída.

- Trechos têm tamanho, sobreposição, índice e identificadores determinísticos.
- Texto, URL, título, data, documento e grupo de independência são preservados.
- Ranking BM25 puro combina entidades, números, datas, título e adequação temporal.
- Bônus oficial só existe quando a claim ou consulta exige documento oficial.
- Cada resultado expõe fatores auditáveis; não há probabilidade de verdade.
- No máximo cinco grupos independentes são selecionados por claim.
- Verificação: `110 passed`; Ruff sem erros.

## Tarefa 8 — Julgamento, agregação e relatórios

Concluída.

- Julgamentos usam contratos estritos e aceitam somente IDs fornecidos ao modelo.
- Toda citação é mapeada de volta para caracteres literais da evidência armazenada.
- Uma saída inválida recebe uma única tentativa de correção e depois falha explicitamente.
- Agregação considera independência, fonte primária e adequação temporal.
- Cópias do mesmo conteúdo não contam como confirmações independentes.
- Erros técnicos e evidência insuficiente permanecem distintos de refutação.
- Relatórios rejeitam claims, evidências, URLs ou conclusões factuais sem lastro.
- Verificação: `125 passed`; Ruff sem erros.

## Tarefa 9 — Pipeline, jobs e recuperação

Concluída.

- Pipeline síncrono persiste entrada limpa, claims, consultas, resultados, evidências,
  decisões e relatório, com estado durável entre cada etapa.
- Entradas de texto e URL percorrem o mesmo fluxo após a coleta segura.
- Cenários demo cobrem `SUPPORTED`, `REFUTED`, `NEI` e `CONFLICTING` sem rede.
- Falha técnica de coleta permanece distinta de ausência de evidência.
- Limites por análise cobrem cinco minutos, chamadas, tokens e armazenamento.
- Conclusão parcial lista limitações por claim; reexecução terminal não duplica custo.
- Executor aceita duas análises ativas e dez na fila, rejeitando excesso explicitamente.
- Jobs duplicados são reaproveitados; exceções ficam registradas sem derrubar os workers.
- Reinícios marcam trabalhos interrompidos como falha técnica recuperável.
- Verificação: `141 passed`; Ruff sem erros.
