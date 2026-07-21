# Fundacao do Administrador do Gabinete

## Escopo implementado

- Menu de Administracao visivel apenas para usuarios com papel `admin` do gabinete.
- Area de trabalho de configuracao administrativa com secoes para gabinete, usuarios, jurisdicao, categorias, territorios, orgaos, templates, integracoes e auditoria.
- Persistencia de dados do vereador, informacoes do mandato, identidade visual e chefe de gabinete no tenant.
- APIs de perfil do gabinete em `/api/v1/admin/perfil-gabinete`.
- APIs de usuarios internos em `/api/v1/admin/usuarios`.
- Criacao de usuarios com limite contratado do gabinete.
- Perfil `representative` para vereador ou deputado estadual, cadastrado como usuario proprio do gabinete.
- Perfil `representative` com acesso executivo a painel, indicadores, solicitacoes, agenda, documentos, canais e assistente de IA, sem acesso ao menu administrativo.
- Aprovacao de minutas legislativas em revisao pelo perfil `representative`.
- Bloqueio e atualizacao de perfil de usuarios internos.
- Auditoria interna em `/api/v1/admin/auditoria`.
- Restricao de rotas administrativas de configuracao para `admin`.
- Reaproveitamento das configuracoes ja existentes de categorias, territorios, orgaos, templates, jurisdicao e integracoes dentro do workspace administrativo.

## Guardrails de isolamento

Todas as consultas e mutacoes do Administrador do Gabinete usam o `tenant_id` do token autenticado. O perfil nao tem acesso a `/api/v1/platform/*` e nao consegue operar sobre usuarios, configuracoes ou auditoria de outro gabinete.

O perfil `representative` tambem usa o isolamento por `tenant_id`. Ele pode consultar dados executivos do proprio gabinete e aprovar minutas, mas nao pode cadastrar configuracoes administrativas nem executar mutacoes operacionais restritas aos perfis `admin`, `manager` e `staff`.

## APIs principais

- `GET /api/v1/admin/perfil-gabinete`
- `PATCH /api/v1/admin/perfil-gabinete`
- `GET /api/v1/admin/usuarios`
- `POST /api/v1/admin/usuarios`
- `PATCH /api/v1/admin/usuarios/{user_id}`
- `GET /api/v1/admin/auditoria`
- `GET|POST|PATCH /api/v1/admin/categorias`
- `GET|POST /api/v1/admin/territorios`
- `GET|POST /api/v1/admin/orgaos`
- `GET|POST|PATCH /api/v1/admin/templates-resposta`
- `GET|POST /api/v1/admin/integracoes`

## Pendencias tecnicas mapeadas

- Evoluir permissoes para matriz granular por modulo e acao, alem dos papeis `admin`, `manager` e `staff`.
- Criar telas dedicadas para documentos legislativos, agenda, notificacoes, RAG e privacidade dentro da administracao do gabinete.
- Conectar identidade visual configurada a temas, logo e assets renderizados no workspace.
- Adicionar fluxo formal de designacao/aceite do chefe de gabinete.
- Implementar politicas configuraveis de consentimento, retencao e exportacao por gabinete.
- Adicionar testes automatizados de browser cobrindo o workspace administrativo completo.
