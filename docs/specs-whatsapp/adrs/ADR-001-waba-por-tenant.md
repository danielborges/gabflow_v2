# ADR-001 — WABA e número próprios por tenant

**Status:** Aceito

## Contexto

O GabFlow é multi-tenant e precisa preservar identidade institucional, isolamento, portabilidade e reputação de cada gabinete.

## Decisão

Cada gabinete possui sua WABA, número, templates e método de cobrança. Um único aplicativo Meta do GabFlow atua como Tech Provider e conecta clientes por Embedded Signup.

## Consequências

O onboarding é mais elaborado, porém bloqueios, reputação, cobrança e offboarding ficam isolados. Um número central compartilhado é proibido como arquitetura padrão.
