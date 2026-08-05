# Release 7.2 — Pesquisa e resultado territorial

## Entrega

O Incremento 2 fecha a primeira jornada analítica do módulo: o Parlamentar seleciona uma eleição,
pesquisa uma candidatura e examina votos, participação e posição por município ou zona eleitoral.

## Contratos

- `GET /api/v1/electoral/candidates`: pesquisa paginada por nome sem acento, nome de urna, número,
  partido, cargo e eleição publicada.
- `GET /api/v1/electoral/candidates/{candidate_id}/results`: resultado paginado e ordenável por
  município ou zona eleitoral.

As respostas identificam pessoa e candidatura separadamente para distinguir homônimos. Também
incluem fonte, hash, versão publicada, qualidade, denominador e fórmula reproduzível.

## Metodologia

Para cada território, o denominador é a soma dos votos nominais válidos de todas as candidaturas do
mesmo cargo e eleição. A participação é:

`votos_do_candidato / votos_nominais_validos_do_cargo_no_territorio`

A posição usa `RANK` decrescente por votos dentro do território. Municípios são agregados a partir
das zonas oficiais e recebem um UUID determinístico vinculado à versão do dataset. Zonas mantêm o
identificador persistido do catálogo.

Níveis sem dados confiáveis, como bairro, local ou seção no dataset atual, retornam `422` com a lista
de níveis disponíveis; não são inferidos.

## Segurança e auditoria

Os endpoints exigem a capacidade `consultar_dados_publicos` e somente usam versões `PUBLISHED`.
A auditoria registra eleição, IDs, nível, paginação e tamanho do termo pesquisado, sem guardar o
texto da pesquisa.

## Caso de aceite

No dataset piloto 2024/MG/Vereador, a pesquisa `Mauricio Delgado` deve localizar a candidatura
18010/REDE e retornar 5.453 votos em Juiz de Fora, com detalhamento nas quatro zonas eleitorais.
