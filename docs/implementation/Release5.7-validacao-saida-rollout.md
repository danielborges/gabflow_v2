# Release 5.7 — Validação de saída, métricas e rollout

O resultado final de consultas documentais, estruturadas e híbridas é validado
antes de ser persistido ou retornado. A decisão fechada armazena apenas hash,
versões, sinais, bucket, percentual e ação; nunca duplica o texto da resposta.

Vazamento de instruções internas, credenciais e alegações de ação não executada
são críticos e bloqueiam sempre. Destinos externos e inconsistências de citação
respeitam o canário determinístico por tenant. Os gates promovem `5 -> 20 -> 50 ->
100` e fazem rollback quando a taxa de bloqueio excede o limite.

Endpoints:

- `GET/POST /api/v1/assistente/seguranca/validacao-saida/rollout`;
- `POST /api/v1/assistente/seguranca/validacao-saida/rollback`;
- `/api/v1/assistente/metricas`, campo `validacaoSaida`.
