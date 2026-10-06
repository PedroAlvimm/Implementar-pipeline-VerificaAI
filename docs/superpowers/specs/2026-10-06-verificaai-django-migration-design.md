# VerificaAI — migração integral para Django

**Data:** 2026-10-06  
**Status:** desenho aprovado e revisado com requisitos de execução auditável; aguardando
aprovação da especificação escrita

## 1. Objetivo

Transformar o VerificaAI em uma aplicação web Python unificada, baseada em Django, sem perder
as garantias de segurança, auditabilidade e separação entre análise linguística e verificação
factual já existentes.

A migração substitui integralmente FastAPI, Streamlit e SQLAlchemy por Django, Django REST
Framework, templates Django e Django ORM. PyTorch e Transformers permanecem responsáveis pela
inferência local do BERTimbau. A primeira versão continua executável em uma única máquina com
SQLite e fila local limitada, sem exigir Redis ou outros serviços.

O resultado será uma aplicação Django única que oferece interface web, API compatível,
persistência, administração local e execução assíncrona limitada.

## 2. Princípios obrigatórios

1. O veredito factual depende somente de afirmações, fontes, evidências e decisões auditáveis.
2. O BERTimbau é um sinal linguístico auxiliar e nunca participa da agregação factual.
3. Falha de rede, provedor ou modelo não pode ser convertida em ausência de evidência.
4. Citações factuais devem existir literalmente nas evidências persistidas.
5. Republicações não podem ser contadas como fontes independentes.
6. Coleta de URL mantém proteção contra SSRF, DNS rebinding e redirecionamentos inseguros.
7. HTML potencialmente volumoso permanece comprimido no filesystem, fora do banco.
8. Cada fase da migração deve permanecer executável e testada.
9. O banco legado é preservado; nenhuma etapa destrutiva é automática.
10. O corte remove completamente FastAPI, Streamlit e SQLAlchemy somente após equivalência
    funcional comprovada.
11. Reexecuções criam novos registros imutáveis; resultados anteriores nunca são sobrescritos.
12. Toda execução registra versões suficientes para explicar e reproduzir seu comportamento.
13. Detector de fake news e recuperação/ranking semântico são capacidades distintas, sem
    compartilhamento implícito de scores ou modelos.
14. Esta arquitetura delimita uma aplicação local; operação pública em produção exige uma
    etapa arquitetural posterior.

## 3. Arquitetura de destino

```text
Navegador
   |
   v
Templates Django + polling HTTP
   |
   v
Views Django / Django REST Framework
   |
   v
Serviço de análises + AnalysisRun + fila local limitada
   |-- coleta segura de entrada e URLs
   |-- extração e validação de afirmações
   |-- descoberta, coleta e ranking de evidências
   |-- julgamento e agregação factual
   |-- persistência do relatório factual
   `-- BERTimbau auxiliar, isolado e limitado
   |
   v
Django ORM ----> SQLite do Django
   |
   `----------> artefatos comprimidos no filesystem
```

O pipeline de domínio não conhecerá `HttpRequest`, serializers, templates ou detalhes do ORM.
Views e endpoints chamarão uma fachada de aplicação com contratos explícitos. Adaptadores do
Django traduzirão modelos persistidos para os objetos do domínio e vice-versa.

### 3.1 Componentes

- **`config`**: projeto Django, settings, URLs, ASGI/WSGI e configuração por ambiente.
- **`analyses`**: modelos, migrations, repositórios Django, serviços de aplicação, views,
  serializers, templates e comandos administrativos.
- **`ingestion` e `scraping`**: validação e coleta segura, preservadas como módulos de domínio.
- **`claims`, `search`, `evidence` e `fact_checking`**: regras existentes independentes do web
  framework.
- **`risk_analysis`**: contrato tipado, cache e inferência local do BERTimbau.
- **`semantic_ranking`**: fronteira reservada para um futuro modelo de recuperação ou
  reranking; não usa o detector BERTimbau e não faz parte desta entrega.
- **`reports`**: construção e validação do relatório auditável.
- **`jobs`**: interface de execução assíncrona e implementação local limitada.
- **`observability`**: contexto de correlação, logs estruturados e métricas operacionais.

