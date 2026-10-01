# VerificaAI — Especificação de desenho da primeira versão

## 1. Objetivo e limites

O VerificaAI será uma aplicação de apoio à verificação de informações em português brasileiro. A primeira versão recebe texto ou URL, preserva o conteúdo original, extrai até três afirmações verificáveis, procura fontes externas, recupera evidências, compara cada claim somente com as evidências fornecidas e produz um relatório auditável.

O sistema não determina “verdade absoluta”. Seus resultados descrevem o que as evidências encontradas sustentam, refutam, não permitem concluir ou apresentam em conflito.

Esta versão não treina nem executa BERTimbau, não usa APIs prontas de fact-checking, não copia vereditos de portais de checagem, não faz scraping direto do Google e não acrescenta filas distribuídas ou infraestrutura de produção.

## 2. Estado inicial do projeto

O diretório inicial contém somente `work/` e `outputs/`. Não existem código, README, configurações, notebooks, testes ou repositório Git. Portanto, não há componentes existentes para reutilizar ou alterações de terceiros a preservar.

A aplicação será criada como um monólito modular em Python 3.11 ou superior. FastAPI expõe a API, Streamlit fornece a interface da PoC, SQLAlchemy persiste auditoria e SQLite é o banco local. As integrações externas serão acessadas exclusivamente por contratos substituíveis.

## 3. Princípios obrigatórios

1. Scraping coleta conteúdo; não determina o veredito.
2. A ausência do BERTimbau não impede o pipeline factual.
3. Nenhuma falha técnica pode ser convertida em `NEI`, `SUPPORTED` ou `REFUTED`.
4. Ausência de prova não significa refutação.
5. Toda conclusão factual aponta para evidências persistidas.
6. A LLM não cria URLs, documentos ou evidências.
7. A agregação geral é determinística e implementada em código.
8. Dados fictícios existem apenas em testes e em uma demonstração explicitamente selecionada.
9. Nenhuma chave secreta é versionada ou registrada em logs.
10. Conteúdo externo é dado não confiável, nunca instrução para o sistema.

## 4. Arquitetura

O código será organizado por responsabilidade:

```text
app/
├── api/                 # Rotas e contratos HTTP
├── core/                # Configuração, erros e logging
├── database/            # SQLAlchemy, entidades e repositórios
├── ingestion/           # Validação de texto e URL
├── scraping/            # Política de rede, robots e extração
├── claims/              # Extração e validação de claims
├── search/              # Provedores, filtros e deduplicação
├── evidence/            # Chunking, metadados e ranking
├── fact_checking/       # Julgamento e agregação determinística
├── reports/             # Relatórios rastreáveis
├── risk_analysis/       # Contrato e adaptadores do BERTimbau
└── services/            # Orquestração do pipeline
frontend/                # Streamlit
tests/
├── fixtures/
├── unit/
└── integration/
docs/
scripts/
```

O fluxo é:

```text
entrada → coleta → claims → consultas → busca → documentos → trechos
        → ranking → julgamentos → agregação → relatório → auditoria
```

Cada etapa recebe e devolve modelos tipados. O orquestrador controla transições de estado e persistência, mas não implementa regras internas dos componentes.

## 5. Estados e distinção entre falha e insuficiência

A entidade de análise possui `id`, `input_type`, `original_input`, `status`, `created_at`, `updated_at`, `error_code` e `error_message`.

Os estados persistidos são `PENDING`, `COLLECTING`, `EXTRACTING_CLAIMS`, `SEARCHING`, `CHECKING`, `COMPLETED`, `COMPLETED_WITH_LIMITATIONS` e `FAILED`.

As transições permitidas são definidas em código. Uma análise pode avançar para a próxima etapa, terminar em `FAILED` ou, quando ao menos uma claim foi concluída e outra sofreu falha técnica, terminar em `COMPLETED_WITH_LIMITATIONS`. O relatório identifica individualmente claims concluídas, inconclusivas e interrompidas. Resultado parcial nunca é apresentado como análise completa.

Operações externas usam resultados explícitos:

