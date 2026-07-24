# Release 4.5 — Produção e escala

## Escopo entregue

Esta entrega implementa os passos 19–20:

19. instrumentar o pipeline RAG com correlação, métricas, SLOs e alertas operacionais;
20. preparar processamento horizontal, reconciliação em lotes e operação segura.

## Observabilidade

- logs JSON em produção, com `requestId`, tenant quando disponível e duração;
- duração persistida por consulta RAG e processamento de evento;
- `GET /api/v1/health/rag`, protegido por bearer token de monitoramento;
- `GET /api/v1/metrics`, no formato Prometheus e com o mesmo token;
- `GET /api/v1/assistente/metricas`, restrito ao administrador ou gestor do tenant;
- janela, p95 e limites configuráveis.

O endpoint global consulta somente o outbox, sem texto de consultas ou chunks
privados. Métricas de qualidade permanecem sob o RLS do próprio tenant.

Alertas recomendados:

- `gabflow_rag_pipeline_healthy == 0`;
- idade da fila acima de `RAG_SLO_QUEUE_MAX_AGE_SECONDS`;
- aumento de `gabflow_rag_outbox_failed_window`;
- `sloAtendido == false` nas métricas tenant-scoped.

## Escala horizontal

O outbox possui filas lógicas `default`, `rag` e `all`. Claims usam
`FOR UPDATE SKIP LOCKED`, com índices parciais por prontidão e tipo:

```text
docker compose up -d --scale worker-rag=4
```

Somente o worker padrão executa o scheduler. Um advisory lock PostgreSQL impede
execução concorrente quando houver múltiplas réplicas.

## Reconciliação

O backfill usa paginação por chave e commits curtos:

```text
flask sync-operational-memory --batch-size 500
flask sync-operational-memory --tenant gabinete-demo --batch-size 500
```

A projeção por hash é idempotente, permitindo retomada segura.

## Configuração

```text
LOG_FORMAT=json
METRICS_BEARER_TOKEN=<segredo longo e aleatório>
WORKER_QUEUE=default
RAG_METRICS_WINDOW_HOURS=24
RAG_SLO_QUERY_P95_MS=15000
RAG_SLO_QUEUE_MAX_AGE_SECONDS=300
```

## Runbook resumido

1. Se a fila envelhecer, verificar PostgreSQL, armazenamento e embeddings.
2. Escalar `worker-rag` quando a entrada superar o processamento.
3. Não reprocessar eventos já publicados.
4. Após corrigir falhas definitivas, usar reprocessamento específico ou a
   reconciliação idempotente.
5. Nunca contornar RLS para produzir métricas.
6. Validar periodicamente o restore conjunto do banco e dos objetos RAG.

## Validação

- roteamento independente das filas;
- duração registrada no processamento;
- alerta por idade de fila;
- autenticação dos endpoints de monitoramento;
- métricas de qualidade isoladas por tenant;
- migration, downgrade e reaplicação validados em PostgreSQL.
