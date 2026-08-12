# 4. Modelo de dados

## Controles de piloto e operação

- `whatsapp_pilot_controls`: estado e pausa de saída por tenant, motivo, operador e datas de início/conclusão.
- `whatsapp_pilot_gates`: gate único por tenant, status, referência e hash da evidência, revisor e validade.
- `whatsapp_webhook_events.ack_duration_ms`: duração observada até a persistência do ACK, usada no p95 operacional.

As chaves estrangeiras compostas preservam o vínculo entre tenant e operador. Referências de evidência são metadados de governança e não devem conter segredos ou dados pessoais.

## Entidades principais

| Entidade | Campos essenciais |
|---|---|
| `whatsapp_integration` | `id`, `tenant_id`, `business_portfolio_id`, `waba_id`, `phone_number_id`, `display_phone`, `display_name`, `status`, `token_secret_ref`, `connected_at`, `disconnected_at` |
| `whatsapp_contact` | `id`, `tenant_id`, `wa_user_id`, `citizen_id?`, `profile_name`, `opt_status`, `first_seen_at`, `last_seen_at` |
| `conversation` | `id`, `tenant_id`, `contact_id`, `state`, `mode`, `window_expires_at`, `assigned_user_id?`, `version` |
| `message` | `id`, `tenant_id`, `conversation_id`, `provider_message_id`, `direction`, `type`, `body_ciphertext?`, `media_id?`, `status`, `occurred_at` |
| `media_asset` | `id`, `tenant_id`, `message_id`, `object_key`, `mime_type`, `sha256`, `size`, `retention_until`, `scan_status` |
| `consent_record` | `id`, `tenant_id`, `contact_id`, `purpose`, `legal_basis`, `notice_version`, `action`, `occurred_at`, `evidence` |
| `whatsapp_request_draft` | `id`, `tenant_id`, `conversation_id`, `citizen_id`, `status`, `description`, `category_id?`, `idempotency_key?`, `service_request_id?` |
| `service_request` | `id`, `tenant_id`, `citizen_id`, `public_protocol`, `category_id`, `summary`, `description`, `status`, `priority`, `source` |
| `ai_assessment` | `id`, `tenant_id`, `message_id/request_id`, `task`, `model`, `prompt_version`, `output_json`, `confidence`, `review_status` |
| `webhook_event` | `id`, `provider_event_key`, `correlation_id`, `tenant_id?`, `integration_id?`, `phone_number_id`, `payload_hash`, `payload`, `status`, `attempts`, `retention_until`, `payload_redacted_at`, `received_at`, `processed_at` |
| `outbox_event` | `id`, `tenant_id`, `aggregate_type`, `aggregate_id`, `event_type`, `payload`, `published_at?` |
| `flow_definition` | `id`, `tenant_id?`, `meta_flow_id`, `name`, `version`, `schema_hash`, `status` |
| `message_template` | `id`, `tenant_id`, `meta_template_id`, `name`, `language`, `category`, `status`, `version` |
| `audit_event` | `id`, `tenant_id`, `actor_type`, `actor_id?`, `action`, `resource`, `resource_id`, `metadata`, `occurred_at` |

O Incremento 3 implementa `whatsapp_contact`, `whatsapp_conversation`, `whatsapp_message` e
`whatsapp_conversation_transition`. O conteudo continua em `channel_message`; o envelope WhatsApp
referencia esse registro para evitar duplicacao de PII.

O Incremento 4 implementa o `consent_record` conversacional como
`whatsapp_privacy_record`, sem copiar conteúdo bruto para a evidência, e a coleta confirmável como
`whatsapp_request_draft`. O cadastro principal de `citizen` e a `service_request` são reutilizados;
não existe um segundo diretório ou uma segunda fila de solicitações exclusiva do WhatsApp. O
`protocol` sequencial permanece como referência interna e `public_protocol` passa a ser a
referência externa aleatória e não enumerável.

## Restrições

- `UNIQUE(phone_number_id) WHERE status = 'ACTIVE'`.
- `UNIQUE(tenant_id, wa_user_id)` para contatos.
- `UNIQUE(provider_event_key)` para idempotência.
- `UNIQUE(tenant_id, public_protocol)`; protocolo gerado aleatoriamente.
- FKs compostas ou validação equivalente impedem referências cruzadas entre tenants.
- Exclusão lógica para registros sujeitos a auditoria; anonimização para atender eliminação quando legalmente possível.

## Estados de integração

`PENDING`, `ACTIVE`, `DEGRADED`, `SUSPENDED`, `DISCONNECTED`, `REVOKED`.

## Estados da solicitação

`DRAFT`, `OPEN`, `TRIAGE`, `IN_PROGRESS`, `WAITING_CITIZEN`, `FORWARDED`, `RESOLVED`, `CANCELLED`, `CLOSED`.

## Incremento 5 - WhatsApp Flows

O Incremento 5 especializa `flow_definition` em `whatsapp_flow_definitions` e adiciona
`whatsapp_flow_sessions` e `whatsapp_flow_submissions`. A definição é imutável depois do
versionamento e protegida por hash; a sessão guarda somente o hash do token. Cada submissão fica
vinculada ao tenant, conversa e versão exata, com deduplicação pela mensagem da Meta e pelo hash
canônico da resposta. `whatsapp_request_drafts.declared_urgency` conserva a urgência declarada
separadamente de classificações futuras da IA.

## Incremento 6 - Mídia e IA assistiva

`whatsapp_media_assets` vincula tenant, integração, webhook, conversa e mensagem por FKs
compostas. A entidade guarda somente a referência opaca da Meta antes do download e, depois da
verificação, metadados do arquivo criptografado, antivírus, retenção e análise. Transcrição/OCR
registram provedor, modelo, prompt, confiança e revisão humana. Quando existe protocolo, o mesmo
blob é materializado no domínio existente de anexos e derivados, sem uma segunda cópia do arquivo.

## Incremento 7 - Saída, templates e opt-out

`whatsapp_message_templates` versiona o catálogo oficial por tenant e integração, incluindo idioma,
categoria, status da Meta e parâmetros. `whatsapp_messages` registra conteúdo de saída, template,
chave idempotente, decisão da política, ator, erro e timestamps de envio, entrega, leitura e falha.
O opt-out continua no contato e no estado terminal da conversa; a confirmação usa a mesma tabela
de mensagens e possui unicidade lógica por conversa.

## Retenção sugerida

Prazos finais devem ser aprovados pelo controlador e jurídico. Como padrão técnico configurável: payload bruto de webhook por poucos dias; conteúdo e anexos pelo prazo necessário ao atendimento e obrigação institucional; logs técnicos sem conteúdo por período maior; tokens apenas enquanto a integração estiver ativa. Jobs de retenção devem gerar evidência de execução.
