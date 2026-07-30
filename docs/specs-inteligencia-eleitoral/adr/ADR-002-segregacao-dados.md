# ADR-002 — Segregação entre dados eleitorais e dados do mandato

Status: Aceito

## Contexto

O GabFlow contém dados pessoais de atendimentos. Cruzamentos inadequados poderiam produzir perfilamento político ou tratamento discriminatório.

## Decisão

Manter domínios lógicos separados. A camada eleitoral usa dados públicos agregados. A integração com o mandato expõe somente métricas agregadas, com limiar mínimo padrão de 10 ocorrências, supressão de categorias sensíveis e auditoria.

## Consequências

- Reduz risco de reidentificação e uso incompatível.
- Impede drill-down da camada eleitoral para ficha de cidadão.
- Algumas regiões pequenas terão métricas suprimidas.
- Revisão jurídica e RIPD devem preceder produção.
