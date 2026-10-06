# Integração do BERTimbau V4

O componente de risco linguístico é auxiliar e independente do fact-checking. Ele nunca
altera `SUPPORTED`, `REFUTED`, `NEI` ou `CONFLICTING`.

## Fonte fixada

O adaptador consome diretamente o bucket público
`Alvinn007/bertimbau-fakenews-detector-v4-bucket`. Como buckets são mutáveis, a aplicação
fixa tamanho, identificador Xet e SHA-256 de `config.json`, `model.safetensors`,
`tokenizer.json` e `tokenizer_config.json`. Uma alteração silenciosa produz
`technical_error`; ela não é aceita como uma nova versão automaticamente.

O `config.json` validado declara `BertForSequenceClassification` e os rótulos:

- `0`: `FALSA`;
- `1`: `VERDADEIRA`.

O modelo é carregado apenas do cache local, com `safetensors`, `local_files_only=True` e
`trust_remote_code=False`.

## Ativação

Instale as dependências opcionais:

```bash
.venv/bin/pip install -e '.[dev,bertimbau]'
```

Configure:

```dotenv
RISK_MODEL_MODE=bertimbau
BERTIMBAU_CACHE_DIR=./data/models/bertimbau-v4
BERTIMBAU_MAX_INPUT_TOKENS=512
HF_TOKEN=
```

O token não é necessário enquanto o bucket permanecer público. Se for usado, mantenha-o em
variável de ambiente ou no `.env`, que não é versionado.

Na primeira análise, o download é feito em um diretório temporário. Somente depois de todos
os hashes serem validados o snapshot é movido para o cache definitivo. O peso ocupa cerca de
436 MB; a memória de inferência é maior e deve ser medida na máquina de implantação.

## Semântica do resultado

`RiskAnalyzer.analyze(text)` devolve `label`, `score`, bucket e versão apenas após inferência
válida. O texto é limitado a 512 tokens; quando há truncamento, o relatório informa isso.
Falha de rede, dependência ausente, hash divergente ou erro de inferência retorna
`technical_error` sem rótulo nem score.

Os números publicados no README do bucket são auto-relatados sobre 100 notícias. Eles não
substituem uma avaliação independente de generalização, viés, calibração, textos adversariais
e mudança de domínio antes de uso decisório.

## Atualização deliberada do modelo

Para aceitar uma nova versão do bucket:

1. revise origem, licença, dados, rótulos e métricas;
2. baixe os quatro artefatos em ambiente controlado;
3. confira `id2label`, arquitetura e limite de contexto;
4. atualize tamanhos, identificadores Xet e SHA-256 em
   `app/risk_analysis/bertimbau.py`;
5. execute os testes e uma avaliação independente antes da implantação.
