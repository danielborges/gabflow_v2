# 7. Operação, testes e rollout

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
