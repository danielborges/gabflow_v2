# Release 8.3 — metas e portfólio de cenários

## Escopo entregue

- portfólios com até 20 cenários do mesmo recorte e snapshot;
- associação e remoção lógica de cenários sem mutação dos artefatos originais;
- cenário de referência explicitamente não preditivo;
- metas de votos ou participação no total agregado ou por território;
- cálculo de valor, diferença, atingimento percentual e estado da meta por cenário;
- histórico append-only de criação, atualização, associação, remoção, metas, referência e
  exportação;
- arquivamento do portfólio, bloqueando novas mutações;
- exportação CSV com finalidade obrigatória, auditoria, metodologia e disclaimer;
- interface para criação, composição, metas, referência, avaliação, histórico e exportação.

## Persistência e isolamento

- migration `t3d1b8f5a7c9`;
- `electoral_scenario_portfolios`;
- `electoral_scenario_portfolio_items`;
- `electoral_scenario_portfolio_events`;
- RLS habilitada e forçada nas três tabelas;
- chaves compostas de tenant para mandato, usuários, cenários e portfólio;
- remoção de associação implementada por `removed_at`, sem política SQL `DELETE`.

## Regras analíticas

- cenários são compatíveis somente quando eleição, candidatura, nível, recorte municipal,
  versão do dataset e hash de origem coincidem;
- metas de participação usam fração entre 0 e 1 no contrato;
- a referência não é previsão, recomendação ou resultado oficial;
- o método é versionado como `scenario-portfolio-goals-v1`;
- todas as avaliações retornam `simulation: true` e o disclaimer eleitoral.

## Homologação

- integração backend cobre criação, metas, avaliação, referência, CSV, histórico e remoção;
- frontend cobre criação, meta, atingimento, referência e consulta do histórico;
- migration PostgreSQL cobre upgrade, rollback/reapply, RLS e grants runtime;
- OpenAPI, modelo de dados e cenários Gherkin atualizados.
