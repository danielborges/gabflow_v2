# GabFlow — Integração WhatsApp Business Platform

Especificação de referência para implementar atendimento automatizado e humano por WhatsApp em ambiente SaaS multi-tenant.

## Decisões centrais

- Um único aplicativo Meta do GabFlow, aprovado como **Tech Provider**.
- Uma WABA e um número institucional pertencentes a cada gabinete.
- Onboarding self-service por **Embedded Signup**.
- Cloud API, webhooks e WhatsApp Flows; nenhuma automação por WhatsApp Web.
- Cobrança da Meta diretamente ao gabinete no lançamento.
- Roteamento inicial pelo `phone_number_id`; isolamento obrigatório por `tenant_id`.
- IA nunca decide autorização, identidade, tenant ou transição sensível sem regras determinísticas.
- Atendimento humano pode assumir a conversa a qualquer momento.

## Conteúdo

| Arquivo | Finalidade |
|---|---|
| `01-visao-e-escopo.md` | Objetivos, atores, escopo e jornadas |
| `02-requisitos.md` | Requisitos funcionais, não funcionais e regras |
| `03-arquitetura.md` | Componentes, fluxos, segurança e observabilidade |
| `04-modelo-dados.md` | Entidades, estados, chaves e retenção |
| `05-meta-onboarding.md` | Configuração Meta, Embedded Signup e lifecycle |
| `06-seguranca-lgpd.md` | Controles, consentimento, privacidade e incidentes |
| `07-operacao-rollout.md` | Operação, SLOs, testes e implantação gradual |
| `openapi.yaml` | API administrativa e interna |
| `asyncapi.yaml` | Eventos internos e webhooks normalizados |
| `features/whatsapp.feature` | Cenários Gherkin de aceite |
| `adrs/` | Decisões arquiteturais |

## Critério de pronto do módulo

O módulo só pode entrar em produção quando: App Review e permissões estiverem aprovados; assinatura e deduplicação de webhooks estiverem testadas; isolamento entre tenants tiver teste automatizado negativo; opt-in/opt-out e handoff humano estiverem funcionais; Flows estiverem versionados; logs não contiverem conteúdo sensível; e houver piloto controlado com ao menos um gabinete.

## Estado de implementação em 12/08/2026

Os incrementos 0 a 8 foram implementados e documentados em `docs/implementation`. O staging AWS
foi aplicado com recebimento SQS/DLQ, cofre Secrets Manager/KMS, ECS, RDS e observabilidade. A
conexão Meta real continua bloqueada até a conclusão de HTTPS em `staging.gabflow.app` e dos
demais gates do piloto. Consulte
[`AWS-staging-deployment-2026-08-12.md`](../implementation/AWS-staging-deployment-2026-08-12.md).

## Referências oficiais

- Meta Embedded Signup: https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/overview
- WhatsApp Flows: https://developers.facebook.com/documentation/business-messaging/whatsapp/flows
- Tech Providers: https://developers.facebook.com/documentation/business-messaging/whatsapp/solution-providers/get-started-for-tech-providers
