# Fundacao do Administrador do Gabinete

## Escopo implementado

- Menu de Administracao visivel apenas para usuarios com papel `admin` do gabinete.
- Area de trabalho de configuracao administrativa com secoes para gabinete, usuarios, jurisdicao, categorias, territorios, orgaos, templates, integracoes e auditoria.
- Persistencia de dados institucionais do gabinete, redes sociais oficiais, identidade visual e chefe de gabinete no tenant.
- Catalogo global `political_parties` populado por migracao com partidos registrados no TSE e usado no search-select de partido do parlamentar.
- Endpoint `GET /api/v1/admin/partidos` com busca por sigla, nome ou numero de legenda.
- Aba administrativa propria para cadastro do parlamentar, separada dos dados do gabinete.
- Endpoint `GET|PATCH /api/v1/admin/parlamentar` para dados do titular, contato, partido, redes sociais, areas prioritarias, status e historico de mandatos com votos recebidos.
- Endpoint `POST /api/v1/admin/parlamentar/insights-oficiais` para gerar fontes oficiais de conferencia e sugestoes de insight com auditoria.
- APIs de perfil do gabinete em `/api/v1/admin/perfil-gabinete`.
- Aba Gabinete com nome do gabinete, Camara Municipal, municipio, estado, endereco institucional, telefone, e-mail oficial, horario de atendimento, site, redes sociais, logotipo e cores institucionais.
- APIs de usuarios internos em `/api/v1/admin/usuarios`.
- Criacao de usuarios com limite contratado do gabinete.
- Perfil `representative` para vereador ou deputado estadual, cadastrado como usuario proprio do gabinete.
- Perfil `representative` com acesso executivo a painel, indicadores, solicitacoes, agenda, documentos, canais e assistente de IA, sem acesso ao menu administrativo.
- Aprovacao de minutas legislativas em revisao pelo perfil `representative`.
- Designacao funcional de Chefe de Gabinete por `chief_of_staff_id`, limitada a usuario ativo do proprio gabinete com perfil interno.
- Exposicao de `chefeGabinete` e `funcoes=["chefe_gabinete"]` na sessao e na lista administrativa de usuarios.
- Permissoes adicionais de supervisao legislativa para Chefe de Gabinete sem conversao automatica para `admin`: rejeitar minuta em revisao, registrar protocolo externo e adicionar tramitacao.
- Bloqueio e atualizacao de perfil de usuarios internos.
- Auditoria interna em `/api/v1/admin/auditoria`.
- Restricao de rotas administrativas de configuracao para `admin`.
- Reaproveitamento das configuracoes ja existentes de categorias, territorios, orgaos, templates, jurisdicao e integracoes dentro do workspace administrativo.

## Guardrails de isolamento

Todas as consultas e mutacoes do Administrador do Gabinete usam o `tenant_id` do token autenticado. O perfil nao tem acesso a `/api/v1/platform/*` e nao consegue operar sobre usuarios, configuracoes ou auditoria de outro gabinete.

O perfil `representative` tambem usa o isolamento por `tenant_id`. Ele pode consultar dados executivos do proprio gabinete e aprovar minutas, mas nao pode cadastrar configuracoes administrativas nem executar mutacoes operacionais restritas aos perfis `admin`, `manager` e `staff`.

A funcao `chefe_gabinete` tambem e isolada por `tenant_id` e nasce da designacao feita pelo Administrador do Gabinete. Ela nao altera o papel base do usuario e nao libera `/api/v1/admin/perfil-gabinete`; quando o usuario tambem precisar administrar configuracoes, o perfil `admin` deve ser atribuido explicitamente.

## APIs principais

- `GET /api/v1/admin/perfil-gabinete`
- `PATCH /api/v1/admin/perfil-gabinete`
- `GET /api/v1/admin/partidos`
- `GET /api/v1/admin/parlamentar`
- `PATCH /api/v1/admin/parlamentar`
- `POST /api/v1/admin/parlamentar/insights-oficiais`
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
- Evoluir a matriz granular de permissoes do Chefe de Gabinete para aprovar encerramentos, autorizar respostas e distribuir solicitacoes com regras dedicadas por acao.
- Implementar politicas configuraveis de consentimento, retencao e exportacao por gabinete.
- Adicionar testes automatizados de browser cobrindo o workspace administrativo completo.
- Automatizar rotina periodica para reconciliar logos oficiais dos partidos quando a Justica Eleitoral publicar fonte estruturada de imagem por partido.
