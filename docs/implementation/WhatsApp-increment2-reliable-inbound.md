# WhatsApp Business Platform - Incremento 2

## Objetivo

Receber webhooks da Meta por um endpoint global, responder rapidamente e garantir que eventos
validos nao sejam perdidos ou processados duas vezes. O tenant e sempre resolvido no servidor
pelo `phone_number_id`; nao existe tenant padrao para contingencia.

## Endpoint global

```text
GET  /api/v1/webhooks/meta/whatsapp
POST /api/v1/webhooks/meta/whatsapp
GET  /api/v1/tenants/{tenantId}/whatsapp/health
```

O `GET` realiza o challenge com o verify token. O `POST` valida
`X-Hub-Signature-256` sobre os bytes originais, limita o corpo a 1 MiB por padrao e rejeita
assinaturas invalidas antes de consultar ou gravar dados operacionais.

O ACK `200` so ocorre depois que cada evento logico foi persistido no inbox transacional. Download
de midia, IA e criacao de solicitacao nao fazem parte da rota publica.

O endpoint autenticado de saude consolida assinatura do webhook, estado da integracao, ultimo
recebimento e falhas do inbox sem expor IDs da Meta, referencias de segredo ou payloads.

## Inbox idempotente

`whatsapp_webhook_events` conserva a chave unica `provider_event_key`, o hash SHA-256, a rota
resolvida, o correlation ID, tentativas e o estado do processamento. Os estados sao `RECEIVED`,
`QUEUED`, `PROCESSING`, `PROCESSED`, `QUARANTINED` e `FAILED`.

Mensagens usam a chave `meta:{provider_message_id}:message`. Status incluem mensagem, estado e
timestamp. Uma repeticao recebe `200` e nao cria outro inbox, item de canal ou outbox.

## Roteamento e quarentena

Somente uma `WhatsAppIntegration` em `ACTIVE` pode resolver um `phone_number_id`. Numero ausente,
desconhecido, pendente, suspenso ou desconectado gera `QUARANTINED` sem `tenant_id`, sem fallback e
sem publicacao na fila. Logs registram apenas IDs tecnicos, correlation ID e motivo, nunca texto,
token ou payload bruto.

## Transporte assincrono

Em desenvolvimento e testes, `WHATSAPP_INBOUND_QUEUE_BACKEND=database` grava um `OutboxEvent` na
mesma transacao do inbox e usa o worker existente.

Em staging e producao, `WHATSAPP_INBOUND_QUEUE_BACKEND=aws-sqs` usa Amazon SQS FIFO. O corpo contem
somente `schemaVersion` e `webhookEventId`; o UUID e a chave de deduplicacao; tenant e remetente
formam o grupo ordenado. Long polling e de 20 segundos, visibility timeout de 120 segundos e cinco
recebimentos enviam a referencia para a DLQ FIFO. Ambas as filas usam KMS.

A API persiste antes de publicar. Se o SQS estiver indisponivel, responde `200` porque o inbox ja
esta duravel e deixa o evento em `RECEIVED`. O scheduler reconcilia esses registros depois. Se
houver publicacao duplicada entre SQS e commit, o consumidor permanece idempotente.

## Processamento e retencao

O worker valida novamente integracao, tenant e numero antes de criar `ChannelMessage`. O item do
canal nao recebe payload bruto. Falhas transitorias geram retry; esgotamento marca `FAILED` e o
redrive do SQS conduz a referencia para a DLQ.

O payload normalizado fica armazenado por sete dias por padrao. Depois de `retention_until`, o
scheduler o substitui por objeto vazio e preserva hash, rota, timestamps e evidencia de redacao.

## Infraestrutura e observabilidade

O modulo Terraform `modules/messaging` cria fila, DLQ, redrive allow policy, criptografia KMS,
menor privilegio para API/worker e alarmes para DLQ nao vazia e idade acima de cinco minutos.
Logs estruturados nao incluem conteudo de mensagem.

## Criterios de saida

- assinatura invalida retorna `401` e nao persiste evento;
- ACK valido ocorre depois da persistencia;
- repeticao nao duplica efeitos;
- numero desconhecido fica em quarentena sem tenant;
- indisponibilidade do SQS nao perde evento persistido;
- reconciliacao publica eventos pendentes;
- worker processa mensagem com contexto do tenant;
- payload expirado e redigido;
- SQS FIFO, DLQ, KMS e alarmes estao declarados em Terraform;
- testes automatizados e contratos estao aprovados.

## Proximo gate

O Incremento 3 pode implementar contatos, conversas e maquina de estados. A promocao automatica de
uma integracao `PENDING` para `ACTIVE` continua bloqueada ate o teste de saude comprovar webhook e
envio controlado ponta a ponta.

## Referencias oficiais verificadas em 2026-08-12

- SQS SendMessage e grupos FIFO: https://docs.aws.amazon.com/boto3/latest/reference/services/sqs/queue/send_message.html
- SQS ReceiveMessage e long polling: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_ReceiveMessage.html
- DLQ e redrive: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue-redrive.html