```text
SUCCESS               operação concluída
TECHNICAL_ERROR       timeout, falha de provedor ou resposta inválida
BLOCKED               robots.txt, paywall, login, CAPTCHA ou política
INSUFFICIENT_EVIDENCE coleta válida que não responde à claim
```

Somente resultados `SUCCESS` participam de julgamentos. `NEI` é produzido apenas quando operações necessárias foram concluídas, mas as evidências relevantes não resolvem a claim. Falhas técnicas tornam a análise incompleta ou `FAILED`, conforme a etapa e a possibilidade de continuar.

### 5.1 Limites padrão da PoC

Os limites são centralizados em configuração e começam com estes valores testáveis:

| Recurso | Limite inicial |
|---|---:|
| Texto submetido | 100.000 caracteres |
| Download por resposta | 5 MiB |
| Redirecionamentos | 5 |
| Timeout total por requisição externa | 20 segundos |
| Claims por análise | 3 |
| Consultas por claim | 4 |
| Resultados por consulta | 10 |
| Documentos coletados por claim | 5 |
| Evidências finais por claim | 5 |
| Análises simultâneas | 2 |
| Jobs aguardando execução | 10 |
| Duração total da análise | 5 minutos |
| Chamadas de LLM, incluindo correções | 20 por análise |
| Entrada e saída da LLM | 100.000 tokens por análise |
| Artefatos brutos | 25 MiB por análise |

Limites podem ser reduzidos por ambiente, mas aumentos exigem configuração explícita. Atingir um limite gera código de erro ou limitação específico e nunca um veredito factual.

## 6. Entrada e ingestão

A API aceita `input_type` igual a `text` ou `url`. Texto vazio ou acima do limite configurado é rejeitado. URLs aceitam somente HTTP/HTTPS, devem ser sintaticamente válidas e não podem conter credenciais embutidas.

Para texto, `original_input` e o texto original são preservados. Para URL, são preservados URL original, URL canônica, HTML quando permitido, texto extraído, metadados e horário da coleta.

Submissões aceitam uma chave de idempotência opcional. O serviço também calcula um hash da entrada normalizada, versão do pipeline e configuração factual relevante. Repetições simultâneas com a mesma chave retornam a análise existente. O usuário pode solicitar nova tentativa explícita de uma análise falha sem sobrescrever o registro anterior.

## 7. Coleta segura e SSRF

Antes de qualquer conexão, o coletor:

1. normaliza a URL;
2. rejeita esquemas diferentes de HTTP/HTTPS;
3. permite somente portas configuradas, inicialmente 80 e 443;
4. resolve todos os endereços A e AAAA;
5. rejeita o destino caso qualquer endereço seja loopback, privado, link-local, multicast, reservado, não especificado, de documentação ou metadado de nuvem;
6. conecta ao endereço público validado, preservando `Host` e SNI, para evitar nova resolução entre validação e conexão;
7. processa redirecionamentos manualmente e repete todas as verificações em cada salto;
8. nunca encaminha credenciais ou cabeçalhos sensíveis entre origens.

O cliente ignora proxies herdados do ambiente, limita redirecionamentos, tempo, tamanho de resposta e concorrência por domínio. Usa User-Agent identificável, cache básico e rate limiting. O download é interrompido assim que excede o limite.

Não são contornados CAPTCHA, login, paywall ou medidas de segurança.

### 7.1 Política de robots.txt

`RobotsPolicy` mantém cache por domínio e retorna `ALLOWED`, `DISALLOWED` ou `UNKNOWN`.

- `404` indica ausência de `robots.txt` e permite coleta sujeita aos demais controles.
- `401` ou `403` é tratado como proibição.
- Regra explícita aplicável ao User-Agent é respeitada.
- Timeout, falha de DNS ou erro de rede resulta em `UNKNOWN`.
- `UNKNOWN` bloqueia a coleta naquele momento e registra limitação recuperável.

## 8. Extração de notícias

A sequência é HTTPX, Trafilatura e complementação por BeautifulSoup/JSON-LD. Playwright permanece como fallback opcional e desabilitado por padrão; não é requisito para a primeira entrega funcional.

