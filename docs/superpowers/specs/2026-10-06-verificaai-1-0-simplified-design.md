# VerificaAI 1.0 — desenho simplificado

**Status:** aprovado em conversa; aguardando revisão do documento  
**Substitui:** `2026-10-06-verificaai-django-migration-design.md` para a entrega 1.0

## 1. Objetivo

Entregar uma aplicação local, executável e demonstrável de verificação factual em português. A
versão 1.0 prioriza a qualidade do pipeline, a segurança na coleta de URLs, a auditabilidade das
reexecuções e testes confiáveis. Ela não pretende ser uma plataforma distribuída nem uma
arquitetura de produção pública.

O sistema será compreendido em quatro blocos:

```text
WEB                 FACT CHECK                 NLP              DADOS
Django              Claims                     BERTimbau        SQLite
HTML + API           Busca segura                                Filesystem
Executor local       BM25
Histórico            Evidências
                     Julgamento
                     Relatório
```

## 2. Escopo da versão 1.0

Incluído:

- Django, Django REST Framework e templates Django nativos;
- criação de análises de texto ou URL, consulta de estado, histórico e reexecução;
- `Analysis` como identidade estável e `AnalysisRun` como execução auditável;
- pipeline factual existente: claims, busca, coleta, BM25, evidências, julgamento e relatório;
- BERTimbau como análise linguística auxiliar e isolada do veredito factual;
- SQLite para dados estruturados e filesystem para HTML e artefatos volumosos;
- executor local limitado para não bloquear requisições web;
- segurança de URL, validação de saída da LLM, citações literais e independência de fontes;
- importação única e idempotente do banco legado;
- testes unitários, de integração e de fluxo Django.

Fora do escopo:

- modelo `Job`, fila persistida, leases, heartbeat e recuperação distribuída;
- retries configuráveis por categoria ou orquestração sofisticada;
- manifesto completo de prompts, dependências, migrations e árvore Git;
- métricas de plataforma, tracing distribuído e dashboards operacionais;
- Celery, Redis, filas externas e múltiplos processos de workers;
- PostgreSQL e implantação pública de produção;
- reranking semântico; o BERTimbau não será reutilizado para retrieval.

## 3. Arquitetura

### 3.1 Web

Django será o único framework web. Templates nativos oferecem formulário, acompanhamento de
estado, relatório e histórico. A API REST preserva os fluxos equivalentes já disponíveis, com
contratos adaptados apenas para expor `run_id` e o histórico de reexecuções.

O módulo web valida entrada e delega para serviços. Views, serializers e templates não executam
o pipeline factual diretamente.

### 3.2 Fact check

O pipeline factual permanece dividido em componentes testáveis:

1. normalização da entrada e coleta segura quando a entrada é uma URL;
2. extração e validação estrutural de claims;
3. geração de consultas e busca por provedor configurado;
4. coleta segura e extração de texto das fontes;
5. chunking e ranking BM25;
6. agrupamento de fontes dependentes ou copiadas;
7. julgamento por claim com validação de citações;
8. agregação do veredito e construção do relatório.

Falha técnica e ausência de evidência são resultados distintos. Uma falha de provedor, coleta
ou parsing nunca será convertida silenciosamente em “não há evidências”. Saídas de LLM que não
passarem no schema serão rejeitadas ou registradas como limitação técnica.

### 3.3 NLP

O BERTimbau fake-news detector é um componente auxiliar. Ele recebe o texto da entrada e produz
estado, rótulo, score, versão do modelo e eventual erro técnico. Seu resultado aparece em seção
separada do relatório e nunca altera claims, ranking, evidências, julgamentos ou veredito factual.

A inicialização, download e inferência terão limites explícitos. Indisponibilidade, timeout ou
saída inválida do modelo produzem erro auxiliar sem impedir a persistência do resultado factual.

### 3.4 Dados

SQLite é o banco local da versão 1.0. As transações serão curtas e a aplicação será documentada
para um único processo web e baixa concorrência. WAL, foreign keys e busy timeout serão ativados
em conexões de arquivo.

