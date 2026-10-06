# VerificaAI — migração integral para Django

**Data:** 2026-10-06  
**Status:** desenho aprovado em conversa; aguardando revisão da especificação escrita

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
Serviço de análises + fila local limitada
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
- **`reports`**: construção e validação do relatório auditável.
- **`jobs`**: interface de execução assíncrona e implementação local limitada.

O Django Admin permitirá inspeção de análises, estados, limitações e relatórios. Segredos,
HTML bruto, cookies, cabeçalhos de autorização e conteúdo sensível não serão exibidos.

## 4. Persistência com Django ORM

O Django ORM substituirá todas as sessões, modelos e repositórios SQLAlchemy. Os modelos de
destino preservarão os conceitos atuais:

| Modelo Django | Conteúdo principal |
|---|---|
| `Analysis` | entrada, tipo, hash, estado, erro, limitações e timestamps |
| `Claim` | afirmação validada, prioridade, tipo e entidades |
| `Query` | consultas geradas por afirmação |
| `SearchResult` | metadados de resultados descobertos |
| `Evidence` | trecho, fonte, grupo de independência e datas |
| `Decision` | decisão por evidência e citação validada |
| `Report` | relatório final estruturado e versão do contrato |
| `Artifact` | caminho relativo, hash, tamanho, compressão e retenção |

Chaves primárias, identificadores de domínio e timestamps legados serão preservados quando
existirem. Restrições de unicidade e relacionamentos impedirão duplicação silenciosa. Payloads
JSON continuarão disponíveis onde a evolução do contrato exigir flexibilidade, mas campos
consultados ou relacionais terão colunas próprias.

SQLite permanece como padrão local. A modelagem e as transações não dependerão de extensões
específicas, permitindo migração futura para PostgreSQL sem fazer parte desta entrega.

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
- nenhum bloqueio da thread de requisição durante uma análise;
- transações curtas e conexões ORM abertas somente quando necessárias;
- interface substituível futuramente por Celery sem alterar o pipeline.

Celery e Redis ficam fora do escopo desta entrega.

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

## 11. Testes e validação

A suíte usará `pytest`, `pytest-django` e os clientes de teste do Django e DRF. Ela cobrirá:

- compatibilidade dos endpoints e schemas atuais;
- formulários, templates, acessibilidade textual e polling;
- transições de estado, idempotência e saturação da fila;
- migração em `--dry-run`, importação, repetição, rollback e reconciliação;
- preservação de IDs, datas, relações, payloads e relatórios legados;
- SSRF, DNS rebinding, redirecionamentos e `robots.txt`;
- citações literais, URLs conhecidas e grupos de independência;
- falha, timeout, truncamento, score inválido e rótulo inválido do BERTimbau;
- cache adulterado, arquivo extra, link simbólico e escritores concorrentes;
- prova de que qualquer saída ou falha do BERTimbau não muda o veredito factual;
- execução ponta a ponta em SQLite sem provedores externos;
- corpus de avaliação existente sem regressões.

Testes de rede reais ficarão fora da suíte padrão. Um smoke test opt-in poderá baixar o bucket
público anonimamente, validar o snapshot, carregar o modelo e executar exemplos conhecidos.

## 12. Fases de implementação e corte

1. Adicionar o projeto Django e configuração de testes sem remover o sistema atual.
2. Criar modelos, migrations e o importador do banco legado.
3. Adaptar a persistência e os serviços do pipeline ao Django ORM.
4. Implementar a API DRF compatível e seus testes de contrato.
5. Implementar templates, polling e histórico.
6. Adaptar jobs e BERTimbau ao fluxo factual-primeiro.
7. Executar dry-run e migração real dos dados, com reconciliação.
8. Fazer smoke test ponta a ponta e comparar comportamento com a aplicação anterior.
9. Remover FastAPI, Streamlit e SQLAlchemy, além dos entrypoints e testes obsoletos.
10. Atualizar instalação, execução, segurança, limitações e operação.

Cada fase termina com testes verdes. Enquanto houver dependência funcional do sistema antigo,
ele permanece executável; o corte acontece somente quando a alternativa Django correspondente
estiver comprovada.

## 13. Fora do escopo

- Celery, Redis e workers distribuídos;
- publicação direta na internet;
- autenticação multiusuário e autorização por organização;
- migração para PostgreSQL;
- retreinamento ou recalibração do BERTimbau;
- aceitação automática de novas versões do bucket;
- substituição dos provedores externos ainda não operacionalizados.

## 14. Critérios de aceitação

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
10. o sistema completo executar localmente com Django, SQLite e fila local, sem Redis.
