# ADR-002 — Webhook assíncrono, idempotente e com outbox

**Status:** Aceito

## Contexto

Webhooks podem ser repetidos, atrasados ou entregues fora de ordem. Processamento de mídia e IA é lento.

## Decisão

O gateway valida, persiste a chave idempotente e responde rapidamente. Workers processam eventos; mudanças e comandos de saída usam transactional outbox. Status só avança de forma monotônica.

## Consequências

Exige fila, DLQ, observabilidade e reconciliação, mas evita perda e duplicação de protocolos/mensagens.