O filesystem armazenará HTML, documentos e outros artefatos volumosos. O banco guardará caminho
relativo seguro, SHA-256, tamanho e tipo quando o artefato participar de um run. Caminhos
absolutos ou com travessia de diretório serão rejeitados.

PostgreSQL será considerado apenas numa etapa futura de produção pública.

## 4. Modelo de dados

### 4.1 `Analysis`

Representa a solicitação estável:

- UUID público;
- tipo `text` ou `url`;
- conteúdo original ou referência segura ao artefato;
- hash da entrada normalizada;
- chave de idempotência opcional;
- timestamps.

A mesma `Analysis` pode possuir vários runs. Reexecutar nunca sobrescreve resultados anteriores.

### 4.2 `AnalysisRun`

Representa uma execução:

- UUID público e relação protegida com `Analysis`;
- ordinal crescente por análise;
- estado `QUEUED`, `RUNNING`, `COMPLETED`, `COMPLETED_WITH_LIMITATIONS` ou `FAILED`;
- `request_id`, `analysis_id` e `run_id` para correlação;
- versão lógica do pipeline;
- versões dos provedores e modelos efetivamente usados em JSON compacto;
- consultas e metadados intermediários úteis em JSON compacto;
- relatório final estruturado;
- código e mensagem segura de erro;
- timestamps de criação, início e fim.

Não haverá manifesto completo de reprodução. Segredos, prompts preenchidos, HTML e texto integral
de evidências não serão gravados em logs ou campos de versão.

### 4.3 `Claim`

Pertence a um run e contém chave estável dentro do run, posição, texto, prioridade, veredito,
confiança e explicação. A combinação `(run_id, claim_key)` será única.

### 4.4 `Evidence`

Pertence a uma claim e ao mesmo run. Armazena URL canônica, título, domínio, trecho, citação,
rank BM25, grupo de independência, relação com a claim e metadados de disponibilidade. A citação
aceita deve existir literalmente no trecho normalizado armazenado.

### 4.5 `BERTAnalysis`

Relação um-para-um com o run. Usa estados `PENDING`, `AVAILABLE`, `UNAVAILABLE` e `ERROR`.
`AVAILABLE` exige rótulo `FALSA` ou `VERDADEIRA`, score finito entre 0 e 1, identificador e
versão do modelo. Demais estados não carregam rótulo ou score.

### 4.6 Constraints e índices

O banco imporá as invariantes portáveis e essenciais:

- entrada não vazia e `input_type` válido;
- idempotency key única quando presente;
- `(analysis_id, ordinal)` único e ordinal positivo;
- no máximo um run `QUEUED` ou `RUNNING` por análise;
- valores de estado válidos e timestamps em ordem;
- unicidade de claim e evidência dentro do run;
- score válido e dependências de estado do BERT;
- foreign keys auditáveis com `PROTECT`.

Índices explícitos serão limitados aos caminhos reais de consulta:

- análise por criação e hash de entrada;
- runs por análise/ordinal e por estado/atualização;
- claims por run/posição;
- evidências por claim/rank e por grupo de independência.

Invariantes entre múltiplas tabelas que SQLite não expressa de forma portátil serão verificadas
por serviços transacionais e testes.

## 5. Execução local

Um único `ThreadPoolExecutor` de tamanho pequeno executará runs sem bloquear a requisição HTTP.
Ele será criado explicitamente pelo ciclo da aplicação, nunca durante imports, migrations ou
testes, e encerrado com `shutdown(wait=False, cancel_futures=True)`.

Fluxo:

```text
POST /analyses
  -> cria Analysis + AnalysisRun(QUEUED)
  -> agenda a execução
  -> retorna request_id, analysis_id e run_id
  -> worker muda o run para RUNNING
  -> executa e persiste o pipeline factual
  -> executa o BERT auxiliar dentro de limite próprio
  -> termina o run
```

Não haverá retry automático do run. Clientes HTTP podem realizar poucas tentativas locais para
erros transitórios, com backoff curto e limites fixos próximos ao cliente.

