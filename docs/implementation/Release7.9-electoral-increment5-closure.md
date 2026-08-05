# Release 7.9 — Fechamento da Inteligência Integrada do Mandato

## Escopo

Esta release fecha as lacunas funcionais remanescentes do Incremento 5 sem ampliar o uso de
dados pessoais e sem usar desempenho eleitoral para priorização de atendimento.

## Overlay e briefing territorial

- `GET /api/v1/electoral/territories/{territory_id}/mandate-overlay` entrega o recorte
  operacional de um snapshot persistido e reproduzível;
- `GET /api/v1/electoral/territories/{territory_id}/briefing` produz um briefing estruturado,
  explicitamente marcado como rascunho sujeito a revisão humana;
- grupos abaixo do limiar não recebem fatos, categorias ou indicadores protegidos;
- fonte temporal, hash de configuração, fórmula e contexto eleitoral ficam separados;
- na ausência de crosswalk oficial/revisado, a resposta declara que o overlay eleitoral não
  está disponível. Nenhuma geometria ou correspondência é inferida.

## Alertas configuráveis

- preferências individuais por usuário e mandato;
- canais `IN_APP` e `EMAIL` e frequências imediata, diária ou semanal;
- tipos estruturados para SLA degradado, SLA vencido, ausência de agenda, ausência de
  fiscalização e compromisso vencido;
- feed derivado do snapshot mais recente e filtrado pelas preferências;
- RLS forçada por `tenant_id + user_id` e auditoria de configuração e consulta;
- baixa votação nunca cria alerta.

## Estabilização da Release 7.8

- fluxo de compromisso, evidência append-only, prazo derivado e mapa operacional coberto por
  testes de serviço e interface;
- ponto não confirmado como público continua rejeitado;
- navegação por URL e submenu eleitoral corrigidos e cobertos por regressão;
- migração 7.8 permanece isolada da migração 7.9, permitindo rollback independente.

## Gate automatizado local

Em 4 de agosto de 2026:

- 23 testes eleitorais de backend aprovados;
- 59 testes de frontend aprovados, incluindo briefing, alertas e regressão de navegação;
- 9 testes de migração PostgreSQL/PostGIS aprovados em banco efêmero com roles de runtime;
- compilação Python, lint e build de frontend aprovados;
- contrato OpenAPI alinhado às rotas tenant-facing implementadas no Incremento 5.

O mesmo gate PostgreSQL/PostGIS deve permanecer obrigatório no pipeline antes do merge. A
homologação operacional com dados reais autorizados continua sendo uma atividade do gabinete-piloto
e não deve reutilizar a carga `[DEMO]` como evidência pública.
