# Release 8.7 — Cobertura eleitoral histórica

## Lacuna corrigida

O catálogo apresentava a quantidade de datasets publicados, mas não demonstrava se a
série eleitoral exigida por RF-011 estava completa. Um único cargo em uma única UF podia
ser interpretado visualmente como “cobertura oficial”, mesmo com anos e cargos ausentes.

## Matriz de cobertura

A série suportada passa a ser explícita e auditável:

- municipais: 2012, 2016, 2020 e 2024, cargos Prefeito e Vereador;
- gerais: 2014, 2018 e 2022, cargos Presidente, Governador, Senador, Deputado Federal e
  Deputado Estadual/Distrital;
- granularidades publicadas pelo pipeline atual: município e zona eleitoral.

Cada ciclo/UF recebe o estado `COMPLETE`, `PARTIAL` ou `MISSING`, com cargos presentes,
ausentes, datasets, granularidades e URL oficial do TSE. O percentual considera somente
ciclos completos; cargas parciais continuam consultáveis, mas são rotuladas como tal.

## Importação e publicação

O comando abaixo planeja ou executa o backfill idempotente com os arquivos oficiais:

```bash
flask electoral-backfill --uf MG --dry-run
flask electoral-backfill --uf MG
```

É possível repetir `--year` para limitar anos. Ano e escopo incompatíveis são rejeitados.
Quando uma versão completa de um ciclo é publicada, todas as versões parciais sobrepostas
são substituídas para impedir duplicidade de candidatos e votos. Uma carga parcial não
pode se sobrepor posteriormente a uma versão completa.

## Contratos e interface

`GET /api/v1/electoral/coverage` aceita `uf` e retorna datasets mais a matriz histórica.
O painel do Parlamentar exibe ciclos completos, percentual e a lista de ciclos parciais ou
ausentes, sem mascarar falta de dados com a nota de qualidade das cargas existentes.

Testes cobrem matriz ano/escopo, substituição de recorte parcial, plano de backfill,
contrato OpenAPI e apresentação acessível do estado incompleto.

## Homologação em Minas Gerais

O backfill operacional de MG foi concluído para os sete ciclos, totalizando 6.036.007
resultados publicados, sem linhas inválidas. Nas eleições gerais, o parser
`tse-munzona-v3` combina os cargos estaduais do arquivo de MG com Presidente no arquivo
nacional, sem duplicar os demais cargos.

A promoção passou a trabalhar em lotes e a fazer *upsert* incremental, evitando manter
milhões de resultados em memória. Cargas interrompidas nos estados `DOWNLOADED` ou
`PARSED` também podem ser retomadas. A migração `v5f3d0a8b2c4` completa os manifests
legados com cargos e granularidades, permitindo que o catálogo consulte a cobertura sem
varrer toda a tabela de resultados.
