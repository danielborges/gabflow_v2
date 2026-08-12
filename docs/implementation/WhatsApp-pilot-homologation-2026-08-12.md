# Homologação do piloto WhatsApp - 12/08/2026

## Resultado executivo

O GabFlow foi atualizado localmente até a migration `b7d8e9f0a1c2`, reimplantado em Docker e validado com PostgreSQL real. A aplicação, o banco, o parser e os serviços de apoio estão saudáveis; o cockpit operacional respondeu com semáforo `GOOD`.

O piloto real ainda não foi iniciado. A plataforma AWS de staging foi aplicada no mesmo dia e
está saudável. Permanecem pendentes os gates de HTTPS, configuração Meta, testes E2E com número
de homologação, treinamento do gabinete e validação de rollback.

## Evidências concluídas

| Controle | Resultado | Evidência |
| --- | --- | --- |
| Backup pré-homologação | Aprovado | `output/homologation/gabflow-pre-homolog-20260812-183201.dump`, 886.849.956 bytes |
| Restore isolado | Aprovado | restore em banco temporário, leitura da versão Alembic e 117 tabelas |
| Migration sobre base existente | Aprovado | banco atualizado de `a5d9f1b3c7e2` para `b7d8e9f0a1c2` |
| Migration PostgreSQL do zero | Aprovado | banco descartável `gabflow_whatsapp_ci` chegou ao head e confirmou a restrição composta |
| Serviços locais | Aprovado | API, PostgreSQL, parser, ClamAV, Ollama e SearXNG saudáveis; web e workers em execução |
| Smoke HTTP | Aprovado | `/api/v1/health`, `/api/v1/ready`, aplicação web e login administrativo retornaram sucesso |
| Cockpit do piloto | Aprovado | 8 gates carregados, saúde operacional `GOOD`, início corretamente bloqueado enquanto incompleto |
| Testes WhatsApp/operacionais | Aprovado | 49 testes automatizados aprovados |

## Defeito encontrado e corrigido

A migration `f5b6c7d8e9a0` referenciava `whatsapp_messages(tenant_id, id)`, mas a migration `c2e3f4a5b6d7` não criava a restrição única composta exigida pelo PostgreSQL. O erro não aparecia nos testes SQLite.

Foi adicionada a restrição `uq_whatsapp_messages_tenant_id_id` ao modelo e à migration de origem, além de uma asserção no teste PostgreSQL. A cadeia foi executada novamente sobre a base existente e sobre um banco vazio, com sucesso.

## Evidências registradas no cockpit

- `MULTITENANT_NEGATIVE_TESTS`: aprovado com referência à suíte automatizada;
- `BACKUP_RESTORE`: aprovado com referência ao backup e restore isolado;
- `RUNBOOKS_INCIDENTS`: aprovado com referência ao runbook versionado.

Os demais gates continuam pendentes, evitando uma aprovação artificial de controles ainda não exercitados.

## Bloqueios externos

1. O certificado ACM de `staging.gabflow.app` aguarda validação DNS no Cloudflare; HTTPS ainda
   não está ativo.
2. Aplicativo Meta, número de homologação, Embedded Signup, Flows e templates ainda não foram
   conectados ao staging.
3. Os testes de backup/restore, IAM negativo, carga, DLQ/replay e rollback ainda precisam ser
   exercitados no runtime AWS.
4. Não há gabinete/equipe formalmente designados para treinamento e piloto real.

## Evolução AWS concluída no mesmo dia

- AWS CLI e Terraform instalados e autenticados via IAM Identity Center como `daniel.admin`;
- backend remoto, OIDC e roles de plan/apply aplicados;
- ECR, ECS/Fargate, ALB/WAF, RDS, EFS, SQS/DLQ e CloudWatch implantados;
- secret de aplicação preenchido sem exposição dos valores;
- bootstrap das roles e migration executados com código de saída 0;
- API, web e workers estabilizados e validados por HTTP 200;
- certificado ACM solicitado para o domínio de staging.

Detalhes e evidências:
[`AWS-staging-deployment-2026-08-12.md`](AWS-staging-deployment-2026-08-12.md).

## Próximo gate objetivo

Antes do piloto real:

1. publicar os CNAMEs no Cloudflare e ativar HTTPS no ALB;
2. executar smoke funcional completo no domínio seguro;
3. configurar Meta pelo cofre e conectar o número de homologação;
4. executar testes E2E, carga, DLQ/replay, backup/restore e IAM negativo;
5. realizar treinamento, rollback e desconexão simulados;
6. aprovar os gates restantes no cockpit.
