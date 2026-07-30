# ADR-004 — PostgreSQL/PostGIS para inteligência territorial

Status: Aceito

## Contexto

O módulo precisa consultar hierarquias territoriais, mapas, interseções e agregações, mantendo compatibilidade com a stack PostgreSQL do GabFlow.

## Decisão

Adotar PostGIS no PostgreSQL principal, com geometrias versionadas, índices GiST, particionamento de resultados e materialized views. Serviços de tiles podem ser adicionados quando o volume justificar.

## Consequências

- Menor complexidade operacional inicial.
- Transações e autorização permanecem próximas ao domínio.
- Cargas e índices exigem rotina específica de manutenção.
- Em escala nacional elevada, tiles pré-computados e réplicas de leitura poderão ser necessários.
