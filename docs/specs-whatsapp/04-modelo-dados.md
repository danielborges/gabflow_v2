# 4. Modelo de dados

## Entidades principais

| Entidade | Campos essenciais |
|---|---|
| `whatsapp_integration` | `id`, `tenant_id`, `business_portfolio_id`, `waba_id`, `phone_number_id`, `display_phone`, `display_name`, `status`, `token_secret_ref`, `connected_at`, `disconnected_at` |
| `whatsapp_contact` | `id`, `tenant_id`, `wa_user_id`, `citizen_id?`, `profile_name`, `opt_status`, `first_seen_at`, `last_seen_at` |
| `conversation` | `id`, `tenant_id`, `contact_id`, `state`, `mode`, `window_expires_at`, `assigned_user_id?`, `version` |
| `message` | `id`, `tenant_id`, `conversation_id`, `provider_message_id`, `direction`, `type`, `body_ciphertext?`, `media_id?`, `status`, `occurred_at` |
| `media_asset` | `id`, `tenant_id`, `message_id`, `object_key`, `mime_type`, `sha256`, `size`, `retention_until`, `scan_status` |
| `consent_record` | `id`, `tenant_id`, `contact_id`, `purpose`, `legal_basis`, `notice_version`, `action`, `occurred_at`, `evidence` |
| `service_request` | `id`, `tenant_id`, `citizen_id`, `public_protocol`, `category_id`, `summary`, `description`, `status`, `priority`, `source` |
| `ai_assessment` | `id`, `tenant_id`, `message_id/request_id`, `task`, `model`, `prompt_version`, `output_json`, `confidence`, `review_status` |
| `webhook_event` | `id`, `provider_event_key`, `tenant_id?`, `payload_hash`, `status`, `attempts`, `received_at`, `processed_at` |
| `outbox_event` | `id`, `tenant_id`, `aggregate_type`, `aggregate_id`, `event_type`, `payload`, `published_at?` |
| `flow_definition` | `id`, `tenant_id?`, `meta_flow_id`, `name`, `version`, `schema_hash`, `status` |
| `message_template` | `id`, `tenant_id`, `meta_template_id`, `name`, `language`, `category`, `status`, `version` |
| `audit_event` | `id`, `tenant_id`, `actor_type`, `actor_id?`, `action`, `resource`, `resource_id`, `metadata`, `occurred_at` |

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

## Retenção sugerida

Prazos finais devem ser aprovados pelo controlador e jurídico. Como padrão técnico configurável: payload bruto de webhook por poucos dias; conteúdo e anexos pelo prazo necessário ao atendimento e obrigação institucional; logs técnicos sem conteúdo por período maior; tokens apenas enquanto a integração estiver ativa. Jobs de retenção devem gerar evidência de execução.
