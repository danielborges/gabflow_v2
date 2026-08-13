# Fundação AWS com Terraform

Esta árvore implementa a fundação definida no
[`ADR-012`](../../docs/specs/adr/ADR-012-aws-production-platform.md). Ela não contém credenciais,
IDs de conta, e-mails reais ou valores de segredos.

## Camadas

| Camada | Diretório | State | Responsabilidade |
| --- | --- | --- | --- |
| Backend de management | `management-backend/` | local apenas no bootstrap, depois S3 | bucket/KMS do state da conta de gerenciamento |
| Organização | `organization/` | S3 remoto na conta de gerenciamento | OUs e contas de `staging` e `production` |
| Bootstrap | `bootstrap/` | local no primeiro uso | bucket/KMS do state e OIDC do GitHub em cada conta |
| Ambiente | `environments/<environment>/` | S3 remoto do próprio ambiente | VPC, subnets, NAT, endpoints, KMS, secret e task roles |

Produção e não produção devem permanecer em contas AWS diferentes. Se a organização ou as
contas já existirem, importe os recursos antes de aplicar; não tente recriá-los.

## Pré-requisitos

- Terraform `>= 1.10, < 2.0`;
- AWS CLI autenticado temporariamente, sem access key persistida no repositório;
- uma conta de gerenciamento do AWS Organizations;
- e-mails exclusivos para novas contas, caso o vending seja habilitado;
- repositório GitHub informado no formato `owner/repository`.

## 1. Backend remoto da conta de gerenciamento

O backend da conta de gerenciamento é um bootstrap isolado. Ele cria somente o bucket S3
versionado e privado, a chave KMS e as configurações de proteção do state:

```powershell
terraform -chdir=infra/terraform/management-backend init
terraform -chdir=infra/terraform/management-backend plan -var="state_bucket_name=gabflow-management-ACCOUNT_ID-tfstate" -out=management-backend.tfplan
terraform -chdir=infra/terraform/management-backend apply management-backend.tfplan
```

Depois do primeiro apply, copie `backend.hcl.example` para `backend.hcl`, preencha o bucket e a
chave KMS retornados nos outputs e migre o próprio state do bootstrap:

```powershell
terraform -chdir=infra/terraform/management-backend init -migrate-state -backend-config=backend.hcl
```

`backend.hcl`, states locais e planos são ignorados pelo Git.

## 2. Contas e ambientes

Copie `organization/terraform.tfvars.example` para `organization/terraform.tfvars`, preencha os
e-mails e execute:

```powershell
terraform -chdir=infra/terraform/organization init -migrate-state -backend-config=backend.hcl
terraform -chdir=infra/terraform/organization plan -out=organization.tfplan
terraform -chdir=infra/terraform/organization apply organization.tfplan
```

O padrão `create_accounts = false` impede criação acidental. Revise o plano antes de alterar
para `true`. A criação de contas é assíncrona e pode levar vários minutos.

## 3. Bootstrap por conta

Assuma primeiro a conta de destino. Execute o bootstrap uma vez para `staging` e outra para
`production`, usando nomes diferentes e globalmente únicos para o bucket:

```powershell
terraform -chdir=infra/terraform/bootstrap init
terraform -chdir=infra/terraform/bootstrap workspace new staging
terraform -chdir=infra/terraform/bootstrap plan -var-file=staging.tfvars -out=bootstrap.tfplan
terraform -chdir=infra/terraform/bootstrap apply bootstrap.tfplan
```

O bootstrap cria state S3 versionado, criptografado e bloqueado por lockfile nativo, além do
provedor OIDC e roles GitHub de leitura/plano e aplicação. O state local do bootstrap deve ser
guardado em local restrito até uma decisão específica para sua custódia; ele nunca deve ir para
o Git.

## 4. Fundação do ambiente

Copie os exemplos de backend e variáveis, substitua os placeholders e inicialize:

```powershell
terraform -chdir=infra/terraform/environments/staging init -backend-config=backend.hcl
terraform -chdir=infra/terraform/environments/staging plan -out=staging.tfplan
terraform -chdir=infra/terraform/environments/staging apply staging.tfplan
```