São extraídos `title`, `subtitle`, `author`, `published_at`, `domain`, `canonical_url`, `language`, `original_html`, `clean_text`, `extraction_method` e `extracted_at`.

Páginas vazias, telas de bloqueio, login e assinatura não são tratadas como notícia. Quando o conteúdo não puder ser obtido, o usuário é orientado a colar o texto.

## 9. Armazenamento do conteúdo bruto

SQLite armazena metadados, caminho, SHA-256, tamanho, tipo e política de retenção. O HTML permitido é comprimido e salvo em diretório de artefatos por análise, fora do banco.

Há limites por resposta, por análise e para o diretório de artefatos. Arquivos temporários são gravados atomicamente. Uma rotina remove temporários órfãos. Conteúdo proibido, excessivo ou desnecessário não é persistido, e a razão fica registrada.

A futura migração para PostgreSQL não altera os contratos de repositório; artefatos poderão migrar para armazenamento de objetos.

### 9.1 Privacidade e retenção

Logs não contêm texto integral, HTML, chaves, tokens, cookies ou cabeçalhos de autenticação. Identificadores e códigos de erro substituem conteúdo sensível nos registros operacionais.

A retenção local padrão é de 30 dias para análises e 7 dias para HTML bruto, configurável para valores menores. Uma rotina de limpeza remove artefatos expirados e registra somente identificador, hash e resultado da remoção. A arquitetura reserva um serviço de exclusão para futura rota autenticada, mesmo que essa rota não integre a API mínima da PoC.

Antes de enviar texto ou evidências a uma LLM externa, a interface informa que os dados serão processados pelo provedor configurado e exige consentimento explícito. Somente claims e trechos necessários são enviados; HTML completo, cookies e metadados não essenciais nunca são encaminhados. O modo fake/local não exige esse consentimento externo.

## 10. BERTimbau

`RiskAnalyzer` define `analyze(text: str) -> dict`. `DisabledRiskAnalyzer` sempre retorna:

```json
{
  "status": "modelo_indisponivel",
  "label": null,
  "score": null,
  "model_name": null,
  "model_version": null,
  "message": "O modelo de risco textual ainda não foi integrado."
}
```

`BertimbauRiskAnalyzer` é um adaptador sem inferência e documenta o ponto futuro de integração. Nenhum score aleatório ou inferência simulada é permitido. A interface mostra “Análise linguística: aguardando integração do BERTimbau.”

## 11. LLM e proteção contra conteúdo malicioso

Os contratos são `ClaimExtractor`, `QueryGenerator`, `EvidenceJudge` e `ExplanationGenerator`. A implementação real é configurada por variáveis de ambiente; testes usam implementações fake determinísticas.

Toda chamada possui timeout, tentativas limitadas, saída JSON estruturada e validação Pydantic. IDs, enumerações, claims, evidências e URLs devem pertencer ao conjunto fornecido. Respostas fora do esquema são rejeitadas; uma correção de formato pode ser solicitada antes da falha definitiva.

Prompts do sistema são imutáveis e separados do conteúdo coletado. Textos de páginas são delimitados e rotulados como dados não confiáveis. Instruções encontradas em páginas não podem modificar o comportamento do componente. Mesmo uma resposta sintaticamente válida passa por validações determinísticas posteriores.

Nome do provedor, modelo, versão do prompt, tempo e estado da chamada são persistidos. Chaves e cabeçalhos de autenticação nunca são registrados.

O modo de provedor é explícito: `disabled`, `fake` ou `real`. `fake` só pode ser selecionado em testes ou na demonstração identificada. Antes da Fase 3, um registro de decisão deve escolher o primeiro provedor real de LLM com base em credenciais disponíveis, JSON estruturado, política de dados, custo e limites. Antes da Fase 4, o mesmo ocorre para busca. Nenhum adaptador que finja compatibilidade genérica será criado sem contrato oficial do fornecedor escolhido.

## 12. Claims e consultas

São extraídas no máximo três claims factuais, atômicas e verificáveis. Nomes, números, datas, verbos e negações são preservados. Cada claim contém trecho original, tipo, prioridade, entidades e indicador de verificabilidade.

