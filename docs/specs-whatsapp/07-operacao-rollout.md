# 7. Operação, testes e rollout

## Implementação do Incremento 8

O cockpit administrativo implementa o gate de piloto por tenant, sem transformar o checklist abaixo em aprovação automática. Cada item interno exige status, revisor e referência de evidência com hash; início e retomada também dependem da prontidão externa e do semáforo operacional. A pausa segura bloqueia saídas comuns, preserva inbound e permite a confirmação obrigatória de opt-out.

As métricas são expostas em endpoint protegido e sem dimensão de tenant. O dashboard CloudWatch cobre idade/volume da fila, DLQ e alarmes. O procedimento detalhado está em `docs/runbooks/whatsapp-pilot-operations.md`.

## Estado do staging em 12/08/2026

A infraestrutura AWS de homologação foi aplicada e validada com API e workers estáveis. SQS
FIFO, DLQ, Secrets Manager/KMS, logs, dashboards e alarmes estão disponíveis. A integração Meta
permanece desativada por desenho.

O certificado ACM de `staging.gabflow.app` foi solicitado, mas o CNAME de validação e o CNAME da
aplicação ainda precisam ser publicados na zona Cloudflare. Até HTTPS ser validado, não se deve
conectar um número Meta nem usar credenciais reais. Consulte
[`AWS-staging-deployment-2026-08-12.md`](../implementation/AWS-staging-deployment-2026-08-12.md).

## Ambientes

- Desenvolvimento com números/testes próprios e dados sintéticos.
- Homologação isolada, aplicativo/segredos próprios e tenant fictício.
- Produção com deploy gradual, feature flags e acesso restrito.

## Estratégia de rollout

1. Sandbox técnico: webhook, idempotência, mídia, Flows e templates.
2. Alpha interno: tenant fictício e testes de falha/segurança.
3. Piloto: um gabinete, horário controlado e revisão humana obrigatória.
4. Piloto ampliado: 3–5 gabinetes, limites conservadores e métricas semanais.
5. GA: onboarding self-service após SLOs e auditoria aprovados.

## Matriz mínima de testes

- Unitários: máquina de estados, políticas de janela, opt-out e validação de esquema.
- Contrato: payloads oficiais versionados, erros e status de entrega.
- Integração: Embedded Signup, mídia, Flow endpoint e templates.
- Idempotência: duplicidade, retry, fora de ordem e replay.
- Multi-tenant: tentativa de leitura, escrita, cache, busca e mídia cruzados.
- Segurança: CSRF, SSRF, upload malicioso, prompt injection, IDOR e segredo.
- Carga: pico por campanha pública/evento sem degradação global.
- Resiliência: Meta/IA/storage indisponíveis, timeout, DLQ e replay seguro.
- E2E: cadastro, protocolo, acompanhamento, handoff, opt-out e desconexão.

## SLOs e alertas

- Disponibilidade do pipeline: 99,9% mensal após estabilização.
- p95 do ACK < 500 ms; alerta se tendência ameaçar limite externo.
- 99% dos eventos aceitos iniciam processamento em até 30 s.
- DLQ sem crescimento contínuo; zero conflito de tenant tolerado.
- Alerta imediato para token inválido, integração suspensa, assinatura inválida em volume ou suspeita de cruzamento de dados.

## Runbooks

### Meta indisponível

Abrir circuit breaker, preservar outbox, informar painel, não duplicar envios e retomar com rate limit.

### IA indisponível

Manter coleta estruturada e protocolo; encaminhar para triagem humana; nunca perder mensagem.

### Token revogado

Marcar `DEGRADED`, suspender envios, avisar administradores e oferecer reconexão por Embedded Signup.

### Evento na DLQ

Exibir motivo sem PII, corrigir causa, reprocessar por identificador com idempotência e registrar operador.

### Número desconhecido

Quarentena, alerta, investigação de configuração; nunca associar automaticamente por nome ou telefone textual.

## Go-live checklist

- [ ] App Review e termos aprovados.
- [ ] Políticas e versões da Graph API revisitadas.
- [ ] DPA, aviso de privacidade e retenção aprovados.
- [ ] Segredos, rotação, backup e restore testados.
- [ ] Testes multi-tenant negativos aprovados.
- [ ] Opt-out, handoff e contingência sem IA aprovados.
- [ ] Flows e templates aprovados em produção.
- [ ] Dashboards, alertas, DLQ e runbooks operacionais.
- [ ] Treinamento do gabinete e canal de suporte.
- [ ] Plano de rollback e desconexão validado.