O Django Admin permitirá inspeção de análises, estados, limitações e relatórios. Segredos,
HTML bruto, cookies, cabeçalhos de autorização e conteúdo sensível não serão exibidos.

## 4. Persistência com Django ORM

O Django ORM substituirá todas as sessões, modelos e repositórios SQLAlchemy. Os modelos de
destino preservarão os conceitos atuais:

| Modelo Django | Conteúdo principal |
|---|---|
| `Analysis` | identidade estável da solicitação, entrada, hash e estado agregado |
| `AnalysisRun` | uma execução auditável, ordinal, versões, estado, erro e timestamps |
| `Job` | tentativa assíncrona, lease, retry, estado e correlation IDs |
| `BERTAnalysis` | execução auxiliar ligada ao run, estado, versão, rótulo e score |
| `Claim` | afirmação validada de um run, prioridade, tipo e entidades |
| `Query` | consultas geradas por afirmação e versão do gerador |
| `SearchResult` | metadados de resultados descobertos por run |
| `Evidence` | trecho, fonte, grupo de independência e datas por run |
| `Decision` | decisão por evidência, citação validada e versão do julgador |
| `Report` | relatório imutável de um run e versão do contrato |
| `Artifact` | caminho relativo, hash, tamanho, compressão e retenção por run |

Chaves primárias, identificadores de domínio e timestamps legados serão preservados quando
existirem. Restrições de unicidade e relacionamentos impedirão duplicação silenciosa. Payloads
JSON continuarão disponíveis onde a evolução do contrato exigir flexibilidade, mas campos
consultados ou relacionais terão colunas próprias.

SQLite permanece como padrão local. A modelagem e as transações não dependerão de extensões
específicas, permitindo migração futura para PostgreSQL sem fazer parte desta entrega.

### 4.1 Constraints de banco

As invariantes abaixo serão declaradas nas migrations por `UniqueConstraint`, `CheckConstraint`,
`ForeignKey`/`OneToOneField` e nulabilidade. Validação apenas em serializer ou `clean()` não é
suficiente.

Regras comuns:

- chaves públicas serão UUIDs imutáveis e timestamps obrigatórios usarão UTC;
- todo campo de estado terá `choices` e `CheckConstraint` com os valores permitidos;
- relações auditáveis usarão `PROTECT`; arquivamento e retenção não apagarão resultados;
- `finished_at` não poderá preceder `started_at`; lease expirado não poderá preceder heartbeat;
- contadores, ordinais, tamanhos e números de tentativa serão não negativos, e ordinais começam
  em 1;
- hashes terão tamanho e formato validados pela aplicação e comprimento fixo no schema;
- campos obrigatórios do manifesto não aceitarão string vazia nem `NULL`.

Constraints por agregado:

- `Analysis`: `input_type` limitado a `text|url`, entrada não vazia e `idempotency_key` única
  quando presente; reutilização da mesma chave com outro hash será conflito, não deduplicação;
- `AnalysisRun`: unicidade `(analysis_id, ordinal)`, `ordinal >= 1` e no máximo um run em estado
  não terminal por análise por meio de constraint única condicional;
- `Job`: unicidade `(run_id, attempt_number)`, `attempt_number >= 1`, no máximo um job ativo por
  run e `retry_of_id != id`; lease/heartbeat serão nulos fora de `RUNNING`;
- `BERTAnalysis`: unicidade `(run_id, ordinal)`; `AVAILABLE` exige rótulo
  `FALSA|VERDADEIRA`, score finito entre 0 e 1, modelo e versão; outros estados não podem
  carregar rótulo ou score;
- `Claim`: unicidade `(run_id, claim_key)`;
- `Query`: unicidade `(run_id, claim_id, normalized_query_hash)`;
- `SearchResult`: unicidade `(run_id, canonical_url_hash)` após deduplicação;
- `Evidence`: unicidade `(run_id, evidence_key)` e referência obrigatória ao run e à fonte;
- `Decision`: unicidade `(run_id, claim_id, evidence_id)` e referências pertencentes ao mesmo
  run, esta última validada transacionalmente pelo serviço;
- `Report`: relação um-para-um com `AnalysisRun` e versão de schema obrigatória;
- `Artifact`: unicidade `(run_id, relative_path)`, tamanho não negativo e hash obrigatório;
  caminho relativo seguro é validado antes da gravação e da leitura.

