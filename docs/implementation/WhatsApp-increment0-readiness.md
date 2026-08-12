# WhatsApp Business Platform - Incremento 0

## Objetivo

Preparar o GabFlow para iniciar a integracao oficial com a WhatsApp Business Platform sem
ativar o novo pipeline em producao. Este incremento transforma dependencias externas e
decisoes de arquitetura em gates verificaveis por ambiente e por tenant.

## Decisoes confirmadas

- Cloud API oficial; automacao por WhatsApp Web permanece proibida.
- Um aplicativo Meta do GabFlow como Tech Provider.
- WABA, numero, reputacao e cobranca pertencem a cada gabinete.
- Embedded Signup sera o unico onboarding de producao.
- O webhook futuro sera global e resolvera o tenant pelo `phone_number_id`.
- A outbox e os workers existentes serao reutilizados no pipeline assincrono.
- O rollout sera controlado por kill switch, estagio e allowlist de tenants.
- Segredos reais nao entram em `IntegrationSetting.config`, frontend, logs ou repositorio.

## Configuracao criada

O pipeline novo nasce desabilitado. `WHATSAPP_PLATFORM_ENABLED` e a chave de emergencia;
`WHATSAPP_ROLLOUT_STAGE` aceita `disabled`, `sandbox`, `pilot` e `ga`. Nos estagios
`sandbox` e `pilot`, somente slugs declarados em `WHATSAPP_PILOT_TENANT_SLUGS` ficam
elegiveis.

Em producao, o cofre decidido e o AWS Secrets Manager com KMS, conforme o
[`ADR-012`](../specs/adr/ADR-012-aws-production-platform.md). Declarar o nome do backend nao e
suficiente: o gate somente passa quando `WHATSAPP_SECRET_BACKEND=aws-secrets-manager`, prefixo
e chave KMS estiverem configurados e `WHATSAPP_SECRET_BACKEND_READY=true`, depois de IAM,
gravacao, leitura, revogacao e recuperacao terem sido testados.

O endpoint autenticado abaixo apresenta apenas booleanos e nomes de gates:

```text
GET /api/v1/tenants/{tenantId}/whatsapp/readiness
```

App ID, Configuration ID, App Secret e verify token nunca aparecem na resposta.

## Gates tecnicos para sandbox

- pipeline habilitado;
- estagio de rollout valido e tenant na allowlist;
- App ID e Configuration ID configurados;
- versao da Graph API fixada explicitamente no formato `vNN.0`;
- redirect URI HTTPS;
- App Secret e verify token presentes no backend.

## Gates adicionais para piloto

- Embedded Signup habilitado;
- Business Portfolio verificado;
- Tech Provider aprovado;
- App Review e permissoes aprovados;
- cofre externo de segredos em producao;
- aviso de privacidade, bases legais, DPA e subprocessadores aprovados.

## Registro de pendencias externas

| Gate | Responsavel sugerido | Evidencia esperada | Estado inicial |
| --- | --- | --- | --- |
| Business Verification | Produto/administracao | Portfolio verificado na Meta | Pendente |
| Tech Provider | Produto/engenharia | Aprovacao do programa | Pendente |
| App Review | Produto/engenharia | Permissoes avancadas e screencast aceitos | Pendente |
| AWS Secrets Manager | Plataforma/seguranca | Terraform, KMS, IAM e lifecycle testados | Implementado; apply e prova pendentes |
| Privacidade e bases legais | Juridico/DPO | Aviso versionado e parecer | Pendente |
| DPA e subprocessadores | Juridico/compras | Instrumentos aprovados | Pendente |
| Tenant piloto | Produto/suporte | Gabinete, numero e janela de operacao definidos | Pendente |

## Permissoes a validar no App Review

As colecoes oficiais da Meta atualmente indicam `business_management`,
`whatsapp_business_management` e `whatsapp_business_messaging` para o fluxo completo de
onboarding, gestao e envio. A lista final deve ser confirmada novamente antes da submissao,
usando menor privilegio e demonstrando o caso de uso real no screencast.

## Referencias oficiais verificadas em 2026-08-11

- Embedded Signup: https://www.postman.com/meta/whatsapp-business-platform/documentation/du6gzjv/embedded-signup
- Webhooks: https://www.postman.com/meta/whatsapp-business-platform/folder/lboq68h/webhooks
- Webhook payloads: https://www.postman.com/meta/whatsapp-business-platform/folder/tduohwq/webhook-payload-reference
- Mensagens: https://www.postman.com/meta/whatsapp-business-platform/folder/o48mro7/messages
- Assinatura da WABA: https://www.postman.com/meta/whatsapp-business-platform/folder/ozgs3jn/webhook-subscriptions

## Saida do incremento

O Incremento 0 e considerado concluido no codigo quando configuracao, endpoint, contrato e
testes estiverem aprovados. O inicio do Incremento 1 nao exige que os gates externos ja
estejam aprovados, mas o sandbox real depende de credenciais de desenvolvimento e o piloto
nao pode comecar enquanto `prontoPiloto` for falso.
