# Segurança

## Modelo de ameaças

URLs, HTML, snippets de busca, respostas de provedores e texto do usuário são tratados como
dados não confiáveis. O sistema assume que uma fonte pode tentar acessar a rede interna,
redirecionar a coleta, injetar instruções na LLM, exceder recursos ou forjar referências.

## SSRF, DNS rebinding e redirecionamentos

1. Apenas `http` e `https`, sem credenciais embutidas e nas portas 80/443.
2. Todas as respostas A/AAAA são validadas; endereços privados, loopback, link-local,
   multicast, reservados, não especificados e representações numéricas ambíguas são bloqueados.
3. A conexão usa o IP já aprovado, preservando `Host` e SNI. Uma segunda resolução DNS não
   decide o destino da conexão, mitigando rebinding entre validação e uso.
4. Cada redirecionamento é resolvido e validado novamente. Credenciais e cookies são removidos
   quando a origem muda. O número de saltos é limitado.
5. O transporte não usa proxies do ambiente.

## `robots.txt` e coleta

Regras são armazenadas em cache por origem. `404` permite coleta; `401/403` bloqueia; falha de
rede, resposta ambígua ou status inesperado resulta em `UNKNOWN` e bloqueio. O usuário pode
colar o texto manualmente. Tipo de conteúdo, tamanho, timeout, paywall, login e CAPTCHA têm
resultados distintos.

## LLM e referências

- Conteúdo externo é delimitado como não confiável.
- Respostas obedecem JSON Schema estrito e recebem no máximo uma tentativa de correção.
- IDs e URLs não fornecidos pelo pipeline são rejeitados.
- Veredictos factuais exigem evidência; citações são remapeadas para caracteres literais.
- `NEI`, falha técnica e conflito são estados diferentes.
- Processamento externo real requer consentimento explícito na API.

## Recursos, armazenamento e exposição

Chamadas, tokens, tempo, downloads, artefatos, concorrência e fila possuem limites. HTML bruto
não é retornado pela API e fica fora do SQLite. Logs aplicam redação a segredos. CORS e os
comandos documentados restringem a aplicação a `localhost`; esta PoC não deve ser publicada
diretamente na internet.

## Modelo local e cadeia de fornecimento

O BERTimbau é baixado somente do bucket explicitamente configurado. Como esse armazenamento é
mutável, tamanho, identificador Xet e SHA-256 de cada artefato são fixados no código; divergência
interrompe a carga. O download é promovido ao cache apenas depois da validação completa. A carga
usa `safetensors`, bloqueia código remoto e opera localmente após o download. `HF_TOKEN`, quando
necessário, é lido de segredo de ambiente e não deve aparecer em logs ou relatórios. O rótulo do
modelo é isolado do veredito factual e qualquer falha vira indisponibilidade técnica.

## Resposta operacional

Em caso de suspeita: interrompa API e UI, revogue chaves externas, preserve o SQLite e os hashes
para auditoria, remova artefatos conforme a política de retenção e execute novamente os testes
de segurança antes de reativar o serviço.
