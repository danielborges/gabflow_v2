# Release 8.11 — Fechamento das funcionalidades SHOULD/COULD

Esta release fecha a lacuna 7 da Inteligência Eleitoral com funcionalidades operacionais
que permaneciam apenas na especificação.

## Entregas

- preferências privadas por usuário para eleição, cargo, recorte e indicadores;
- criação e manutenção de segmentos territoriais agregados;
- briefing pré-visita derivado do snapshot e da agenda institucional;
- relatórios recorrentes diários, semanais ou mensais para destinatários internos ativos;
- heatmaps e clusters baseados em grupos não suprimidos e locais públicos confirmados;
- rota cronológica de agenda que exclui eventos vinculados a cidadãos e não retorna o
  endereço textual do compromisso.

## Segurança e governança

As preferências e os segmentos usam RLS por tenant e usuário. Os agendamentos usam RLS
por tenant, autorização por mandato e auditoria de criação/desativação. Toda visualização
geográfica reaproveita o limiar do snapshot; pontos residenciais e dados individuais de
cidadãos são proibidos. O briefing é identificado como rascunho editável sujeito à revisão
humana.

## Operação

O scheduler consulta agendamentos vencidos com bloqueio concorrente, cria um job por
destinatário, publica cada job pelo outbox e atualiza a próxima execução. O painel do
mandato concentra as seis capacidades em seções progressivamente reveladas, evitando
poluir a jornada principal.

## Critérios de homologação

- contrato OpenAPI alinhado exatamente às rotas implementadas;
- migração com RLS forçada nas três novas tabelas;
- isolamento de preferências e segmentos por usuário;
- supressão e exclusão de locais privados testadas;
- recorrência cria apenas jobs para usuários internos ativos;
- testes de regressão do painel, API, worker, lint e build aprovados.
