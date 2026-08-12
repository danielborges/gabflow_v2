# Plataforma de execucao AWS de staging

**Status em 12/08/2026:** infraestrutura aplicada, API e workers estáveis; certificado ACM
solicitado e validação DNS/HTTPS pendente no Cloudflare.

**Evidência operacional:**
[`AWS-staging-deployment-2026-08-12.md`](AWS-staging-deployment-2026-08-12.md).

## Objetivo

Disponibilizar um ambiente isolado para validar o GabFlow e os incrementos WhatsApp antes de
conectar um numero Meta real. O runtime nasce com a integracao Meta desativada e com os services
ECS desligados por padrao.

## Arquitetura implementada

- imagens imutaveis em dois repositorios ECR, `backend` e `web`, com scan no push e lifecycle;
- ECS Fargate privado para a aplicacao e os workers, sem IP publico;
- ALB publico protegido por AWS WAF e circuit breaker nos deployments;
- PostgreSQL 17 em RDS privado, criptografado, com backup, Performance Insights e protecao contra exclusao;
- EFS criptografado com access points separados para anexos, RAG e dados eleitorais;
- CloudWatch Logs, Container Insights enhanced e alarmes para erros do ALB e espaco do banco;
- migration Alembic executada como tarefa Fargate one-shot antes da ativacao dos services;
- bootstrap das roles PostgreSQL executado como tarefa Fargate one-shot separada;
- GitHub Actions autenticado por OIDC, sem access keys persistentes;
- WhatsApp Platform, Embedded Signup e rollout permanecem desativados no runtime.

A tarefa da aplicacao agrupa web, API, parser e ClamAV. O web encaminha `/api` para a API no
loopback da mesma tarefa. A tarefa de processamento agrupa workers, parser e ClamAV e monta o
mesmo EFS com IAM authorization.

## Bootstrap seguro

O primeiro apply deve usar:

```text
image_tag       = "bootstrap"
enable_services = false
```

Isso cria a infraestrutura, inclusive os repositorios, sem iniciar containers. O secret
`gabflow/staging/application/config` continua sem valor no Terraform. Antes da migration, o
processo operacional autorizado deve preencher externamente as chaves esperadas pelo runtime:

- `database_url_api`
- `database_url_worker`
- `database_url_migration`
- `database_url_backup`
- `secret_key`
- `jwt_secret_key`
- `storage_encryption_master_key`
- `metrics_bearer_token`

Valores, senhas e tokens nao devem ser colocados no GitHub, em `tfvars`, outputs ou logs. A
credencial administrativa do RDS e gerenciada pelo proprio RDS no Secrets Manager e deve ser
usada apenas no bootstrap de roles e URLs de conexao da aplicacao.

## Pipeline

O workflow manual `.github/workflows/deploy-staging.yml`:

1. assume a role de staging via GitHub OIDC;
2. provisiona ou atualiza a infraestrutura com services desligados;
3. publica imagens com tag igual ao commit SHA;
4. registra as novas task definitions;
5. executa e valida a migration one-shot;
6. opcionalmente ativa API e workers;
7. publica a URL no resumo da execucao.

Configure o GitHub Environment `staging` com aprovadores e com estas variables, que nao sao
segredos:

- `AWS_STAGING_REGION`
- `AWS_STAGING_ACCOUNT_ID`
- `AWS_STAGING_APPLY_ROLE_ARN`
- `AWS_STAGING_STATE_BUCKET`
- `AWS_STAGING_STATE_KMS_KEY_ARN`
- `AWS_STAGING_CERTIFICATE_ARN` (opcional ate a configuracao de HTTPS)

Quando o certificado for gerenciado pelo próprio Terraform, use `domain_name` e o gate
`enable_https`. O primeiro apply mantém `enable_https=false`, solicita o ACM e publica o output
`certificate_dns_validation_records`. Depois que o DNS externo validar o certificado, o segundo
apply usa `enable_https=true` para criar o listener 443, redirecionar HTTP e habilitar cookies
seguros.

## Gates antes do numero Meta

1. concluir a validação DNS de `staging.gabflow.app` no Cloudflare e associar o ACM ao ALB;
2. executar smoke tests de login, solicitacoes, agenda, fiscalizacao, relatorios e canais;
3. confirmar alarmes, logs estruturados, backup e restauracao do RDS e EFS;
4. validar DLQ, idempotencia do webhook e teste de carga do recebimento;
5. concluir teste negativo de IAM entre API, worker e migration;
6. revisar WAF, retencao, custos e plano de rollback;
7. somente entao habilitar Embedded Signup e rollout WhatsApp por tenant piloto.

O apply real da AWS e a carga segura das configurações foram executados em 12/08/2026. A
integração Meta permanece desativada. O processo não lê nem documenta valores secretos.
