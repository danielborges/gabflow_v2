# Arquitetura — Contêineres

## Plataforma de produção

A topologia oficial de `staging` e `production` está definida no
[`ADR-012`](../adr/ADR-012-aws-production-platform.md): AWS em `sa-east-1`, infraestrutura
como código em Terraform, frontend privado em S3/CloudFront, API e workers em ECS, banco no
RDS, objetos no S3 e segredos no AWS Secrets Manager. O Docker Compose permanece como ambiente
local e não é a topologia final de produção.

## Topologia ativa de staging

Desde 12/08/2026, o staging executa:

- task `app` no ECS Fargate, reunindo web, API, parser isolado e ClamAV;
- task `worker` no ECS Fargate, reunindo workers, parser e ClamAV;
- tasks one-shot distintas para bootstrap das roles PostgreSQL e migration Alembic;
- RDS PostgreSQL privado e EFS criptografado com access points separados;
- ALB público associado ao WAF, com health check em `/api/v1/ready`;
- SQS FIFO/DLQ para inbound WhatsApp e CloudWatch para logs, métricas e alarmes.

Tasks não recebem IP público. Imagens são publicadas no ECR com tags imutáveis e promovidas
somente após bootstrap e migration bem-sucedidos. O domínio previsto é
`staging.gabflow.app`; o listener HTTPS depende da emissão ACM validada no Cloudflare.

Os access points do EFS impõem a identidade POSIX do volume. Entry points não devem assumir que
`chown` é permitido em um mount EFS.

## Aplicação Web

- gestão de atendimento;
- dashboards;
- relatórios operacionais e de insights com exportação executiva;
- agenda institucional diária, semanal e mensal;
- fiscalização de campo, pendências e gestão de evidências;
- administração;
- revisão de IA;
- produção legislativa.

## API Backend

Responsável por:
- autenticação e autorização;
- regras de negócio;
- APIs;
- auditoria;
- composição síncrona dos PDFs executivo semanal e de relatórios por período;
- orquestração.

## Worker Assíncrono

Responsável por:
- transcrição;
- OCR;
- classificação;
- geocodificação;
- notificações;
- indexação;
- projeção governada das entidades dos módulos;
- reconciliação, expiração e purge do conhecimento operacional;
- validação, compilação e reavaliação dos sinais de feedback;
- geração de relatórios.

## Serviço de IA

Camada de abstração para:
- provedores de LLM;
- prompts versionados;
- políticas;
- mascaramento;
- avaliação;
- fallback.

## Serviço RAG

Responsável por:
- ingestão global e privada;
- parsing;
- chunking;
- embeddings;
- distribuição e versionamento do catálogo global;
- recuperação federada global + privada;
- registry de projetores e ciclo de vida das fontes operacionais;
- roteamento documental, estruturado e híbrido;
- filtros de tenant, ACL, módulo, jurisdição, vigência e finalidade;
- normalização e reranking;
- citações;
- controle de acesso;
- avaliação e melhoria tenant-scoped por artefatos versionados e reversíveis.

## Scanner ClamAV

- recebe uploads por `INSTREAM`, sem volume de documentos compartilhado;
- mantém a base de assinaturas em volume próprio e atualizável;
- não publica a porta 3310 no host;
- falha ou limite excedido nunca equivalem a arquivo limpo.

## Parser isolado

- não participa da rede do Compose e não recebe segredos ou credenciais;
- monta anexos e RAG somente para leitura e escreve apenas no socket Unix e `/tmp`;
- executa um subprocesso limitado e descartável por documento;
- retorna somente texto, páginas, confiança, contagem e versão do parser.

## Banco Transacional

Decisão:
- PostgreSQL;
- PostGIS para geodados;
- schemas distintos para RAG global e privado;
- row-level security forçado no domínio privado;
- roles separadas para migration, API, worker e backup;
- pgvector para busca vetorial quando adotado.
- full-text search para recuperação lexical;
- read models tenant-scoped para fatos, contagens e indicadores.

No staging, as roles são criadas por tarefa one-shot idempotente. API e worker são validados sem
`SUPERUSER`, `CREATEDB`, `CREATEROLE`, replicação ou `BYPASSRLS`; a credencial administrativa
gerenciada pelo RDS fica restrita ao bootstrap e às migrations.

## Armazenamento de Objetos

- anexos;
- evidências fotográficas e documentais de fiscalização;
- áudios;
- documentos;
- versões;
- relatórios.

Em produção, esses objetos usam buckets S3 privados, tenant-scoped, criptografados e com
políticas de lifecycle. Volumes locais não são fonte durável de produção.

## Índice de Busca

- busca textual;
- filtros;
- agregações;
- busca híbrida.

## Barramento de Eventos

- desacoplamento;
- integração;
- processamento assíncrono;
- outbox transacional com payload mínimo e sem conteúdo sensível;
- auditoria operacional.
