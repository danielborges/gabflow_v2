# Fundacao do Administrador Geral

## Escopo implementado

- Novo perfil `platform_admin`, sem vinculo obrigatorio com gabinete.
- Login sem campo de ambiente para Administrador Geral.
- Area de trabalho separada para administracao da plataforma.
- APIs em `/api/v1/platform` protegidas por perfil global.
- Cadastro e gestao de gabinetes, plano, contrato, limites e modulos.
- Controle efetivo de modulos em menus, busca global e endpoints tenant-scoped.
- Workflow contratual com motivo obrigatorio, status sincronizado e historico por gabinete.
- Consumo agregado por gabinete sem exposicao de conteudo interno.
- Configuracoes globais para parametros, modelos, provedores, flags e politicas.
- Registro de suporte excepcional com motivo, autorizacao, escopo e auditoria.
- Auditoria administrativa com `tenant_id` nulo para acoes de plataforma.

## Guardrails de privacidade

O modulo de plataforma nao disponibiliza endpoints para listar solicitacoes, documentos, cidadaos, mensagens ou bases RAG de um gabinete. O consumo e retornado por contagem agregada. Acesso excepcional de suporte e apenas registrado; qualquer futura ferramenta de impersonacao ou diagnostico devera validar esse registro antes de abrir dados internos.

## Operacao

Para criar o Administrador Geral em ambiente local ou container:

```bash
flask --app wsgi:app seed-platform-admin \
  --email platform@gabflow.local \
  --password "$SEED_PLATFORM_ADMIN_PASSWORD"
```

No container, o seed opcional e controlado por:

```env
SEED_PLATFORM_ADMIN_ON_START=true
SEED_PLATFORM_ADMIN_EMAIL=platform@gabflow.local
SEED_PLATFORM_ADMIN_PASSWORD=
```

## APIs principais

- `GET /api/v1/platform/overview`
- `GET /api/v1/platform/gabinetes`
- `POST /api/v1/platform/gabinetes`
- `PATCH /api/v1/platform/gabinetes/{tenant_id}`
- `GET /api/v1/platform/gabinetes/{tenant_id}/contrato`
- `POST /api/v1/platform/gabinetes/{tenant_id}/contrato`
- `GET /api/v1/platform/gabinetes/{tenant_id}/consumo`
- `POST /api/v1/platform/gabinetes/{tenant_id}/reset-admin`
- `GET /api/v1/platform/configuracoes`
- `POST /api/v1/platform/configuracoes`
- `GET /api/v1/platform/suporte`
- `POST /api/v1/platform/suporte`
- `GET /api/v1/platform/auditoria`
