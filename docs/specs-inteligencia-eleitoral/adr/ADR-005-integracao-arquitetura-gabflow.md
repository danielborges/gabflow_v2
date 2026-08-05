# ADR-005 — Integração com a arquitetura atual do GabFlow

Status: Aceito

## Contexto

A stack de referência do pacote eleitoral cita FastAPI, Redis, Celery e Qdrant. O
GabFlow em execução utiliza Flask, SQLAlchemy, outbox transacional em PostgreSQL,
worker próprio e um subsistema RAG já governado. Criar uma segunda stack para a
fundação eleitoral aumentaria a superfície operacional e duplicaria mecanismos de
autorização, tenant, auditoria e jobs.

## Decisão

Implementar Inteligência Eleitoral como bounded context dentro do monólito modular
atual. Rotas usam um blueprint Flask em `/api/v1/electoral`; jobs usarão o outbox e os
workers existentes; recursos privados usam o contexto transacional e RLS existentes.
O catálogo eleitoral será global e logicamente separado das tabelas privadas do
mandato. Nova infraestrutura só será adotada após benchmark demonstrar necessidade.

O módulo é opt-in e exige simultaneamente entitlement do plano, habilitação do
gabinete, mandato ativo e capacidade do ator. O Parlamentar possui titularidade; uma
delegação, quando liberada, será temporária e granular.

## Consequências

- autorização, auditoria e isolamento seguem um único modelo operacional;
- a equipe pode entregar fatias verticais sem operar um segundo backend;
- o contrato continua documentado em OpenAPI/AsyncAPI, independentemente do framework;
- escala de ingestão e consulta deverá ser medida antes de introduzir cache ou filas
  adicionais;
- o catálogo global exigirá grants e regras próprias, enquanto artefatos do gabinete
  permanecem sob RLS.