Na inicialização, runs deixados em `QUEUED` ou `RUNNING` por encerramento inesperado serão
marcados `FAILED` com código `PROCESS_INTERRUPTED`. O usuário poderá criar uma reexecução manual,
que sempre gera um novo ordinal e preserva o run interrompido.

## 6. Segurança e confiabilidade factual

### 6.1 URLs e rede

- aceitar somente HTTP e HTTPS;
- rejeitar credenciais embutidas, portas não permitidas e destinos locais/reservados;
- resolver e validar todos os endereços antes da conexão;
- conectar ao endereço validado e manter a identidade do host/TLS;
- repetir resolução e validação a cada redirecionamento;
- limitar redirects, bytes, tempo e tipo de conteúdo;
- tratar falha de obtenção ou interpretação de `robots.txt` de forma segura, sem presumir
  permissão;
- impedir acesso da aplicação a metadados de nuvem e redes privadas.

### 6.2 Evidências

- resultados canônicos repetidos serão deduplicados;
- republicações e conteúdo substancialmente copiado compartilharão grupo de independência;
- quantidade de URLs não será usada como quantidade de fontes independentes;
- toda citação será normalizada e conferida literalmente contra o trecho persistido;
- citação inválida torna o julgamento inválido, não uma evidência parcial;
- indisponibilidade técnica será apresentada como limitação explícita.

### 6.3 LLM

- contratos estruturados estritos para claims, consultas e julgamentos;
- validação de enums, tamanhos, IDs e referências;
- nenhuma fonte ou citação fornecida apenas pela LLM será aceita sem correspondência nos dados
  coletados;
- erros e saídas inválidas não serão convertidos em conteúdo inventado.

## 7. Interface

Páginas mínimas:

- formulário para texto ou URL;
- tela de acompanhamento do run;
- relatório com veredito, claims, evidências, limitações e BERT auxiliar;
- histórico da análise com opção de reexecutar.

Endpoints mínimos:

- `POST /api/analyses/`;
- `GET /api/analyses/{analysis_id}/`;
- `GET /api/analyses/{analysis_id}/runs/`;
- `GET /api/runs/{run_id}/`;
- `POST /api/analyses/{analysis_id}/rerun/`.

## 8. Migração

A migração será incremental:

1. consolidar modelos Django e estados simplificados;
2. adaptar o pipeline existente aos repositórios Django;
3. adicionar o executor local e recuperação simples;
4. expor API e templates Django;
5. importar o SQLite legado de forma transacional, idempotente e com `--dry-run`;
6. validar equivalência e somente então remover FastAPI, Streamlit e SQLAlchemy.

Alterações parciais produzidas para a arquitetura anterior serão reaproveitadas somente quando
compatíveis com este documento. Modelos `Job`, lease, heartbeat e respectivos testes não serão
incorporados.

## 9. Testes de aceitação

A versão 1.0 estará pronta quando os testes confirmarem:

- criação, acompanhamento e reexecução com novo `AnalysisRun`;
- imutabilidade de runs concluídos;
- estados e constraints essenciais diretamente no banco;
- limitação do executor e recuperação de runs interrompidos;
- SSRF, DNS rebinding, redirecionamentos e política de `robots.txt`;
- falhas de busca, coleta e LLM distintas de ausência de evidência;
- deduplicação e agrupamento de fontes dependentes;
- citações literalmente presentes nas evidências;
- falha, timeout ou saída inválida do BERT sem alterar o veredito factual;
- armazenamento de artefatos fora do SQLite;
- importação legada seca, idempotente e transacional;
- fluxo Django completo com provedores falsos e rede bloqueada.

## 10. Limite de produção

Esta arquitetura é deliberadamente local. Um lançamento público exigirá uma nova etapa para
PostgreSQL, fila externa, workers independentes, armazenamento de objetos, observabilidade,
gestão de segredos, rate limiting, autenticação, isolamento de rede e operação multi-instância.
Esses itens não são pré-requisitos para concluir ou apresentar o VerificaAI 1.0.