Repita em `production`. Cada ambiente cria:

- VPC com duas zonas de disponibilidade, subnets públicas e privadas;
- Internet Gateway, NAT e rotas privadas;
- VPC endpoints para S3, ECR, CloudWatch Logs, KMS, Secrets Manager, SQS e STS;
- flow logs e default security group sem regras implícitas;
- chave KMS e alias próprios;
- secret de configuração sem valor inicial;
- task roles distintas para API, worker e migrations;
- prefixo dinâmico `gabflow/<environment>/whatsapp/*` para onboarding Meta.

Os valores de segredos devem ser gravados pela aplicação ou por processo operacional seguro,
nunca por `*.tfvars` ou `aws_secretsmanager_secret_version` no Terraform.

Para o WhatsApp, configure os containers a partir do output
`whatsapp_runtime_configuration`. A API usa `CreateSecret` e `DeleteSecret` somente no prefixo
do ambiente, com KMS e tags obrigatorias. O worker possui `GetSecretValue`; a API nao possui
permissao para reler tokens apos o onboarding. Exclusao imediata e negada e o adapter usa uma
janela de recuperacao de 7 a 30 dias.

O modulo `messaging` cria a fila FIFO de recebimento WhatsApp, a DLQ FIFO, criptografia KMS,
redrive restrito a fila de origem e alarmes de profundidade da DLQ e idade da mensagem. O output
`whatsapp_runtime_configuration` fornece `inbound_queue_backend=aws-sqs` e a URL da fila para as
tasks ECS, sem credenciais estaticas.

O bootstrap autoriza os subjects OIDC nominal e imutavel do repositorio. O formato imutavel
`owner@owner_id/repo@repo_id`, adotado pelo GitHub para novos repositorios, deve permanecer
restrito aos IDs declarados em `github_repository_immutable`; nao use wildcard nessa condicao.

O ambiente `staging` tambem inclui o modulo `runtime`: ECR imutavel, ECS Fargate, ALB, WAF,
RDS PostgreSQL, EFS, logs, alarmes e uma task de migration one-shot. Por seguranca,
`enable_services=false` e o padrao. A ativacao acontece somente depois da publicacao das imagens,
configuracao externa do secret de aplicacao e sucesso da migration. Consulte
[`AWS-STAGING-RUNTIME.md`](../../docs/implementation/AWS-STAGING-RUNTIME.md).

### Domínio e HTTPS do staging

O certificado pode ser externo por `certificate_arn` ou gerenciado neste ambiente. Para o fluxo
gerenciado, use duas fases porque a zona `gabflow.app` está no Cloudflare:

```powershell
terraform -chdir=infra/terraform/environments/staging plan `
  -var="domain_name=staging.gabflow.app" `
  -var="enable_https=false" `
  -out=staging-acm-request.tfplan
terraform -chdir=infra/terraform/environments/staging apply staging-acm-request.tfplan
```

Publique no Cloudflare o output `certificate_dns_validation_records` e um CNAME DNS-only de
`staging.gabflow.app` para `load_balancer_dns_name`. Depois que o ACM estiver `ISSUED`, planeje e
aplique com `enable_https=true`. Essa segunda fase cria o listener 443, troca o listener 80 para
redirect HTTP 301 e registra `COOKIE_SECURE=true` na nova revisão da task da aplicação.

Não use `enable_https=true` antes de a validação DNS estar publicada: o recurso de validação ACM
aguardará a emissão do certificado.

## Gates

Antes de aplicar em produção:

1. confirmar identidade com `aws sts get-caller-identity`;
2. revisar o plano e a conta indicada no output `account_id`;
3. proteger os GitHub Environments `staging` e `production` com reviewers;
4. restringir a branch de produção para `main`;
5. executar teste negativo entre task roles;
6. confirmar versionamento, criptografia e recuperação do state;
7. executar `terraform fmt -check -recursive infra/terraform` e o workflow de validação.