SQLite não consegue expressar todas as invariantes relacionais entre várias tabelas. As que não
couberem em constraint nativa serão protegidas por serviço transacional e teste concorrente, e
serão listadas como candidatas a constraint/trigger na futura migração PostgreSQL.

### 4.2 Índices

Além dos índices criados por PKs, FKs e constraints únicas, as migrations declararão somente os
índices exigidos pelos caminhos de consulta:

| Nome lógico | Campos | Uso |
|---|---|---|
| `analysis_state_created_idx` | `Analysis(state, created_at)` | histórico e operação |
| `analysis_input_hash_idx` | `Analysis(input_hash)` | auditoria/deduplicação sem indexar texto |
| `run_analysis_created_idx` | `AnalysisRun(analysis_id, created_at)` | histórico de runs |
| `run_state_updated_idx` | `AnalysisRun(state, updated_at)` | recuperação e acompanhamento |
| `job_queue_idx` | `Job(state, available_at, created_at)` | retirada ordenada da fila |
| `job_lease_idx` | `Job(state, lease_expires_at)` | detecção de jobs órfãos |
| `job_request_idx` | `Job(request_id)` | correlação operacional |
| `claim_run_priority_idx` | `Claim(run_id, priority)` | relatório e execução |
| `query_claim_idx` | `Query(run_id, claim_id)` | trilha de busca |
| `result_run_domain_idx` | `SearchResult(run_id, domain_hash)` | auditoria de fontes |
| `evidence_claim_rank_idx` | `Evidence(run_id, claim_id, rank)` | seleção e relatório |
| `evidence_independence_idx` | `Evidence(run_id, independence_group)` | deduplicação |
| `decision_claim_idx` | `Decision(run_id, claim_id)` | agregação factual |
| `bert_run_state_idx` | `BERTAnalysis(run_id, state)` | painel auxiliar |
| `artifact_expiry_idx` | `Artifact(retain_until)` | retenção |

Não serão indexados texto original, HTML, citações, prompts preenchidos ou URLs completas. Os
índices usarão IDs e hashes de cardinalidade controlada. `EXPLAIN` em fixtures representativas
confirmará os caminhos críticos; índices sem consulta comprovada não serão adicionados.

### 4.3 Reexecuções e imutabilidade

`Analysis` representa a solicitação e sua entrada canônica. Cada execução cria um novo
`AnalysisRun` com ordinal crescente e nunca reutiliza as linhas de claims, consultas,
evidências, decisões, artefatos ou relatório de outro run. A ação “executar novamente” cria um
run e um job novos; ela não limpa nem modifica o run anterior.

O estado exibido em `Analysis` é o estado agregado do run mais recente, enquanto histórico e
API permitem selecionar qualquer run. Idempotência do `POST` inicial evita análises duplicadas;
idempotência de reexecução vale somente para a mesma chave e mesma operação de criação de run.

### 4.4 Versionamento integral do pipeline

Cada `AnalysisRun` armazenará um manifesto imutável com:

- versão lógica e hash da configuração do pipeline;
- commit Git da aplicação e indicação explícita de árvore modificada quando aplicável;
- versão do schema do relatório e das migrations Django;
- provedor, modelo, revisão e parâmetros de cada LLM;
- versão e SHA-256 de cada prompt ou template usado;
- versão do gerador de consultas, chunking, ranking, agregação e validação de citações;
- snapshot dos limites que alteram comportamento;
- identificador e manifesto de hashes do BERTimbau;
- versões relevantes de Python, Django, Transformers e PyTorch.

Segredos e conteúdo sensível nunca entram no manifesto. Se uma versão obrigatória não puder ser
determinada, o run não será apresentado como reproduzível e registrará uma limitação explícita.

### 4.5 Máquinas de estado

Transições serão implementadas por métodos de serviço transacionais; alterações diretas de
estado pelo Admin ou por `save()` genérico serão bloqueadas.

**`Analysis`**

```text
CREATED -> RUNNING
CREATED -> FAILED
RUNNING -> COMPLETED | COMPLETED_WITH_LIMITATIONS | FAILED
COMPLETED | COMPLETED_WITH_LIMITATIONS | FAILED -> RUNNING  (novo AnalysisRun)
qualquer estado terminal -> ARCHIVED
```

