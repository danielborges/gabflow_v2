# WhatsApp Business Platform - Incremento 1

## Objetivo

Criar o dominio tenant-scoped da integracao oficial e implementar o backend do Embedded
Signup sem ativar mensagens antes do teste de saude do numero. O resultado deste incremento
e uma integracao `PENDING`, com ativos confirmados pela Meta e token armazenado fora do banco.

## Entregas

- `whatsapp_integrations` versiona Business Portfolio, WABA e numero por tenant;
- `whatsapp_onboarding_sessions` controla idempotencia, expiracao e uso unico do callback;
- indice parcial impede que um `phone_number_id` ativo pertenca a dois tenants;
- `state` usa nonce aleatorio, assinatura HMAC e hash persistido;
- o callback troca o `code` apenas no backend e nunca o persiste;
- a Graph API confirma WABA, portfolio, numero e assinatura do aplicativo;
- o token e entregue a um `WhatsAppSecretStore` e somente a referencia e persistida;
- a aba administrativa de Integracoes inicia o Embedded Signup pelo SDK oficial da Meta;
- reconexoes futuras recebem uma nova versao, preservando historico;
- a resolucao `phone_number_id -> tenant_id` aceita somente uma integracao `ACTIVE`.

## Endpoints implementados

```text
GET  /api/v1/tenants/{tenantId}/whatsapp/integration
POST /api/v1/tenants/{tenantId}/whatsapp/onboarding-sessions
POST /api/v1/tenants/{tenantId}/whatsapp/onboarding-callback
```

Todos exigem administrador do proprio tenant. Tentativas cross-tenant retornam `404` para
nao revelar a existencia do gabinete ou da integracao.

App ID, Configuration ID e versao da Graph API sao entregues somente na sessao autenticada
de onboarding porque sao parametros publicos exigidos pelo SDK. Segredos continuam restritos
ao backend.

## Lifecycle deste incremento

```text
sessao: PENDING -> PROCESSING -> COMPLETED
                     |
                     +-> FAILED
PENDING -> EXPIRED

integracao: PENDING
```

`ACTIVE` fica reservado para o incremento que comprovar a saude ponta a ponta. Uma
integracao `PENDING` nao participa do roteamento de webhooks e nao autoriza envios.

## Adapter Meta

O adapter de producao executa as seguintes operacoes:

1. troca do `code` por token na Graph API;
2. depuracao do token e leitura dos ativos autorizados;
3. exigencia de exatamente uma WABA e um numero no escopo;
4. consulta do portfolio proprietario e dos metadados oficiais do numero;
5. registro do numero e criacao do PIN de verificacao em duas etapas;
6. assinatura da WABA em `subscribed_apps`.

Respostas externas sao validadas e erros retornados ao frontend sao deliberadamente
genericos. Token, PIN, `code`, App Secret e payload bruto da Meta nao entram em logs ou
auditoria. O token e o PIN sao gravados juntos no cofre e o banco conserva apenas a referencia.

## Cofre de segredos

O cofre de producao e o AWS Secrets Manager em `sa-east-1`, criptografado por KMS e acessado
por ECS Task Roles. O adapter implementa `WhatsAppSecretStore` e cria um secret por integracao:

```text
gabflow/{environment}/whatsapp/{tenant_id}/{integration_id}
```

O conteudo possui `access_token` e `two_step_pin`, mas somente o ARN retornado pelo AWS Secrets
Manager e persistido no PostgreSQL. A API pode criar o secret e agendar sua exclusao com janela
de recuperacao; a task role do worker e a unica com leitura das credenciais WhatsApp. Access
keys estaticas nao fazem parte da configuracao.

O backend continua falhando fechado com `503 secret_backend_unavailable` se o SDK nao puder
usar a task role, se o KMS estiver ausente ou se o AWS Secrets Manager rejeitar a operacao.

## Criterios de saida

- migration sobe e desce sem quebrar a cadeia Alembic;
- sessao e idempotente por tenant e expira em dez minutos por padrao;
- `state` alterado, expirado ou reutilizado e rejeitado;
- callback nao aceita IDs de WABA ou numero enviados pelo browser como autoridade;
- conflito de numero falha sem sobrescrever o tenant existente;
- banco guarda apenas `token_secret_ref`;
- integracao criada permanece `PENDING`;
- resolucao de numero desconhecido nunca escolhe tenant padrao;
- OpenAPI e testes automatizados estao aprovados.

## Evolucao posterior

O Incremento 2 implementa o webhook global, quarentena, inbox idempotente, fila e DLQ. A promocao
para `ACTIVE` continua condicionada ao teste de webhook e envio controlado ponta a ponta.

## Referencias oficiais verificadas em 2026-08-11

- Embedded Signup: https://www.postman.com/meta/whatsapp-business-platform/documentation/du6gzjv/embedded-signup
- Debug Token: https://www.postman.com/meta/whatsapp-business-platform/request/i1mz7w8/debug-token
- Registro do numero: https://www.postman.com/meta/whatsapp-business-platform/folder/zuoeksl/registration
- Assinatura da WABA: https://www.postman.com/meta/whatsapp-business-platform/request/0yubu4i/subscribe-app-to-whatsapp-business-account
