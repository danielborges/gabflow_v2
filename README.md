# GabFlow

Plataforma multi-tenant para gestão de atendimento e atuação de gabinetes
parlamentares.

## Stack

- React 19 + Vite no frontend;
- Python 3.12 + Flask no backend;
- PostgreSQL 17;
- Docker Compose para execução local;
- Ollama com modelo local para triagem assistida;
- Sentry no frontend e backend;
- JWT em cookie `HttpOnly`, proteção CSRF, RBAC, Argon2 e auditoria.

## Recursos implementados

- solicitações, interações, histórico e outbox transacional;
- cidadãos e organizações com contatos, consentimentos e base legal;
- categorias e SLA parametrizáveis;
- responsáveis, tarefas e notificações internas;
- agrupamento de duplicidades sem perda de histórico;
- anexos isolados por tenant, validados e acessados por URL assinada;
- templates, retornos agendados e envio transacional de e-mail pelo Resend.

## Executar com Docker

1. Copie `.env.example` para `.env`.
2. Substitua todas as credenciais de exemplo por valores fortes.
3. Execute:

```powershell
docker compose up --build
```

O aplicativo ficará disponível na porta definida por `WEB_PORT` (por padrão,
`http://localhost:8080`). O tenant e o usuário iniciais são definidos em `.env`;
a senha nunca possui valor padrão no código.

Na primeira inicialização, o serviço `ollama-init` baixa o modelo configurado em
`AI_TRIAGE_MODEL`. O download fica persistido no volume `ollama_data`; as próximas
inicializações reutilizam o modelo local.

Para habilitar e-mails, verifique um domínio no Resend e configure
`RESEND_API_KEY` e `RESEND_FROM_EMAIL` no `.env`. A chave deve possuir somente
permissão de envio e nunca deve ser exposta no frontend ou versionada.

## Desenvolvimento local

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
flask --app wsgi:app db upgrade
flask --app wsgi:app run
```

Frontend:

```powershell
cd frontend
pnpm install
pnpm run dev
```

## Qualidade

```powershell
cd backend
ruff check .
pytest --cov=app

cd ..\frontend
pnpm run lint
pnpm test
pnpm run build
```

Testes de integração com PostgreSQL exigem um banco descartável cujo nome termine em
`_test` ou `_ci`. A suíte recria o schema público antes de aplicar as migrations:

```powershell
cd backend
$env:POSTGRES_TEST_DATABASE_URL="postgresql+psycopg://gabflow:senha@localhost:5432/gabflow_test"
pytest -m postgres tests/postgres
```

## Worker e scheduler

O serviço `worker` do Docker Compose processa o outbox transacional, aplica retentativas
com backoff exponencial e gera lembretes de retornos agendados. Para executar apenas um
ciclo manualmente:

```powershell
cd backend
flask --app wsgi:app worker --once
```

## Segurança operacional

Em produção, habilite TLS no proxy, configure `COOKIE_SECURE=true`, use um backend
compartilhado para rate limiting e armazene segredos em um cofre. O Sentry não envia
PII por padrão; configure `SENTRY_DSN` e `VITE_SENTRY_DSN` somente no deploy.
Conecte também o pipeline de anexos a um scanner antimalware dedicado.
