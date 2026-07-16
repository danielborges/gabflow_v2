# ADR-002 — Integrações orientadas a eventos

## Status
Aceito

## Decisão
Usar eventos de domínio para processamento assíncrono, integrações, analytics e IA.

## Regras
- eventos são imutáveis;
- devem possuir tenant, correlationId e versão;
- publicação deve usar padrão outbox;
- consumidores devem ser idempotentes.
