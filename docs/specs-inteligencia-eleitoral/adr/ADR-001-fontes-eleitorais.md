# ADR-001 — Fontes eleitorais oficiais e versionadas

Status: Aceito

## Contexto

O módulo depende de resultados eleitorais confiáveis, reproduzíveis e atualizáveis.

## Decisão

Usar dados públicos oficiais do TSE como fonte primária. Cada ingestão será imutável e identificada por URL/origem, horário, hash, versão do parser e nota de qualidade. Uma versão só será publicada após validação de totalizações.

## Consequências

- Análises podem ser reproduzidas.
- Correções oficiais geram nova versão.
- O armazenamento cresce, exigindo particionamento e política de arquivamento.
- Mapeamentos derivados, como bairro, serão explicitamente rotulados.
