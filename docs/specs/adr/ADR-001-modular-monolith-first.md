# ADR-001 — Monólito Modular como arquitetura inicial

## Status
Aceito

## Contexto
O domínio possui vários módulos, mas a equipe precisa evoluir rapidamente sem assumir a complexidade operacional de microsserviços prematuros.

## Decisão
Adotar monólito modular com fronteiras explícitas, eventos internos e contratos estáveis.

## Consequências
- implantação simplificada;
- transações mais fáceis;
- menor custo operacional;
- possibilidade de extração futura de módulos;
- necessidade de testes de arquitetura para evitar acoplamento.