Quando identificável no texto, a claim também contém `event_date`, `valid_from`, `valid_until` e `temporal_scope`. Datas desconhecidas permanecem nulas; não são inferidas. Incompatibilidade temporal impede que a evidência decida a claim atual, e ausência de escopo temporal relevante reduz a confiança ou aparece como limitação.

O trecho original deve existir no texto analisado. Claim sem correspondência é descartada com motivo auditável. Opiniões, preferências, perguntas, piadas, previsões não verificáveis e frases vagas não são claims factuais.

Para cada claim são geradas de duas a quatro consultas que preservam entidade, ação, objeto, data, número e local. Quando pertinente, uma consulta favorece fontes oficiais.

## 13. Busca, filtragem e dependências externas

`SearchProvider.search(query: str, limit: int = 10) -> list[SearchResult]` desacopla o domínio do mecanismo escolhido. O modo real exige configuração explícita; sem ela, retorna erro orientado. Nenhum dado fake substitui silenciosamente resultados reais.

Provedores têm health check, timeout, tentativas limitadas e classificação própria de erros. Mudanças de API, indisponibilidade, rate limit e custo são limitações registradas, não sinais factuais.

Resultados de domínios de fact-checking configurados são excluídos. URLs iguais e canônicas são deduplicadas antes da coleta.

## 14. Documentos, independência e deduplicação

Após a coleta, documentos são normalizados para cálculo de SHA-256 e similaridade aproximada. URL canônica, hash, SimHash ou técnica equivalente, atribuição declarada, domínio e sinais de republicação são combinados.

Documentos copiados recebem o mesmo `independence_group`. Várias páginas do mesmo grupo contam como uma origem na agregação. O agrupamento e os sinais utilizados são persistidos para auditoria, pois deduplicação aproximada pode produzir falsos positivos ou negativos.

Metadados de fonte são descritivos: `source_type`, `is_primary_source`, `has_author`, `has_publication_date`, `has_original_document`, `jurisdiction_match`, `temporal_match` e `independence_group`. Eles não formam uma probabilidade de verdade.

## 15. Trechos e ranking

Documentos são divididos em trechos de tamanho configurável, com pequena sobreposição, índice, documento, URL e metadados preservados.

O ranking inicial combina TF-IDF ou BM25, entidades, datas, números, título, atualidade e adequação a fonte oficial. No máximo cinco evidências são selecionadas por claim. Um reranking por LLM é opcional e só pode reordenar candidatos fornecidos.

## 16. Julgamento e validação de citações

`EvidenceJudge` recebe uma claim e evidências específicas. O prompt exige uso exclusivo dessas evidências, preservação de números/datas/nomes e `NEI` quando não houver suporte suficiente.

Cada decisão contém `claim_id`, `evidence_id`, `label`, `reason`, `quoted_excerpt` e `limitations`. O rótulo por par é `SUPPORTED`, `REFUTED` ou `NEI`.

Antes de aceitar uma decisão:

- `claim_id` e `evidence_id` devem existir;
- `quoted_excerpt` deve ser substring literal do texto original da evidência;
- a explicação não pode citar outro documento ou URL;
- decisões inválidas são rejeitadas e podem ser corrigidas uma vez;
- erro persistente é técnico e não participa da agregação.

Normalização Unicode ou de espaços pode localizar uma correspondência, mas o relatório sempre exibe os caracteres retirados do texto original. Trechos incluem contexto suficiente para reduzir citações enganosas.

## 17. Agregação determinística

O agregador considera relevância, primariedade, adequação temporal/jurisdicional e grupos independentes. Regras iniciais:

- nenhuma evidência relevante: `NEI`;
- evidência apenas relacionada ao tema: `NEI`;
- apoio direto de fonte primária relevante: pode produzir `SUPPORTED`;
- contradição direta de fonte primária relevante: pode produzir `REFUTED`;
- fontes relevantes de grupos independentes em desacordo: `CONFLICTING`;
- fonte desatualizada não decide claim atual;
- cópias contam como uma origem;
- erro técnico nunca produz veredito factual.

