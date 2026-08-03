# Release 7.1 — Pipeline TSE e catálogo consultável

## Entrega

Este incremento transforma a fundação eleitoral em um catálogo público global, acessível apenas por atores autorizados do módulo. A carga é independente de tenant; autorização e auditoria continuam vinculadas ao gabinete que consulta.

## Pipeline

1. `flask electoral-import` baixa ou recebe um ZIP com URL de proveniência sob `*.tse.jus.br`.
2. O arquivo bruto é preservado por SHA-256 e a combinação `hash + cobertura` torna a operação idempotente.
3. CSVs são lidos em streaming e inseridos em staging por lotes, filtrados por ano, UF e cargo.
   Quando o ZIP contém simultaneamente a partição `BRASIL` e arquivos estaduais, o parser seleciona
   exclusivamente a partição da UF solicitada para impedir dupla contagem.
4. Campos obrigatórios, votos não negativos, cobertura e totalização esperada bloqueiam publicação quando divergentes.
5. Linhas válidas são promovidas para eleição, cargo, partido, candidato, candidatura, território e resultado.
6. A publicação substitui atomicamente a versão anterior do mesmo recorte e emite eventos no outbox.

## Operação

Exemplo com download oficial:

```bash
flask --app wsgi:app electoral-import \
  --source-url https://cdn.tse.jus.br/estatistica/sead/odsele/votacao_candidato_munzona/votacao_candidato_munzona_2022.zip \
  --year 2022 --scope general --uf MG --office-code 6
```

Uma carga pode ser validada sem publicação com `--no-publish` e publicada depois por `flask electoral-publish --dataset-id UUID`.

## Contratos entregues

- `GET /api/v1/electoral/elections`
- `GET /api/v1/electoral/offices`
- `GET /api/v1/electoral/datasets`
- `GET /api/v1/electoral/coverage`
- `GET /api/v1/electoral/quality`

O catálogo não recebe RLS por ser um acervo oficial compartilhado e somente leitura para o papel runtime da API. As tabelas de mandato, configuração e delegação seguem com RLS por tenant.

## Limite deste incremento

Novas cargas continuam exigindo recorte explícito para evitar ingestão nacional acidental. Busca de
candidatos e resultados territoriais na API ficam para o Incremento 2.

## Carga-piloto local

Em 3 de agosto de 2026 foi publicada no ambiente local a versão
`ccfd70f9-4962-4d50-b56c-ee26b6062782`, usando o recurso oficial de votação nominal por município
e zona de 2024, com o recorte `MG / Vereador (13)`:

- parser `tse-munzona-v2`;
- arquivo selecionado `votacao_candidato_munzona_2024_MG.csv`;
- 91.134 linhas válidas e nenhuma inválida;
- 11.273.397 votos no recorte estadual;
- SHA-256 `ca25961135929c5f98d01741d4fcecf912b4edc1dcdc69cc8648eb60c3e32179`;
- qualidade calculada `1.0`.

O caso de aceite foi Maurício Henrique Pinto de Oliveira Delgado, nome de urna Maurício Delgado,
número 18010, REDE 18: 5.453 votos em quatro zonas de Juiz de Fora. Uma execução anterior do parser
`v1`, que somava as partições estadual e nacional, foi preservada como `REJECTED` para manter a
rastreabilidade do incidente.
