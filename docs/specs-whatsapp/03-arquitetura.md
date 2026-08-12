# 3. Arquitetura

## Plano operacional do piloto

O plano de dados continua recebendo webhooks e processando filas de forma assíncrona. O plano de controle adiciona um cockpit autenticado por tenant, gates de evidência e um interruptor de saída consultado no enfileiramento e no dispatch. Health e Prometheus expõem apenas agregados globais protegidos; o dashboard CloudWatch acompanha SQS e DLQ sem cardinalidade por cidadão ou tenant.

Os ambientes de `staging` e `production` seguem o
[`ADR-012`](../specs/adr/ADR-012-aws-production-platform.md). Para WhatsApp, API e workers
executam no ECS, tokens ficam no AWS Secrets Manager com KMS e somente a referência opaca é
persistida no PostgreSQL/RDS.

## Componentes

- **Portal React:** onboarding, caixa de entrada, configuração e auditoria.
- **API Python:** autenticação, RBAC, domínio e endpoints administrativos.
- **Webhook Gateway:** validação, ACK, idempotência e publicação na fila.
- **Message Orchestrator:** máquina de estados, janela de atendimento e handoff.
- **Meta Adapter:** Cloud API, mídia, templates, Flows e status.
- **AI Gateway:** transcrição, extração, classificação, redaction e versionamento.
- **Worker Queue:** Amazon SQS FIFO com agrupamento por conversa, retries e DLQ FIFO; inbox
  PostgreSQL garante persistencia antes do ACK e reconciliacao cobre falha de publicacao.
- **PostgreSQL:** estado transacional com isolamento por tenant.
- **Object Storage:** anexos criptografados e URLs temporárias.
- **Observability:** métricas, traces, logs e alertas.

## Fluxo de entrada

1. `GET /webhooks/meta/whatsapp` valida o challenge de configuração.
2. `POST /webhooks/meta/whatsapp` valida autenticidade conforme especificação vigente.
3. O payload bruto recebe hash, `received_at` e chave idempotente.
4. O gateway resolve `phone_number_id -> tenant_id` em cache seguro/DB.
5. Desconhecido, suspenso ou conflitante é enviado à quarentena.
6. O ACK ocorre antes de transcrição, download de mídia ou chamada de IA.
7. Worker normaliza evento, atualiza conversa e executa a máquina de estados.
8. Outbox grava comandos de envio na mesma transação da mudança de estado.
9. Worker de saída envia à Meta e correlaciona status posteriores.

## Máquina de estados da conversa

`NEW -> PRIVACY_NOTICE -> IDENTIFICATION -> INTENT -> DATA_COLLECTION -> REVIEW -> PROTOCOL_CREATED -> FOLLOW_UP`

Estados laterais: `HUMAN_HANDOFF`, `OPTED_OUT`, `BLOCKED`, `ERROR_RECOVERY`, `CLOSED`.

Eventos inválidos não avançam estado. Cada transição registra ator, origem, versão da regra e correlação.

## Isolamento multi-tenant

- Contexto de tenant vem do token do usuário ou do mapeamento servidor-side do número.
- Repositórios exigem `tenant_id`; consultas sem tenant são proibidas na camada de aplicação.
- RLS no PostgreSQL é recomendado como segunda barreira.
- Chaves únicas compostas incluem tenant quando o dado puder se repetir.
- Cache, filas, armazenamento e índices vetoriais usam namespace por tenant.
- Suporte interno usa acesso just-in-time, motivo obrigatório e auditoria.

## Idempotência e ordenação

- Chave primária lógica: `provider + provider_message_id + event_type`.
- O mesmo evento pode chegar mais de uma vez e deve produzir o mesmo resultado.
- Ordenação por conversa é serializada por chave `tenant_id:wa_user_id`.
- Eventos fora de ordem atualizam status apenas se a transição for monotônica.
- Retry exponencial com jitter; falhas permanentes vão para DLQ e geram alerta.

## Saída e templates

- O serviço de políticas decide se mensagem livre está permitida na janela vigente.
- Fora da janela, somente template aprovado e adequado à finalidade.
- Todo envio passa por outbox, limite por tenant e circuit breaker.
- O tenant não informa diretamente `phone_number_id` no comando; ele é resolvido pela integração ativa.

## IA e RAG

- Entrada é tratada como conteúdo não confiável; instruções do cidadão não alteram políticas do sistema.
- Prompt e esquema de saída são versionados.
- Resposta estruturada é validada por JSON Schema/Pydantic.
- RAG consulta somente documentos autorizados do tenant e base pública aprovada.
- PII é minimizada antes de provedores externos quando possível.
- Guardar resultado, confiança, modelo, prompt version e revisão humana; não guardar raciocínio interno.

## Pipeline de mídia do Incremento 6

O evento normalizado cria a referência de mídia e um comando de download no outbox. Download,
verificação, armazenamento criptografado e transcrição/OCR rodam em etapas independentes depois
do ACK. Cada etapa tem retry e estado terminal próprio. A triagem assistiva consome apenas texto
extraído e metadados aprovados para o tenant; falha de IA nunca altera a confirmação do protocolo.

## Política de saída do Incremento 7

Antes de enfileirar e novamente antes de enviar, o serviço valida tenant, integração ativa,
opt-out, janela de 24 horas e aprovação/categoria do template. O outbox conserva idempotência e o
webhook de status avança `QUEUED -> SENT -> DELIVERED -> READ`, sem regressão. Falhas permanentes
ficam associadas à mensagem; destinatário e credenciais nunca são aceitos do frontend.

## Observabilidade mínima

- `webhook_ack_latency`, `events_received`, `duplicate_events`, `unknown_phone_number`.
- `message_processing_latency`, `flow_completion_rate`, `handoff_rate`.
- `ai_failure_rate`, `low_confidence_rate`, `human_correction_rate`.
- `outbound_failures`, `template_rejections`, `dlq_depth`, `opt_out_rate`.
- Alertas por integração desconectada, token inválido, pico de falha e risco de vazamento entre tenants.
