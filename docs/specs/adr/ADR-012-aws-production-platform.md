# ADR-012 — AWS como plataforma integral de produção

**Status:** Aceito

**Data da decisão:** 11/08/2026

**Atualização de implementação:** 12/08/2026

## Contexto

O GabFlow possui frontend React, API Flask, workers contínuos, PostgreSQL com PostGIS e
pgvector, processamento isolado de documentos, ClamAV, armazenamento de anexos, RAG e
cargas de IA que não se ajustam integralmente a um runtime serverless de curta duração.

A plataforma precisa oferecer isolamento entre ambientes e tenants, execução contínua de
workers, armazenamento durável, gestão de segredos, trilha de auditoria, backup, recuperação,
observabilidade e evolução gradual para alta disponibilidade. A solução também precisa
preservar o monólito modular e a outbox existentes enquanto o produto valida o piloto.

Foram consideradas três alternativas:

1. Vercel para toda a aplicação, com serviços externos para banco, workers e IA;
2. Vercel para o frontend e AWS para o backend;
3. AWS para toda a plataforma de produção.

A primeira alternativa exigiria refatoração imediata de workers, parser, scanner, scheduler,
armazenamento e IA. A segunda reduziria o controle centralizado de identidade, observabilidade,
custos e resposta a incidentes. A terceira possui maior configuração inicial, mas acomoda a
arquitetura atual e concentra os controles operacionais no mesmo provedor.

## Decisão

A AWS será a plataforma oficial e integral dos ambientes de `staging` e `production` do
GabFlow. A região primária será `sa-east-1`, salvo revisão formal motivada por disponibilidade
de serviço, requisito regulatório ou análise de continuidade.

Infraestrutura será criada por Terraform e não por configuração manual como fonte de verdade.
Alterações emergenciais no console deverão ser reproduzidas no código ou revertidas.

O domínio `gabflow.app` já estava delegado ao Cloudflare quando o staging foi implantado. A
autoridade DNS existente será preservada nesta fase; certificados continuam no ACM e o ALB
continua sendo a origem AWS. Registros usados na validação ACM devem ser DNS-only e gerenciados
por processo auditado. Migrar a zona para Route 53 exige uma decisão operacional própria e não é
pré-requisito do piloto.

### Topologia alvo

| Responsabilidade | Serviço AWS decidido |
| --- | --- |
| DNS | Cloudflare para `gabflow.app`; Route 53 permanece opção para zonas futuras controladas pela AWS |
| Certificados TLS | ACM |
| CDN e entrega do frontend | CloudFront |
| Frontend React | bucket S3 privado, acessível somente pelo CloudFront |
| Proteção HTTP | AWS WAF associado ao CloudFront e/ou ALB |
| Entrada da API | Application Load Balancer |
| API Flask | ECS, preferencialmente Fargate |
| Workers e scheduler | ECS como serviços separados, sem scale-to-zero |
| Imagens de contêiner | ECR com scan e política de retenção |
| PostgreSQL/PostGIS/pgvector | RDS for PostgreSQL |
| Anexos, evidências, áudios, relatórios e datasets | S3 com criptografia e lifecycle |
| Segredos da aplicação e integrações | AWS Secrets Manager com KMS |
| Logs, métricas e alarmes | CloudWatch Logs, Metrics e Alarms |
| Auditoria da conta e APIs AWS | CloudTrail |
| Backups gerenciados | AWS Backup e snapshots do RDS |
| Notificações operacionais | SNS |
| IA local e cargas incompatíveis com Fargate | EC2 dedicada, inicialmente CPU |

O parser continuará sem acesso de rede e sem segredos. No ECS, API e parser poderão compartilhar
volume efêmero e socket somente dentro da mesma task enquanto o contrato isolado atual for
preservado. O scanner ClamAV será um sidecar ou serviço privado sem porta pública.

O Ollama, Whisper e modelos locais não serão executados em Lambda nem no frontend. Eles ficarão
em instância EC2 privada dedicada ou serão substituídos por adapter externo aprovado. GPU será
ativada somente após medição de carga e aprovação de custo.

### Banco de dados

