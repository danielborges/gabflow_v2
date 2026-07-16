# P0 - Fundação Técnica e Segurança

## Escopo implementado

| Spec | Implementação |
| --- | --- |
| RF-001 | Login por e-mail, senha e tenant; sessão JWT em cookie HttpOnly |
| RF-002 | Perfis `admin`, `manager` e `staff`; helper de autorização por papel |
| RF-003 | Campo e fronteira de extensão para MFA; segundo fator não ativado neste incremento |
| RF-004 / RNF-008 | Auditoria de login/logout com usuário, tenant, IP e user-agent |
| RNF-006 | Configuração para cookie seguro e operação atrás de TLS |
| RNF-007 / ADR-005 | Tenant obrigatório no usuário, token, consultas e testes de isolamento |
| RNF-009 / RNF-010 | Interface semântica, foco visível e layout responsivo |
| RNF-011 | Request ID, health/readiness e Sentry no frontend/backend |
| RNF-012 | Imagens OCI e orquestração por Docker Compose |
| RNF-016 | Testes de autenticação, isolamento, auditoria, saúde e interface |

## Decisões

- Mantido o monólito modular estabelecido no ADR-001.
- Senhas usam Argon2id e nunca são registradas ou retornadas.
- O token de acesso não fica disponível ao JavaScript.
- Operações mutáveis autenticadas exigem token CSRF.
- Mensagens de login não revelam se tenant, usuário ou senha estão incorretos.
- O seed administrativo só executa com senha explicitamente configurada.

## Pendências deliberadas

- OIDC e MFA completo exigem definição de provedor e cenários de aceite próprios.
- PostgreSQL RLS será adicionado junto aos primeiros dados de domínio; neste P0 o
  isolamento é imposto por chave obrigatória, claims e filtros de servidor.
- Redis deve substituir o rate limiter em memória antes de escalar a API horizontalmente.