A confiança é categórica: `HIGH`, `MEDIUM`, `LOW` ou `INSUFFICIENT`. Não há porcentagem de verdade.

O resultado geral é `CONTAINS_REFUTED_CLAIM`, `MAIN_CLAIMS_SUPPORTED`, `MIXED`, `INSUFFICIENT_EVIDENCE` ou `CONFLICTING_EVIDENCE`.

## 18. API, processamento e Streamlit

A API mínima expõe:

```text
POST /api/v1/analyses
GET  /api/v1/analyses/{analysis_id}
GET  /api/v1/analyses/{analysis_id}/claims
GET  /api/v1/analyses/{analysis_id}/report
```

Ao criar uma análise, o registro é persistido imediatamente. Um `ThreadPoolExecutor` pequeno e limitado executa o serviço síncrono de pipeline fora da requisição. A interface consulta o status periodicamente e apresenta progresso.

Esta fila em memória não promete durabilidade. Ao iniciar, análises deixadas em estado intermediário são marcadas como `FAILED` com código de interrupção e podem ser reenviadas. Concorrência e tamanho da fila são limitados. Redis/Celery não fazem parte desta versão.

O serviço escuta somente em `127.0.0.1` por padrão. A PoC não deve ser exposta diretamente à internet. Uma implantação em rede exige, antes da exposição, autenticação, autorização, TLS no terminador, CORS restrito, rate limiting por identidade e revisão dos limites de uso. Essa infraestrutura não faz parte da primeira versão.

A API aplica os limites de submissão, fila, chamadas externas, tokens, armazenamento e duração total definidos na Seção 5.1. Quando a identidade do cliente não estiver disponível, o controle local usa a origem da conexão apenas como proteção básica, sem alegar resistência a ambientes com proxy. Jobs excedentes são recusados com erro de capacidade e podem ser reenviados.

Streamlit oferece seleção entre texto e URL, botão “Iniciar investigação”, progresso, status do BERTimbau, cards textuais, evidências clicáveis, limitações e mensagens de erro em português brasileiro. Cor nunca é o único indicador.

## 19. Relatório e auditoria

O relatório separa:

```text
Risco textual: aguardando BERTimbau.
Resultado factual: baseado nas claims e evidências encontradas.
```

Mostra entrada, título, data, claims, veredito, explicação, evidências, citações, URLs, datas, confiança, limitações e horário. Explicações não acrescentam fatos ausentes das evidências.

São persistidos entrada, conteúdo permitido, claims, consultas, resultados, documentos, trechos, decisões, agregação, relatório, erros, versões de prompt, provedor, versão do código e datas de cada etapa.

## 20. Estratégia de testes

Testes não acessam a internet. HTTP, DNS, robots, busca e LLM usam fakes ou respostas simuladas. Fixtures fictícias cobrem `SUPPORTED`, `REFUTED`, `NEI` e `CONFLICTING`.

Além dos testes funcionais solicitados, a suíte cobre:

- hostname que muda para IP privado entre resolução e redirecionamento;
- destinos com IPv6 privado, link-local e formatos alternativos de IP;
- redirecionamento que muda origem e tenta carregar credenciais;
- `robots.txt` permitido, proibido, ausente e indisponível;
- provedor ausente, timeout, rate limit e JSON inválido;
- prompt injection dentro de evidência;
- citação inexistente ou pertencente a outra evidência;
- falha técnica que não se torna `NEI` ou `REFUTED`;
- republicações agrupadas e fontes realmente independentes separadas;
- limite de download e de armazenamento;
- recuperação de análise interrompida;
- negação, números, datas e acentos preservados;
- relatório contendo somente evidências persistidas.

Além da suíte unitária, um corpus de avaliação fictício e versionado cobre negação, datas conflitantes, unidades diferentes, republicações, fontes desatualizadas, apoio parcial, citações corretas fora de contexto e falha técnica no meio da análise. O corpus é separado dos fixtures usados diretamente pelos testes unitários e gera um resumo de regressões por versão do pipeline, sem transformar acurácia em “probabilidade de verdade”.

Cada fase termina com testes, Ruff e atualização de `PROGRESS.md`.

## 21. Entregas incrementais

