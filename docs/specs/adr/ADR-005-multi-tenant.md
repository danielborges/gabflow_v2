# ADR-005 — Arquitetura multi-tenant

## Status
Aceito

## Decisão
Utilizar tenant como fronteira obrigatória em autenticação, dados, busca, arquivos, eventos e RAG.

## Controles
- tenantId obrigatório;
- filtros aplicados no servidor;
- testes automatizados de isolamento;
- chaves e namespaces segregados;
- auditoria de acesso cruzado.
