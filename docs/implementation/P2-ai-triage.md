# P2 - IA de Triagem

## Primeira fatia vertical

| Spec | Implementação |
| --- | --- |
| RIA-001 | Sugestão de categoria e subcategoria a partir do relato |
| RIA-002 | Sugestão de prioridade, impacto e urgência |
| RIA-006 | Detecção de possível emergência com orientação para atendimento competente |
| ADR-002 | Execução assíncrona pelo outbox e worker PostgreSQL |
| ADR-004 | Aceite, edição ou rejeição humana antes de alterar a solicitação |

## Controles de governança

- execução registra tenant, caso de uso, modelo, versão do prompt e hash da entrada;
- resultado registra confiança, latência, custo estimado e saída estruturada;
- falhas do provedor usam as retentativas e o dead-letter do worker;
- solicitações sem categoria disparam a triagem automaticamente após o cadastro;
- a solicitação continua disponível para classificação manual quando a IA falha;
- sugestões nunca alteram categoria, prioridade, impacto ou urgência sem revisão humana;
- decisões de aceite, edição ou rejeição geram histórico e auditoria;
- possível emergência é apenas destacada e não substitui serviços de emergência.

## Provedor local

O provider principal é o Ollama, executado na rede privada do Docker Compose com o modelo
`qwen2.5:3b`. O serviço `ollama-init` baixa o modelo uma vez e o mantém no volume
`ollama_data`, sem custo por requisição e sem enviar relatos para terceiros.

A resposta é limitada por JSON Schema, validada novamente pelo backend e executada com
temperatura zero. IDs de categoria que não pertençam ao tenant são rejeitados.

O classificador determinístico `gabflow-triage-rules-v1` permanece como fallback
configurável. Quando utilizado, a execução registra `LOCAL_FALLBACK`, o erro do Ollama e
`fallbackUtilizado: true`. Desabilitar `AI_TRIAGE_FALLBACK_ENABLED` faz com que falhas
sigam as retentativas e o dead-letter do worker.

Configurações:

```dotenv
AI_TRIAGE_PROVIDER=ollama
AI_TRIAGE_MODEL=qwen2.5:3b
AI_TRIAGE_FALLBACK_MODEL=gabflow-triage-rules-v1
AI_TRIAGE_PROMPT_VERSION=triage-v2
AI_TRIAGE_TIMEOUT_SECONDS=120
AI_TRIAGE_FALLBACK_ENABLED=true
OLLAMA_BASE_URL=http://ollama:11434
```
