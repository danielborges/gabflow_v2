# ADR-005 — Arquitetura multi-tenant

## Status

Aceito

## Decisão

Utilizar tenant como fronteira obrigatória em autenticação, dados, busca, arquivos,
eventos e no domínio privado do RAG.

## Controles

- `tenant_id` obrigatório nas entidades privadas;
- contexto de tenant local à transação e negação por padrão quando ausente;
- Row-Level Security com `USING`, `WITH CHECK` e `FORCE ROW LEVEL SECURITY`;
- roles de aplicação e worker `NOSUPERUSER` e `NOBYPASSRLS`;
- proprietário/migrator e backup separados das credenciais de runtime;
- filtros explícitos no servidor mantidos como defesa adicional;
- constraints compostas que incluem `tenant_id` nos relacionamentos privados;
- chaves e namespaces de objetos segregados;
- workers ativam o tenant antes de carregar aggregates privados;
- testes automatizados de isolamento, concorrência e reutilização de conexão;
- auditoria de tentativas de acesso cruzado e suporte excepcional.

## Catálogo global

Conteúdo global publicado não pertence a um tenant e é disponibilizado por política
de distribuição. A existência do catálogo global não reduz a proteção do domínio
privado. Administradores globais não recebem acesso implícito aos dados internos dos
gabinetes.

## Exceções

Implantações fisicamente dedicadas podem ser oferecidas por requisito contratual ou
regulatório, preservando as mesmas fronteiras e contratos funcionais.