`Analysis` reflete o run mais recente. Uma reexecução não reabre nem modifica o run anterior.

**`AnalysisRun`**

```text
PENDING -> COLLECTING -> EXTRACTING_CLAIMS -> SEARCHING -> CHECKING
        -> FACTUAL_COMPLETED -> COMPLETED
                             -> COMPLETED_WITH_LIMITATIONS
qualquer estado não terminal -> FAILED | INTERRUPTED
```

`FACTUAL_COMPLETED` significa que o relatório factual já foi persistido e pode ser entregue,
mesmo que o BERTimbau ainda esteja pendente ou falhe.

**`Job`**

```text
QUEUED -> RUNNING -> SUCCEEDED
                  -> FAILED
                  -> INTERRUPTED
QUEUED -> CANCELLED
FAILED | INTERRUPTED --política de retry--> novo Job em QUEUED
```

Cada `Job` representa uma tentativa e preserva número, causa, horários e lease. Não existe
transição de um estado terminal de volta para `RUNNING`; retry cria outro `Job` auditável com
referência `retry_of` para a tentativa anterior.

**`BERTAnalysis`**

```text
PENDING -> RUNNING -> AVAILABLE
                   -> TECHNICAL_ERROR
                   -> TIMED_OUT
PENDING -> DISABLED
RUNNING -> INTERRUPTED
```

Estados terminais são imutáveis. Um novo teste linguístico exige outro `BERTAnalysis`, ligado ao
mesmo run ou a um novo run conforme a ação solicitada.

## 5. Migração do banco legado

O banco SQLAlchemy atual nunca será alterado diretamente. A aplicação Django usará um novo
arquivo SQLite, e o banco antigo ficará preservado como fonte somente leitura e arquivo de
auditoria.

O comando abaixo fará a importação:

```text
python manage.py migrate_legacy_data --source <sqlite-legado> [--dry-run]
```

O comando terá as seguintes propriedades:

- transação única ou lotes transacionais com checkpoint explicitamente auditado;
- validação do schema legado antes da primeira gravação;
- preservação de IDs, datas, estados, relações e payloads;
- conversão de cada análise legada em `Analysis` e `AnalysisRun` ordinal 1, sem reescrever o
  significado do resultado original;
- idempotência por chaves estáveis, sem duplicar registros na repetição;
- `--dry-run` com contagens e inconsistências, sem gravações;
- rollback integral do lote em caso de erro;
- reconciliação final de contagens, relações órfãs, estados e hashes;
- relatório JSON de migração para auditoria;
- validação e normalização de caminhos de artefatos sob a raiz permitida;
- nenhuma exclusão ou renomeação automática do banco antigo.

Uma análise com dados inconsistentes será rejeitada ou marcada no relatório de migração; o
importador não inventará relações ou valores ausentes.

## 6. API compatível

Django REST Framework preservará, sempre que o contrato atual permitir:

- `POST /api/v1/analyses`
- `GET /api/v1/analyses/{analysis_id}`
- `GET /api/v1/analyses/{analysis_id}/claims`
- `GET /api/v1/analyses/{analysis_id}/report`
- `GET /api/v1/analyses/{analysis_id}/runs`
- `POST /api/v1/analyses/{analysis_id}/runs`
- `GET /api/v1/analyses/{analysis_id}/runs/{run_id}/report`

Serão mantidos códigos HTTP, `Idempotency-Key`, `Location`, validação de entrada, consentimento
para provedores externos e distinção entre análise pendente, em execução, concluída, concluída
com limitações e falha técnica. Alterações inevitáveis serão documentadas e cobertas por testes
de contrato antes do corte.

Templates e clientes externos usarão a mesma API. Regras de negócio não serão duplicadas em
views HTML.

## 7. Interface Django

A interface substituirá integralmente o Streamlit e oferecerá:

- seleção entre texto e URL;
- formulário de entrada e consentimento quando aplicável;
- início de análise sem bloquear a requisição;
- progresso por polling dos endpoints de status;
- relatório por afirmação, com rótulo textual além de cor;
- fontes e citações literais clicáveis;
- limitações técnicas separadas de `NEI`;
- painel independente da análise linguística auxiliar;
- histórico local e reabertura de análises concluídas;
- reexecução explícita que preserva e permite comparar runs anteriores;
- mensagens de erro em português brasileiro.

