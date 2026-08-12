# Fundação AWS — Terraform

**Status em 12/08/2026:** bootstrap e runtime de `staging` aplicados na conta AWS existente;
Organização multi-account e `production` permanecem pendentes.

**Decisão:** [ADR-012](../specs/adr/ADR-012-aws-production-platform.md)

## Escopo entregue

- AWS Organizations com OUs `NonProduction` e `Production`;
- vending protegido das contas `staging` e `production`;
- backend da conta de gerenciamento em S3, versionado, privado e criptografado com KMS;
- state S3 por conta, versionado, com lockfile e KMS;
- OIDC do GitHub sem credenciais estáticas;
- roles separadas para plano e aplicação;
- VPC por ambiente, duas AZs, subnets públicas/privadas, NAT e endpoints privados;
- VPC Flow Logs;
- KMS por ambiente;
- secret de configuração sem valor versionado no Terraform;
- task roles de execução, API, worker e migrations;
- namespace de segredos Meta `gabflow/<environment>/whatsapp/*`;
- validação de formato e schema no GitHub Actions.

## Limites desta etapa

Em 12/08/2026 foi confirmado que a organização possui somente a conta `601914507690`. Para não
bloquear a homologação técnica, `staging` foi isolado por VPC, IAM, KMS, state, banco e prefixos
dentro dessa conta. Essa decisão transitória não substitui o gate arquitetural de uma conta
separada para produção.

O backend remoto da conta de gerenciamento já foi criado. As OUs, contas e fundações dos
ambientes continuam pendentes e exigem decisões e credenciais externas:

| Entrada | Origem | Condição para aplicar |
| --- | --- | --- |
| e-mails exclusivos das contas | responsável financeiro/administrativo | aprovados e sob domínio controlado |
| acesso à management account | administrador AWS | sessão temporária e MFA |
| IDs das contas | output do Organizations ou contas existentes | conferidos antes de cada plan |
| nomes dos buckets de state | plataforma | globalmente únicos |
| proteção dos GitHub Environments | administrador do repositório | reviewers e branch `main` |
| orçamento e contatos de alerta | negócio/FinOps | aprovados antes do primeiro deploy |

O Terraform cria apenas o objeto/metadado do secret de configuração. Valores e tokens não são
incluídos no state. Segredos WhatsApp são criados dinamicamente pelo onboarding, sob o prefixo
autorizado pela task role da API.

## Ordem de execução

1. revisar o plano remoto de `infra/terraform/organization` na management account;
2. aplicar `infra/terraform/organization` somente após aprovação explícita;
3. aguardar e conferir as contas;
4. aplicar `infra/terraform/bootstrap` em cada conta;
5. copiar outputs do bootstrap para `backend.hcl` local;
6. proteger os environments no GitHub;
7. aplicar primeiro `environments/staging`;
8. executar testes de rede, IAM, KMS, secrets e recuperação;
9. aprovar e aplicar `environments/production`.

## Evidências exigidas

- output de `aws sts get-caller-identity` sem credenciais expostas;
- plano salvo e aprovado por segundo revisor;
- state S3 com versionamento e criptografia KMS;
- pull request consegue assumir somente a role de plano, ler o state e operar apenas o lock;
- role de plano não consegue sobrescrever ou excluir o arquivo de state;
- branch/Environment autorizado consegue assumir a role de aplicação;
- API consegue operar somente secrets do próprio namespace;
- worker lê secrets, mas não cria, altera ou exclui;
- migration não acessa secrets;
- staging não acessa KMS, state ou secrets de produção;
- Flow Logs chegam ao CloudWatch;
- lock concorrente do state impede dois applies simultâneos.

## Evolução aplicada em 12/08/2026

Depois da fundação inicial também foram aplicados:

- ECR imutável para backend e web;
- ECS Fargate privado para aplicação e workers;
- ALB público e AWS WAF;
- RDS PostgreSQL privado e criptografado;
- EFS criptografado com access points;
- SQS/DLQ, CloudWatch Logs, dashboards e alarmes;
- tasks one-shot de bootstrap do banco e migration;
- pipeline GitHub Actions com OIDC;
- secret de aplicação preenchido por processo seguro com `asm-exec`;
- certificado ACM solicitado para `staging.gabflow.app`.

O registro completo está em
[`AWS-staging-deployment-2026-08-12.md`](AWS-staging-deployment-2026-08-12.md).

## Próximas fundações

Permanecem pendentes: conta isolada de produção, Budgets, CloudTrail organizacional, AWS Config,
GuardDuty, Security Hub, teste de restore AWS, adapters S3/CloudFront da topologia alvo e a
conclusão de DNS/HTTPS no Cloudflare.