- `staging` pode usar RDS Single-AZ;
- `production` comercial deve usar Multi-AZ antes da ampliação do piloto;
- conexão exige TLS e security group restrito aos workloads autorizados;
- roles distintas de migration, API, worker e backup permanecem obrigatórias;
- backups automáticos, point-in-time recovery e restauração ensaiada são gates de produção;
- nenhuma task de aplicação recebe credencial administrativa do banco.

### Armazenamento de objetos

Volumes locais do Docker Compose não são armazenamento de produção. Antes do go-live, anexos,
RAG, evidências, áudios, relatórios e datasets deverão usar adapters S3 tenant-scoped.

Buckets serão privados, com bloqueio de acesso público, versionamento quando aplicável,
criptografia SSE-KMS, lifecycle e acesso por IAM. Downloads externos usarão URLs assinadas e
curtas. O frontend será publicado em bucket distinto dos objetos operacionais.

### Segredos e criptografia

AWS Secrets Manager é o cofre oficial. O KMS protegerá os segredos e os objetos que exigirem
chave gerenciada pelo GabFlow. Segredos serão separados por ambiente e finalidade.

Para WhatsApp, o padrão de referência será:

```text
gabflow/{environment}/whatsapp/{tenant_id}/{integration_id}
```

O valor conterá o token e o PIN de verificação em duas etapas. O PostgreSQL guardará somente o
ARN ou identificador opaco retornado pelo Secrets Manager.

Permissões mínimas:

- API de onboarding: criar e atualizar apenas segredos WhatsApp no ambiente atual;
- worker de mensageria: ler somente os segredos necessários ao envio;
- rotina de offboarding: revogar e programar exclusão;
- migration e frontend: nenhum acesso aos segredos WhatsApp;
- operadores humanos: nenhum acesso rotineiro ao valor dos segredos.

Credenciais estáticas de usuário AWS são proibidas no deploy. GitHub Actions usará OIDC para
assumir roles temporárias. ECS usará task roles distintas por serviço.

### Rede

- ALB e CloudFront são as superfícies públicas planejadas;
- ECS, RDS, EC2 de IA e serviços auxiliares ficam em subnets privadas;
- security groups permitem somente fluxos explicitamente necessários;
- acesso administrativo ocorre por mecanismos auditáveis, sem SSH público permanente;
- VPC endpoints serão usados para S3, ECR, CloudWatch, Secrets Manager e serviços compatíveis;
- saída para Meta e outros provedores externos passa por egress controlado;
- `staging` e `production` não compartilham VPC, banco, buckets, chaves ou segredos.

### Ambientes e contas

No mínimo, a conta de produção será separada da conta não produtiva. `development` permanece
local e sintético; `staging` reproduz os serviços críticos sem dados pessoais reais; `production`
possui recursos, chaves e permissões próprios.

Promotion entre ambientes ocorre por imagem imutável identificada pelo digest do ECR. A mesma
imagem aprovada em `staging` será promovida para `production`, alterando apenas configuração e
referências de segredos.

Na implantação inicial de 12/08/2026 a organização possuía somente uma conta. O staging foi
isolado nessa conta por VPC, IAM, KMS, state, banco e namespaces. Essa exceção é temporária:
produção continua proibida nessa mesma conta e exige conta própria antes de qualquer go-live.

### Estado implementado do staging em 12/08/2026

- state remoto S3/KMS e lockfile nativo;
- GitHub OIDC com roles separadas para plan e apply;
- VPC em duas AZs, endpoints privados, NAT e Flow Logs;
- ALB e WAF públicos; ECS Fargate, RDS e EFS privados;
- ECR imutável para backend e web;
- SQS FIFO/DLQ e CloudWatch para recebimento WhatsApp;
- Secrets Manager/KMS com configuração carregada fora do Terraform;
- roles PostgreSQL segregadas e migration executadas por tasks one-shot;
- API e workers estáveis;
- certificado ACM solicitado para `staging.gabflow.app`, aguardando validação Cloudflare.

O registro auditável está em
[`AWS-staging-deployment-2026-08-12.md`](../../implementation/AWS-staging-deployment-2026-08-12.md).

### Observabilidade e continuidade