Templates Django produzirão HTML no servidor. JavaScript pequeno e sem framework será usado
somente para envio assíncrono, polling e atualização progressiva. A interface continuará útil
com recarregamento manual quando JavaScript estiver indisponível.

## 8. Jobs e concorrência

A primeira versão usará uma implementação local de uma interface `JobExecutor`, baseada em
`ThreadPoolExecutor`, com os limites atuais de concorrência e fila. Isso evita Redis e processos
adicionais durante a migração.

Requisitos:

- submissão idempotente;
- limite explícito de workers e itens aguardando;
- rejeição controlada quando a capacidade acabar;
- recuperação de jobs interrompidos após reinício;
- lease persistido com heartbeat para distinguir job ativo de processo morto;
- nenhum bloqueio da thread de requisição durante uma análise;
- transações curtas e conexões ORM abertas somente quando necessárias;
- interface substituível futuramente por Celery sem alterar o pipeline.

Celery e Redis ficam fora do escopo desta entrega.

### 8.1 Retry e backoff

Retries serão definidos por categoria, nunca por um `except Exception` genérico:

| Categoria | Política |
|---|---|
| validação de entrada, SSRF, `robots.txt` negado, schema ou hash inválido | sem retry |
| timeout, reset de conexão, DNS público temporariamente indisponível | até 2 novas tentativas, backoff exponencial com jitter |
| HTTP `429` | respeitar `Retry-After`, limitado pelo orçamento total; no máximo 2 tentativas |
| HTTP `5xx` transitório | até 2 novas tentativas com jitter; `4xx` não recebe retry, exceto `429` |
| saída LLM inválida | uma correção controlada já prevista; depois falha explícita |
| bucket/modelo BERT indisponível | até 2 tentativas de materialização; inferência inválida não é repetida automaticamente |
| SQLite ocupado | poucas tentativas curtas e limitadas; esgotamento vira erro operacional explícito |
| erro determinístico de código, integridade ou permissão | sem retry automático |

O backoff respeitará deadline e orçamento do run. Cada tentativa cria ou atualiza registros de
tentativa auditáveis, preserva a causa anterior e nunca duplica efeitos já confirmados. A
aleatoriedade do jitter será injetável para testes determinísticos.

### 8.2 Crash recovery real

No startup, o executor reconciliará jobs `RUNNING` cujo lease expirou. Eles serão marcados como
`INTERRUPTED`; somente etapas idempotentes elegíveis gerarão uma nova tentativa `QUEUED`.
Estados e checkpoints persistidos decidirão onde retomar, sem inferir sucesso pela ausência de
erro.

Os testes iniciarão um worker em subprocesso, interromperão o processo durante etapas
controladas e iniciarão outro processo contra o mesmo banco. Eles verificarão lease expirado,
estado `INTERRUPTED`, retry permitido, ausência de duplicação e preservação do relatório factual
quando o crash ocorrer depois de `FACTUAL_COMPLETED`.

### 8.3 Limite de SQLite com threads

SQLite é aceitável somente para a versão local, com poucos workers e uma única instância da
aplicação. Escritas concorrentes são serializadas pelo banco e podem gerar `database is locked`;
transações longas, compartilhamento de conexões entre threads e múltiplos processos aumentam o
risco. Cada thread usará sua própria conexão, transações serão curtas, WAL e timeout serão
configurados e a concorrência continuará baixa e explícita.

Essas medidas reduzem contenção, mas não transformam SQLite em banco de produção concorrente.
PostgreSQL é requisito da futura etapa de produção pública.

### 8.4 Lifecycle do `ThreadPoolExecutor`

O executor será propriedade de um `LocalJobRuntime` com máquina de lifecycle interna
`NEW -> RUNNING -> DRAINING -> STOPPED`. Não haverá pool global criado em import, singleton
implícito em módulo nem inicialização em `AppConfig.ready()`, porque essas opções abrem threads
durante migrations, testes e comandos administrativos.

Lifecycle obrigatório:

1. **Inicialização:** o serviço de aplicação chama `start()` explicitamente ou no primeiro
   `submit()`. A operação é thread-safe e idempotente. Antes de aceitar jobs, ela fecha conexões
   herdadas, reconcilia leases expirados e só então cria o pool.
2. **Operação:** existe um runtime por processo e cada job passa por um wrapper que chama
   `close_old_connections()` antes e depois do trabalho, estabelece correlation IDs, renova o
   lease e converte exceções em estados persistidos.
3. **Submissão:** somente `RUNNING` aceita trabalho. `DRAINING` e `STOPPED` rejeitam com erro de
   capacidade/indisponibilidade sem criar um job órfão. A reserva da capacidade e a criação do
   `Job` são coordenadas para impedir oversubscription.
4. **Shutdown gracioso:** parar de aceitar jobs, cancelar futures ainda não iniciados sem tirar
   seus registros de `QUEUED`, esperar futures ativos até `JOB_SHUTDOWN_GRACE_SECONDS`, fechar
   conexões e chamar `shutdown(wait=False, cancel_futures=True)` depois da espera limitada.
   `shutdown()` é idempotente.
5. **Encerramento forçado:** threads Python não serão mortas de forma insegura. Se o processo
   terminar após o período de graça, leases dos jobs ativos expiram; o próximo runtime os marca
   `INTERRUPTED` e aplica a política de recovery.

O entrypoint local instalará handlers de `SIGTERM`/`SIGINT` e fallback `atexit` de melhor
esforço. O servidor de desenvolvimento será documentado com autoreload desativado, evitando
dois processos e dois pools. Fork depois da criação do pool é proibido. A configuração local
rejeitará múltiplos processos web, pois cada processo criaria seu próprio executor contra o
mesmo SQLite.

`ThreadPoolExecutor` não consegue interromper com segurança uma função Python já iniciada, e
`wait=False` não garante que o interpretador saia enquanto threads não daemon permanecem
ativas. Se o período de graça expirar, o runtime registra o evento e depende de segundo sinal ou
`SIGKILL` do operador/supervisor; a recuperação acontece pelos leases no próximo processo. Essa
limitação é mais um motivo para a futura produção usar workers isolados em processos.

Testes de lifecycle cobrirão `start()` e `shutdown()` repetidos, submissão durante drenagem,
cancelamento de itens não iniciados, espera limitada, fechamento de conexões, ausência de
threads após a fixture e recuperação por lease depois de `SIGKILL` em subprocesso.

## 9. BERTimbau auxiliar

O modelo continuará vindo diretamente do bucket
`Alvinn007/bertimbau-fakenews-detector-v4-bucket`. O snapshot aceito fixa tamanho,
identificador Xet e SHA-256 de `config.json`, `model.safetensors`, `tokenizer.json` e
`tokenizer_config.json`.

O fluxo será deliberadamente posterior ao factual:

1. produzir e persistir o relatório factual;
2. marcar a etapa linguística como pendente;
3. executar o BERTimbau sob timeout próprio;
4. validar integralmente o resultado;
5. anexar `available`, `disabled` ou `technical_error` ao relatório sem alterar claims.

O factual continuará disponível se o download, carregamento ou inferência travar ou falhar. O
resultado linguístico será validado quanto a status, rótulo, score finito entre zero e um,
modelo, versão e mensagem segura.

O cache terá estas garantias:

- diretório com allowlist exata dos quatro arquivos, sem extras ou links simbólicos;
- validação de tamanho e SHA-256 antes de cada carga inicial do processo;
- download em staging e promoção atômica;
- bloqueio entre processos durante instalação e nova verificação depois do bloqueio;
- nunca remover um snapshot válido antes de a substituição estar pronta;
- `safetensors`, `local_files_only=True` e `trust_remote_code=False`;
- entrada limitada a 512 tokens, com truncamento explícito no relatório;
- carregamento único por processo e inferência serializada quando necessário.

Um snapshot local já validado permanece utilizável quando o bucket estiver indisponível. Como
o snapshot é fixado por hashes, alterações remotas não são consumidas. Aceitar uma nova versão
exige revisão e atualização deliberada do manifesto; não há atualização automática.