### Fase 1 — Fundação

Configuração com limites exatos, modelos, máquina de estados, idempotência, tipos de resultado, contratos, persistência inicial, retenção, `DisabledRiskAnalyzer`, adaptador vazio do BERTimbau e testes.

### Fase 2 — Entrada e coleta

Validação, SSRF com IP fixado, redirecionamentos manuais, robots, limites, scraping, metadados, artefatos comprimidos e testes.

### Fase 3 — LLM, claims e consultas

Registro da escolha do primeiro provedor de LLM, consentimento para processamento externo, adaptadores real/fake, orçamento de tokens, validação estruturada, proteção contra prompt injection, claims temporais, consultas e testes.

### Fase 4 — Busca e evidências

Registro da escolha do primeiro provedor de busca, contrato de busca, filtro de fact-checkers, orçamento de chamadas, coleta, chunking, ranking, deduplicação, grupos de independência e testes.

### Fase 5 — Julgamento e agregação

Comparação restrita às evidências, citações literais, distinção de falha técnica, regras determinísticas e testes.

### Fase 6 — Produto funcional

Orquestrador, executor local limitado, recuperação e reenvio, resultados parciais explícitos, API restrita a localhost, Streamlit, relatório, auditoria e testes de integração.

### Fase 7 — Finalização

README, `.env.example`, instruções, limitações, integração futura do BERTimbau, revisão de segurança e validação completa.

## 22. Riscos residuais aceitos

As proteções reduzem, mas não eliminam:

- cobertura incompleta ou viés dos mecanismos de busca;
- fontes primárias incorretas, adulteradas ou fora de contexto;
- decisões semanticamente ruins da LLM apesar de esquema válido;
- mudanças, indisponibilidade, custo e limites de provedores;
- falsos agrupamentos ou separações na deduplicação aproximada;
- ambiguidades de `robots.txt` e obrigações dos termos de uso;
- perda de trabalhos em execução após reinício;
- contenção do SQLite sob concorrência elevada;
- consumo de disco e questões de retenção ou direitos sobre HTML;
- alterações posteriores das páginas coletadas;
- interferência de DNS ou infraestrutura de rede;
- citações literais que ainda sejam enganosas sem contexto;
- lentidão do Streamlit sob carga, pois a PoC não é arquitetura de produção.
- submissões duplicadas quando clientes não enviarem chave de idempotência e a entrada tiver configurações diferentes;
- exposição indevida caso um operador ignore a restrição de localhost sem adicionar os controles documentados;
- envio de dados pessoais ao provedor externo após consentimento, sujeito à política desse fornecedor;
- cortes prematuros impostos pelos limites de custo, tempo, tokens ou armazenamento.

Esses riscos aparecem no relatório quando afetarem uma análise. O hash e o horário registram apenas o conteúdo observado, e conclusões sempre são qualificadas pelas evidências efetivamente encontradas.

## 23. Critérios de aceite adicionais

Além dos critérios funcionais originais:

1. Nenhuma conexão ocorre antes da validação do IP efetivamente utilizado.
2. Redirecionamentos repetem a validação completa e não carregam credenciais entre origens.
3. Falha de busca, scraping ou LLM não produz veredito factual.
4. Citação ausente da evidência não aparece no relatório.
5. Republicações não aumentam a contagem de fontes independentes.
6. Demonstração fictícia nunca é selecionada silenciosamente no modo real.
7. Análise interrompida termina em estado explicável e pode ser repetida.
8. SQLite não recebe HTML bruto sem limite.
9. Conteúdo externo não modifica instruções da LLM.
10. O relatório declara limitações de cobertura, coleta e temporalidade.
11. Todos os limites da Seção 5.1 possuem testes de fronteira e erros próprios.
12. A aplicação escuta somente em `127.0.0.1` por padrão.
13. Conteúdo só é enviado a LLM externa após consentimento explícito.
14. Submissões idempotentes não criam jobs nem custos duplicados.
15. Claims concluídas e interrompidas nunca são misturadas em resultado aparentemente completo.
16. O corpus de avaliação pode ser executado separadamente e compara regressões entre versões.
