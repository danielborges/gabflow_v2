# Release 4.1 — Fundação segura do RAG Privado

## Escopo entregue

- roles PostgreSQL separadas para migration, API, worker e backup;
- API e worker executados como `NOSUPERUSER` e `NOBYPASSRLS`;
- runtime falha fechado quando conectado como superusuário, `BYPASSRLS` ou
  proprietário das tabelas RAG;
- contexto `app.tenant_id` local à transação;
- validação de vínculo entre usuário, sessão e tenant do JWT;
- RLS com negação por padrão e `FORCE ROW LEVEL SECURITY`;
- foreign keys compostas com `tenant_id`;
- worker ativa o tenant antes de carregar aggregates privados;
- namespace canônico de objetos por tenant, documento e versão;
- tokens de download assinados e vinculados ao tenant;
- compatibilidade temporária e estritamente validada com storage keys legadas;
- testes adversariais em SQLite e PostgreSQL.

## Tabelas protegidas

- `rag_documents`
- `rag_document_versions`
- `rag_chunks`
- `rag_assistant_queries`

Os filtros explícitos da aplicação foram preservados como defesa adicional.

## Contexto transacional

Requisições autenticadas validam usuário, sessão, tenant, contrato e módulo antes de
executar:

```sql
SELECT set_config('app.tenant_id', :tenant_id, true);
```

O valor é local à transação. Ausência de contexto torna linhas privadas invisíveis e
impede novas gravações. Uma transação já vinculada não pode trocar de tenant.

## Integridade composta

Documentos, versões, chunks, autores, revisores e consultas usam relações que
incluem `tenant_id`. A migration falha antes de ativar os controles se detectar
vínculos históricos cruzados.

## Runtime PostgreSQL

O container `db-roles` provisiona ou atualiza:

- `gabflow_app`;
- `gabflow_worker`;
- `gabflow_backup`.

O usuário `POSTGRES_USER` permanece reservado para migrations. O serviço `migrate`
executa migrations e seeds antes da API; a API não possui mais autorização para
executar DDL.

Em produção, `APP_DB_PASSWORD`, `WORKER_DB_PASSWORD` e `BACKUP_DB_PASSWORD` devem
ser distintos. O fallback para `POSTGRES_PASSWORD` existe apenas para facilitar a
transição de ambientes locais antigos.

## Armazenamento

Novos documentos usam:

```text
tenants/{tenant_id}/rag/{document_id}/{version_id}/{arquivo}
```

Downloads exigem token assinado com tenant, documento, versão, finalidade e
expiração. Chaves no formato legado continuam disponíveis enquanto
`RAG_ALLOW_LEGACY_STORAGE_KEYS=true`; após migrar os objetos existentes, essa opção
deve ser desativada.

## Validação

- suíte completa: 113 testes aprovados e 9 testes PostgreSQL ignorados quando não há
  banco de integração;
- suíte PostgreSQL isolada: 9 testes aprovados;
- lint Ruff aprovado;
- Docker Compose validado;
- bootstrap de roles validado em PostgreSQL 17 descartável.
- inicialização completa `db → roles → migration → API` validada com healthcheck
  usando a role restrita.