O BERTimbau fake-news detector não participa de busca, embedding, recuperação ou ranking de
evidências. Um futuro semantic reranker terá módulo, contrato, modelo, métricas, versionamento e
testes próprios. Nenhum score ou representação interna do detector poderá ser reutilizado como
relevância sem uma nova especificação aprovada.

## 10. Falhas, segurança e privacidade

- As proteções atuais contra SSRF, DNS rebinding, redirecionamentos, portas indevidas e IPs
  não públicos serão mantidas e testadas na aplicação Django.
- `robots.txt` continuará falhando fechado quando sua política não puder ser determinada.
- Falha técnica continuará distinta de `NEI`, conflito e refutação.
- Saídas de LLM e BERTimbau serão validadas antes da persistência.
- O relatório factual só usará evidências e URLs persistidas.
- Logs não conterão entrada completa, HTML, vetores, cookies, autorização, tokens ou chaves.
- `SECRET_KEY`, `HF_TOKEN` e chaves de provedores virão do ambiente; produção não aceitará
  defaults inseguros.
- CSRF, cookies seguros, hosts permitidos, CORS e binding de rede serão configurados por
  ambiente. O padrão continuará restrito a localhost.
- Uploads ou caminhos fornecidos pelo usuário não decidirão caminhos no filesystem.
- Limites de download, texto, tempo, chamadas, tokens, armazenamento, fila e concorrência
  continuarão centralizados nas settings.

## 11. Correlação e observabilidade

Cada requisição terá `request_id`; cada solicitação persistente, `analysis_id`; cada execução,
`run_id`; e cada tentativa assíncrona, `job_id`. IDs recebidos do cliente só serão aceitos em
formato validado; na ausência deles, o servidor criará UUIDs. O `request_id` será devolvido no
header de resposta e todos os IDs aplicáveis acompanharão contexto de logs, jobs e chamadas a
adaptadores.

Logs serão JSON estruturado com timestamp, nível, evento, componente, duração, estado, código de
erro e correlation IDs. Não registrarão texto integral, HTML, prompts preenchidos, evidências,
cookies, tokens ou chaves. Stack traces ficarão restritos ao log local de erro e nunca serão
devolvidos pela API.

Métricas operacionais mínimas:

- análises e runs criados, concluídos, limitados, falhos e interrompidos;
- jobs em fila, em execução, saturação, retries e tempo de espera;
- duração por etapa e duração total;
- coleta permitida, bloqueada, falha e bytes baixados;
- chamadas, tokens, erros e latência por provedor;
- evidências encontradas, deduplicadas e aceitas por run;
- estados, latência, truncamento, cache hit/miss e erros do BERTimbau;
- contenção/locks do SQLite e falhas de persistência;
- recuperação de crash e jobs órfãos reconciliados.

Métricas não terão texto do usuário, URL completa ou labels de cardinalidade ilimitada. A versão
local exporá snapshot operacional no Admin e logs; exportadores externos ficam para produção.

## 12. Testes e validação

A suíte usará `pytest`, `pytest-django` e os clientes de teste do Django e DRF. Ela cobrirá:

- compatibilidade dos endpoints e schemas atuais;
- formulários, templates, acessibilidade textual e polling;
- transições de estado, idempotência e saturação da fila;
- transições proibidas das quatro máquinas de estado;
- reexecução com novo `AnalysisRun` sem alteração dos resultados anteriores;
- manifesto completo de versões, prompts e commit por run;
- propagação de `request_id`, `analysis_id`, `run_id` e `job_id`;
- retry/backoff por categoria, orçamento e idempotência;
- migração em `--dry-run`, importação, repetição, rollback e reconciliação;
- preservação de IDs, datas, relações, payloads e relatórios legados;
- SSRF, DNS rebinding, redirecionamentos e `robots.txt`;
- citações literais, URLs conhecidas e grupos de independência;
- falha, timeout, truncamento, score inválido e rótulo inválido do BERTimbau;
- cache adulterado, arquivo extra, link simbólico e escritores concorrentes;
- prova de que qualquer saída ou falha do BERTimbau não muda o veredito factual;
- execução ponta a ponta em SQLite sem provedores externos;
- crash recovery em subprocesso real antes e depois de `FACTUAL_COMPLETED`;
- contenção SQLite sob a concorrência local configurada;
- constraints rejeitando estados, ordinais, scores e relações inválidas diretamente no banco;
- planos de consulta usando os índices definidos para fila, lease, histórico e relatório;
- lifecycle completo do executor, incluindo drenagem, sinais e ausência de threads vazadas;
- corpus de avaliação existente sem regressões.

