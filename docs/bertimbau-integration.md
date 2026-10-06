# Integração futura do BERTimbau

O componente de risco linguístico é auxiliar e independente do fact-checking. Ele nunca deve
alterar `SUPPORTED`, `REFUTED`, `NEI` ou `CONFLICTING`.

## Contrato

Implemente `RiskAnalyzer.analyze(text) -> RiskAnalysisResult` com:

- `status`: `available`, `unavailable` ou `technical_error`;
- `label` e `score` somente quando houver inferência válida;
- `model_name` e `model_version` fixados ao artefato carregado;
- `message` em português, sem alegar que risco linguístico determina veracidade.

Até a integração, `DisabledRiskAnalyzer` retorna indisponibilidade e o relatório usa a mensagem
exata: "Análise linguística: aguardando integração do BERTimbau."

## Passos recomendados

1. Versionar tokenizer, pesos, rótulos, limiar e hash do artefato fora do repositório.
2. Validar licença, origem dos dados, vieses e desempenho em português brasileiro.
3. Carregar o modelo uma vez por processo, com limite de memória e timeout de inferência.
4. Preservar o texto original; truncamento precisa ser explícito no resultado.
5. Adicionar testes de acentos, negação, textos longos, falha de modelo e determinismo.
6. Registrar versão e status, mas nunca texto sensível ou vetores em logs.
7. Demonstrar em testes que falha ou rótulo do BERTimbau não modifica o veredicto factual.
8. Atualizar o corpus de avaliação e a documentação antes de habilitar a interface.

O adaptador vazio em `app/risk_analysis/bertimbau.py` é a fronteira prevista para a implementação.