- logs estruturados não conterão tokens, PINs, payloads brutos ou conteúdo pessoal desnecessário;
- alarmes cobrirão disponibilidade da API, erros 5xx, fila/outbox, DLQ futura, falha de worker,
  CPU/memória, armazenamento, conexões RDS, backup e segredos inválidos;
- CloudTrail deverá estar ativo e protegido contra alteração pela aplicação;
- RPO de até 15 minutos e RTO de até 4 horas permanecem metas mínimas;
- restauração do RDS e dos objetos será testada antes do piloto e periodicamente;
- incidentes, rollback e perda de credencial terão runbooks executáveis.

### FinOps

Todos os recursos terão tags de `environment`, `service`, `owner`, `cost-center` e `managed-by`.
AWS Budgets e alertas serão configurados antes do primeiro deploy. Recursos caros — Multi-AZ,
NAT redundante, GPU, retenção extensa e réplicas — serão ativados por gate explícito, sem reduzir
os controles mínimos de segurança, backup ou isolamento.

## Estratégia de implantação

1. criar organização/contas, state remoto e roles do Terraform;
2. criar rede, KMS, Secrets Manager, ECR, logs e budgets;
3. criar S3 e adapters de armazenamento;
4. criar RDS e validar PostGIS, pgvector, roles e migrations;
5. publicar frontend em S3/CloudFront;
6. publicar API e workers no ECS;
7. adicionar parser, ClamAV, serviços auxiliares e IA em rede privada;
8. configurar observabilidade, backup, restore e runbooks;
9. homologar em `staging` com dados sintéticos;
10. liberar `production` por allowlist e piloto controlado.

O Docker Compose continua sendo o ambiente local de desenvolvimento, mas não representa a
topologia final de produção.

## Gates antes do primeiro go-live

- Terraform revisado, aplicado por CI e sem drift não explicado;
- IAM de menor privilégio e testes negativos entre API, worker e migration;
- nenhum volume local usado como fonte durável;
- restore do RDS e de objetos comprovado;
- segredos lidos somente pelas task roles autorizadas;
- WAF, TLS, headers e cookies seguros validados;
- logs e tracing sem conteúdo sensível;
- alarmes e runbooks exercitados;
- orçamento e alertas de custo configurados;
- inventário de subprocessadores, DPA e avaliação LGPD atualizados;
- plano de rollback testado em `staging`.

## Consequências

### Positivas

- menor refatoração da aplicação atual;
- workers, scanner, parser e IA podem operar continuamente;
- identidade, segredos, auditoria, backup e observabilidade ficam integrados;
- crescimento para Multi-AZ e GPU ocorre sem mudar o provedor principal;
- infraestrutura reproduzível e auditável por código.

### Negativas

- custo-base superior a um frontend puramente serverless;
- Terraform, IAM, rede e ECS aumentam a complexidade operacional inicial;
- `sa-east-1` pode ter preços superiores a regiões dos Estados Unidos;
- serviços gerenciados criam dependência relevante da AWS;
- IA local continua sendo o componente de custo mais variável.

### Riscos e mitigação

| Risco | Mitigação |
| --- | --- |
| crescimento inesperado de custos | Budgets, tags, alarmes, limites e revisão FinOps mensal |
| permissões IAM amplas | task roles separadas, policies por prefixo/ARN e testes negativos |
| indisponibilidade regional | backups restauráveis e revisão futura de DR multi-região |
| dependência do provedor | adapters para storage, segredos e IA; dados em formatos portáveis |
| perda de objetos ou banco | versionamento, PITR, AWS Backup e exercícios de restore |
| vazamento de segredos em logs | redaction, testes automatizados e proibição de payload bruto |

## Decisões adiadas

- uso de GPU e classe exata da instância de IA;
- DR ativo em segunda região;
- adoção de SQS além da outbox transacional;
- OpenSearch dedicado para busca;
- ElastiCache para cache e coordenação;
- EKS; ECS permanece a escolha inicial;
- unificação de billing da Meta com a assinatura GabFlow.

Essas decisões exigem métricas reais e ADR próprio quando alterarem custo, segurança ou
fronteiras de responsabilidade.
