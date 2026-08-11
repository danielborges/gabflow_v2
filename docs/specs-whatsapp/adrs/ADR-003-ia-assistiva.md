# ADR-003 — IA assistiva, estruturada e revisável

**Status:** Aceito

## Contexto

LLMs melhoram transcrição e triagem, mas podem errar, sofrer prompt injection e produzir decisões opacas.

## Decisão

A IA gera apenas saídas estruturadas e versionadas, com confiança e revisão. Identidade, autorização, tenant, opt-out e transições irreversíveis são determinísticos. Falha da IA ativa contingência humana.

## Consequências

Há mais regras e telas de revisão, em troca de segurança, auditabilidade e continuidade operacional.
