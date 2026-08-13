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
- agenda institucional nos modos dia, semana e mês, com compromissos editáveis,
  participantes do gabinete e destaque para presença parlamentar;
- agenda executiva semanal exportável em PDF;
- fiscalizações originadas da agenda ou registradas em campo, com pendências por
  participante, vínculo a solicitações e evidências fotográficas/documentais;
- relatórios operacionais e de insights do mandato por período, com indicadores,
  semáforo executivo e exportação em PDF;
- agrupamento de duplicidades sem perda de histórico;
- anexos isolados por tenant, validados e acessados por URL assinada;
- templates, retornos agendados e envio transacional de e-mail pelo Resend;
- RAG privado isolado por tenant e catálogo global distribuído por política;
- recuperação hierárquica com citações e proveniência;
- memória operacional versionada para solicitações, encaminhamentos, minutas,
  tramitações, conteúdo revisado, agenda, fiscalização e memórias temáticas;
- roteamento documental, estruturado e híbrido, com avaliação por tenant.
- canais WhatsApp com onboarding Meta, webhook idempotente, caixa de entrada 2.0, Flows,
  mídia assistida, templates, opt-out, cockpit operacional e gates de piloto;

## Evolução do conhecimento operacional

A incorporação governada de informações dos módulos previstos está implementada.
O alvo não é indexar todas as tabelas: cada módulo fornece projeções governadas,
minimizadas e tenant-scoped. Perguntas quantitativas usam consultas estruturadas;
o RAG permanece responsável por evidências semânticas e documentais.

- Decisão arquitetural: `docs/specs/adr/ADR-008-operational-knowledge-projections.md`
- Implementação:
  `docs/implementation/Release4.6-operational-knowledge-plan.md`

## Feedback e reaprendizado

O GabFlow captura avaliação positiva, negativa ou corrigida em revisões imutáveis,
com taxonomia, julgamento por fonte, minimização, quarentena e moderação
tenant-scoped. O sinal ainda não altera o comportamento do assistente: curadoria,
promoção explícita para o dataset, hard negatives e expectativas de rota/filtros
já estão disponíveis. Artefatos versionados, avaliação contra baseline, ativação e
rollback formam os próximos incrementos. Feedback bruto ou resposta corrigida não
se torna fonte, prompt ou treinamento automático.

- Decisão arquitetural: `docs/specs/adr/ADR-009-controlled-feedback-learning.md`
- Plano de implementação:
  `docs/implementation/Release4.7-controlled-feedback-learning.md`

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

## Fixture local do WhatsApp

Em `development` ou `test`, uma integração sintética pode alimentar o mesmo endpoint global,
validação HMAC, inbox idempotente e worker usados pelo webhook real. Os comandos recusam execução
em `staging` e `production` e nunca substituem uma integração não sintética.

Com a aplicação no Docker, prepare o tenant e injete a primeira mensagem:

```powershell
docker compose exec api flask --app wsgi:app whatsapp-dev-setup --tenant gabinete-demo
docker compose exec api flask --app wsgi:app whatsapp-dev-inject --tenant gabinete-demo
```

Depois, abra **Canais** para testar privacidade, identificação, coleta, protocolo e handoff. Outros
cenários controlados:

```powershell
# Handoff determinístico
docker compose exec api flask --app wsgi:app whatsapp-dev-inject --tenant gabinete-demo --kind handoff

# Opt-out determinístico
docker compose exec api flask --app wsgi:app whatsapp-dev-inject --tenant gabinete-demo --kind opt-out

# Replay: uma aceitação e uma duplicata, sem efeitos duplicados
docker compose exec api flask --app wsgi:app whatsapp-dev-inject --tenant gabinete-demo --message-id wamid.manual.replay-1 --repeat 2

# Deixar o evento na outbox para processar o worker separadamente
docker compose exec api flask --app wsgi:app whatsapp-dev-inject --tenant gabinete-demo --no-process
docker compose exec api flask --app wsgi:app worker --once
```

Use `--sender`, `--sender-name`, `--message` e `--phone-number-id` para variar os dados sintéticos.
O segredo HMAC é efêmero e permanece apenas em memória durante a injeção.

## Segurança operacional

Em produção, habilite TLS no proxy, configure `COOKIE_SECURE=true`, use um backend
compartilhado para rate limiting e armazene segredos em um cofre. O Sentry não envia
PII por padrão; configure `SENTRY_DSN` e `VITE_SENTRY_DSN` somente no deploy.
Conecte também o pipeline de anexos a um scanner antimalware dedicado.

A plataforma integral de produção foi definida como AWS no
[`ADR-012`](docs/specs/adr/ADR-012-aws-production-platform.md). Docker Compose permanece voltado
ao desenvolvimento local; `staging` e `production` usam infraestrutura Terraform, ECS, RDS,
S3, CloudFront, Secrets Manager/KMS e CloudWatch.

A fundação versionada está em [`infra/terraform`](infra/terraform/README.md), com organização de
contas, state remoto, OIDC do GitHub, redes isoladas, KMS e Secrets Manager.

O staging AWS foi implantado em 12/08/2026 com ECR, ECS Fargate, ALB/WAF, RDS, EFS, SQS/DLQ e
CloudWatch. API, web e workers estão estáveis. O certificado ACM de
`staging.gabflow.app` aguarda validação DNS no Cloudflare antes da ativação de HTTPS e da conexão
do número Meta. Consulte o
[`registro da implantação`](docs/implementation/AWS-staging-deployment-2026-08-12.md).
