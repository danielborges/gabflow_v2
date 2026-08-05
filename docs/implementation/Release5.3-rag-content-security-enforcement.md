# Release 5.3 — Quarentena e enforcement pré-derivação

## Resultado

Uploads privados e versões globais só produzem chunks e embeddings quando o gateway
retorna `CLEAN/ALLOW`. Qualquer outro estado encerra a ingestão de forma fail-closed,
remove derivados existentes, limpa o texto extraído e impede publicação e retrieval.

Memórias operacionais e feedback preservam a quarentena fail-closed já existente.

## Ciclo de quarentena

1. O arquivo original permanece no armazenamento restrito para revisão autorizada.
2. Chunks, embeddings, texto extraído, modelo e contadores derivados são eliminados.
3. Uma versão anteriormente publicada é despublicada imediatamente.
4. A fila registra o evento como processado, sem repetir indefinidamente o payload.
5. A listagem de quarentena expõe somente metadados e não inclui link de download.
6. Um administrador pode registrar `APPROVED` ou `REJECTED` com justificativa.
7. Apenas `APPROVED` para o checksum atual autoriza reprocessamento.
8. O novo processamento registra `CLEAN/ALLOW` com a proveniência da revisão antes
   de recriar derivados; a publicação continua sendo uma ação separada.

## Defesa em profundidade

Além do purge, os caminhos ORM, FTS/pgvector e catálogo global filtram explicitamente
`security_status = CLEAN` e `security_action = ALLOW`. Assim, artefatos residuais ou
dados legados não se tornam recuperáveis por engano.

## API

- `GET /api/v1/rag/quarentena`;
- `PATCH /api/v1/rag/documentos/{documentoId}/versoes/{versaoId}/seguranca`;
- `GET /api/v1/platform/rag-global/quarentena`;
- `PATCH /api/v1/platform/rag-global/colecoes/{colecaoId}/documentos/{documentoId}/versoes/{versaoId}/seguranca`.

As APIs de reprocessamento existentes retornam conflito enquanto não houver aprovação
válida. Auditorias armazenam decisão, checksum e identificadores, nunca o payload.

## Persistência

A migração `d5f9b2c7a314` adiciona timestamps de quarentena/purge e a decisão de
revisão vinculada ao checksum às versões privadas e globais.

## Limites

O detector continua determinístico. Canonicalização avançada, classificador dedicado
e tratamento de ataques ofuscados pertencem ao incremento 5.4.