Testes de rede reais ficarão fora da suíte padrão. Um smoke test opt-in poderá baixar o bucket
público anonimamente, validar o snapshot, carregar o modelo e executar exemplos conhecidos.

## 13. Fases de implementação e corte

1. Adicionar o projeto Django e configuração de testes sem remover o sistema atual.
2. Criar modelos, constraints, índices, state machines, migrations e o importador do banco
   legado.
3. Adaptar persistência, versionamento, correlação e serviços do pipeline ao Django ORM.
4. Implementar a API DRF compatível e seus testes de contrato.
5. Implementar templates, polling e histórico.
6. Adaptar jobs, lifecycle do executor, retries, crash recovery, observabilidade e BERTimbau ao
   fluxo factual-primeiro.
7. Executar dry-run e migração real dos dados, com reconciliação.
8. Fazer smoke test ponta a ponta e comparar comportamento com a aplicação anterior.
9. Remover FastAPI, Streamlit e SQLAlchemy, além dos entrypoints e testes obsoletos.
10. Atualizar instalação, execução, segurança, limitações e operação.

Cada fase termina com testes verdes. Enquanto houver dependência funcional do sistema antigo,
ele permanece executável; o corte acontece somente quando a alternativa Django correspondente
estiver comprovada.

## 14. Fronteira de produção

Esta arquitetura é o alvo da versão local e da migração tecnológica. Ela não autoriza exposição
direta à internet nem é apresentada como arquitetura final de produção pública.

Antes de produção pública será necessária outra especificação, no mínimo com PostgreSQL,
fila/worker persistente como Celery, armazenamento de objetos, autenticação e autorização,
gestão de segredos, TLS e proxy reverso, rate limiting distribuído, backups e restauração,
retenção legal, monitoramento/alertas externos, SLOs, capacidade, alta disponibilidade,
isolamento de rede e processo, sandboxing de coleta e revisão de privacidade e termos dos
provedores.

O manifesto de versões, contratos de domínio, correlation IDs e interfaces de job definidos
aqui são pontos de migração para essa etapa; SQLite e `ThreadPoolExecutor` não são.

## 15. Fora do escopo

- Celery, Redis e workers distribuídos;
- publicação direta na internet;
- autenticação multiusuário e autorização por organização;
- migração para PostgreSQL;
- retreinamento ou recalibração do BERTimbau;
- aceitação automática de novas versões do bucket;
- substituição dos provedores externos ainda não operacionalizados;
- semantic retrieval/reranking e qualquer reutilização do detector BERTimbau para esse fim.

## 16. Critérios de aceitação

A migração estará concluída quando:

1. interface e API funcionarem exclusivamente pelo Django;
2. não houver imports ou dependências de FastAPI, Streamlit ou SQLAlchemy;
3. os endpoints preservados passarem nos testes de contrato;
4. dados legados forem importados e reconciliados sem perda silenciosa;
5. o banco antigo permanecer intacto e recuperável;
6. relatório factual persistido sobreviver a qualquer falha do BERTimbau;
7. as proteções de rede, evidência, citação, recursos e privacidade continuarem verdes;
8. testes, lint, corpus de avaliação e smoke test local passarem;
9. documentação permitir instalação e execução a partir de um ambiente limpo;
10. o sistema completo executar localmente com Django, SQLite e fila local, sem Redis;
11. reexecuções criarem runs imutáveis sem sobrescrever resultados anteriores;
12. state machines rejeitarem toda transição não permitida;
13. cada run persistir manifesto completo de versões e correlation IDs;
14. retries, observabilidade e crash recovery real passarem nos testes definidos;
15. documentação declarar inequivocamente que SQLite e fila local não são a fronteira de
    produção pública;
16. constraints e índices definidos nas migrations passarem nos testes de integridade e plano
    de consulta;
17. lifecycle do `ThreadPoolExecutor` ser explícito, idempotente e não deixar threads ou jobs
    órfãos após shutdown e crash recovery.
