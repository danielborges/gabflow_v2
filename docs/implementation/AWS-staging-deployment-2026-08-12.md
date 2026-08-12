# Implantação do staging AWS - 12/08/2026

## Resultado executivo

O ambiente de `staging` do GabFlow foi provisionado e ativado na AWS, na região
`sa-east-1`, por Terraform. A aplicação web, API e workers estão em execução no ECS
Fargate, o PostgreSQL está disponível no RDS e os testes externos de página e prontidão
retornaram HTTP 200.

A implantação foi executada com a sessão temporária do IAM Identity Center do operador
`daniel.admin`, assumindo a role administrativa da plataforma. Nenhuma access key estática foi
criada ou versionada.

O número Meta real continua desconectado. O ambiente está pronto para os testes funcionais de
staging, mas o gate de HTTPS ainda depende da publicação dos registros DNS no Cloudflare.

## Infraestrutura aplicada

| Componente | Estado em 12/08/2026 | Implementação |
| --- | --- | --- |
| State Terraform | Aplicado | S3 privado, versionado, criptografado por KMS e lockfile nativo |
| CI/CD | Preparado | GitHub OIDC e roles distintas para plan e apply |
| Rede | Aplicada | VPC em duas AZs, subnets públicas/privadas, NAT, endpoints e Flow Logs |
| Entrada HTTP | Ativa | ALB público associado ao AWS WAF |
| Aplicação | Estável | ECS Fargate privado, uma task da aplicação em execução |
| Processamento | Estável | ECS Fargate privado, uma task de workers em execução |
| Banco | Disponível | RDS PostgreSQL 17.9, privado, criptografado e Single-AZ |
| Arquivos | Aplicado | EFS criptografado com access points de anexos, RAG e eleitoral |
| Mensageria | Aplicada | SQS FIFO de inbound WhatsApp, DLQ FIFO e alarmes |
| Observabilidade | Aplicada | CloudWatch Logs, dashboards, Container Insights e alarmes |
| Segredos | Aplicado | AWS Secrets Manager com chave KMS gerenciada pelo GabFlow |
| TLS | Em validação | Certificado ACM solicitado para `staging.gabflow.app` |

## Imagens e release

A release ativa utiliza a tag imutável `staging-20260812-efs-fix` nos repositórios ECR:

- backend: digest `sha256:313ce7246f1eaa0ec6ccd5237ab15a7730365136a6c96ec8c04048b22fcf2889`;
- web: digest `sha256:889ceef9fe5e8505fa419cc431827df3e95f8e308c8ba138ab8b4a81abc386b4`.

As revisões ativas no fechamento da implantação eram:

- `gabflow-staging-app:4`;
- `gabflow-staging-worker:4`;
- `gabflow-staging-migration:4`;
- `gabflow-staging-database-bootstrap:3`.

## Bootstrap seguro do banco

O secret `gabflow/staging/application/config` foi preenchido por processo operacional usando
`asm-exec`. A credencial administrativa gerenciada pelo RDS foi resolvida somente no processo
filho e não entrou no contexto, terminal, Terraform state ou repositório.

O secret da aplicação contém referências independentes para API, worker, backup e migration,
além das chaves criptográficas e do token de métricas exigidos pelo runtime. Os valores não são
documentados nem recuperados por operadores ou agentes.

Uma task Fargate one-shot criou e validou as roles PostgreSQL segregadas:

- `gabflow_app`;
- `gabflow_worker`;
- `gabflow_backup`;
- credencial administrativa do RDS reservada à migration/bootstrap.

API, worker e backup são validados sem `SUPERUSER`, criação de banco/roles, replicação ou
`BYPASSRLS`. Depois do bootstrap, a migration Alembic foi executada por task one-shot e terminou
com código de saída 0.

## Correções encontradas durante a implantação

### Administração de roles no RDS

O administrador gerenciado pelo RDS não é um superusuário PostgreSQL pleno e não pode repetir
atributos de superusuário em `ALTER ROLE`. O bootstrap foi tornado compatível com o RDS e passou
a validar os atributos proibidos após criar ou atualizar cada role.

### Identidade POSIX no EFS

Os access points do EFS impõem a própria identidade POSIX e rejeitam `chown` dentro do volume.
Os entrypoints da API e dos workers passaram a tolerar essa restrição, preservando o ajuste de
proprietário em volumes locais onde a operação é permitida.

## Evidências de validação

- bootstrap de roles: código de saída 0;
- migration one-shot: código de saída 0;
- serviço `gabflow-staging-app`: `ACTIVE`, desired 1, running 1, rollout concluído;
- serviço `gabflow-staging-worker`: `ACTIVE`, desired 1, running 1, rollout concluído;
- `GET /api/v1/ready`: HTTP 200;
- `GET /`: HTTP 200;
- RDS: `available`, armazenamento criptografado e sem acesso público;
- Terraform após a implantação: `No changes`.

## Domínio e HTTPS

O domínio público adotado para homologação é `staging.gabflow.app`. O domínio raiz
`gabflow.app` está delegado ao Cloudflare, portanto a autoridade DNS não está no Route 53 desta
conta.

O certificado ACM foi solicitado em `sa-east-1` por Terraform. A ativação final de HTTPS segue
um fluxo em duas fases:

1. publicar no Cloudflare o CNAME de validação fornecido pelo ACM;
2. publicar `staging.gabflow.app` como CNAME DNS-only para o ALB;
3. aguardar o certificado atingir `ISSUED`;
4. aplicar Terraform com `enable_https=true`;
5. validar listener TLS 1.2/1.3, redirecionamento HTTP 301, cookies seguros e health check.

Enquanto esses registros não forem publicados, o listener HTTP continua disponível apenas para
homologação técnica e não deve receber credenciais reais nem o número Meta.

## Gates restantes antes do número Meta

1. concluir DNS, emissão ACM e HTTPS;
2. configurar proteção e aprovadores do GitHub Environment `staging`;
3. exercitar backup e restore do RDS/EFS na AWS;
4. executar testes negativos de IAM e isolamento multi-tenant no runtime AWS;
5. validar DLQ, replay, carga e alarmes com tráfego sintético;
6. executar smoke funcional de login, solicitações, agenda, fiscalização, relatórios e canais;
7. configurar o aplicativo e número Meta de homologação;
8. treinar o gabinete piloto e ensaiar rollback/desconexão.
