# Release 4.7 — Feedback e reaprendizado controlado

## Status

Concluída. Captura confiável (`4.7.1`), curadoria para o dataset (`4.7.2`),
compilação de candidatos (`4.7.3`) e avaliação, ativação e rollback (`4.7.4`)
foram entregues.

## Estado de partida

O endpoint atual permite avaliação `POSITIVA`, `NEGATIVA` ou `CORRIGIDA` e
persiste comentário, resposta corrigida, revisor e data na própria consulta. O
registro é tenant-scoped e auditado, mas:

- uma nova avaliação sobrescreve a anterior;
- não há motivos normalizados nem julgamento por fonte;
- o feedback não passa por quarentena ou moderação;
- não produz dataset, perfil de ranking ou exemplos de roteamento;
- não há artefato versionado, comparação com baseline, ativação ou rollback.

## Objetivo

Usar feedback humano para melhorar retrieval, roteamento e avaliação do mesmo
tenant, sem treinamento implícito, sem converter correções em evidência e sem
permitir que conteúdo não confiável alcance prompts ou outros tenants.

## Arquitetura alvo

```text
consulta e fontes versionadas
  -> feedback imutável + motivos + julgamentos por fonte
  -> validação tenant/ACL + minimização + segurança
  -> PENDENTE_REVISAO | APROVADO | QUARENTENA | REJEITADO | REVOGADO
  -> compilação idempotente por tenant
  -> artefato CANDIDATO versionado
  -> avaliação candidato x baseline
  -> APROVADO_PARA_ATIVACAO
  -> ativação atômica / canário
  -> monitoramento e rollback
```

### Entidades

`RagQueryFeedback`

- evento imutável com tenant, consulta, revisor, avaliação, motivos, comentário,
  correção, método/filtros esperados, estado, hash e referência à revisão anterior;
- guarda snapshots mínimos dos IDs e versões avaliados, não cópias livres dos
  documentos;
- correção e comentário são conteúdo não confiável até aprovação.

`RagFeedbackSourceJudgment`

- julgamento por fonte/versionamento: `RELEVANTE`, `IRRELEVANTE` ou `AUSENTE`;
- motivo normalizado e posição original;
- foreign keys compostas com `tenant_id`.

`RagLearningRun`

- execução idempotente de compilação com janela, configuração, baseline,
  contagens por estado, métricas e erro;
- processada por worker no contexto RLS do tenant.

`RagLearningArtifact`

- tipo, versão, payload limitado, feedbacks de origem, métricas, estado,
  aprovador, ativação e rollback;
- uma versão ativa por tenant e tipo;
- payload validado por schema, sem texto bruto de comentário.

### Estados

Feedback:

- `PENDENTE_REVISAO`;
- `APROVADO`;
- `QUARENTENA`;
- `REJEITADO`;
- `REVOGADO`;
- `SUPERADO`.

A aprovação pode ser automática somente para sinais estruturados de baixo risco
que passam em todas as validações. Comentário livre, resposta corrigida, fonte
ausente e sinal de alto impacto exigem moderação humana. O registro distingue modo
`AUTOMATICA` ou `HUMANA`, moderador e regra aplicada.

Artefato:

- `CANDIDATO`;
- `EM_AVALIACAO`;
- `REJEITADO`;
- `APROVADO`;
- `ATIVO`;
- `SUBSTITUIDO`;
- `REVOGADO`.

## Sequência recomendada de implementação

### 4.7.1 — Captura confiável

1. **Entregue:** tabelas imutáveis, enums, constraints compostas, índices e RLS;
2. **Entregue:** manutenção do `PATCH` atual como fachada compatível, criando uma
   revisão imutável;
3. **Entregue:** motivos normalizados, método/filtros esperados e julgamentos por
   fonte;
4. **Entregue:** validação da fonte contra consulta, versão, tenant e acesso atual;
5. **Entregue:** limites, minimização de PII e detecção de prompt injection em
   texto livre;
6. **Entregue:** auditoria de criação, substituição, moderação e revogação sem
   conteúdo livre;
7. **Entregue:** idempotência por chave do cliente e serialização de revisões em
   corrida pelo bloqueio da consulta.

Papéis: usuários autenticados enviam feedback; gestores moderam conteúdo de alto
risco; administradores do tenant ativam ou revertem artefatos. Ativação relevante
não pode depender somente da aprovação do autor do feedback.

### 4.7.2 — Curadoria e dataset

1. **Entregue:** fila tenant-scoped para gestores;
2. **Entregue:** promoção explícita e idempotente de feedback aprovado para caso de
   avaliação;
3. **Entregue:** conversão de fontes relevantes ou ausentes em expectativas
   versionadas e de fontes irrelevantes em hard negatives;
4. **Entregue:** expectativa de rota, filtros e recusa;
5. **Entregue:** desativação automática antes do uso para sinais revogados,
   superados ou ligados a fonte eliminada/inacessível;
6. **Entregue:** métricas de acurácia de roteamento, acurácia de filtros e taxa de
   recuperação de hard negatives;
7. **Entregue:** proveniência por FK composta entre caso, feedback e tenant.

### 4.7.3 — Compilação de sinais

1. **Entregue:** job assíncrono e idempotente por tenant, janela e configuração;
2. **Entregue:** agregação exclusiva de feedback aprovado;
3. **Entregue:** quantidade mínima configurável ou aprovação explícita da amostra
   pequena;
4. **Entregue:** geração de `RERANK_PROFILE`, `ROUTING_EXAMPLES`,
   `EVALUATION_CASES` e
   `ANSWER_EXEMPLARS`;
5. **Entregue:** limite de boosts/penalidades, meia-vida configurável e preservação
   do limiar mínimo do retrieval;
6. **Entregue:** proveniência relacional até cada feedback e hash canônico do
   payload.

Os artefatos desta etapa nascem sempre em `CANDIDATO` e não alteram retrieval,
roteamento ou geração. Respostas corrigidas aprovadas são novamente verificadas
contra prompt injection e só podem compor exemplar de avaliação e forma, com
`evidenciaFactual=false`.

Configurações operacionais: `RAG_LEARNING_MIN_SIGNALS`,
`RAG_LEARNING_MAX_ADJUSTMENT`, `RAG_LEARNING_DECAY_HALF_LIFE_DAYS` e
`RAG_LEARNING_MAX_EXAMPLES`.

### 4.7.4 — Avaliação, ativação e rollback

1. **Entregue:** execução de baseline e candidato no mesmo dataset e `k`;
2. **Entregue:** bloqueio de aprovação quando a regressão excede a tolerância;
3. **Entregue:** aprovação explícita e ativação atômica de uma versão por tipo e
   tenant, inicialmente em canário;
4. **Entregue:** registro na consulta das versões que efetivamente influenciaram a
   decisão;
5. **Entregue:** métricas online e rollback manual ou automático por taxa de
   avaliações negativas;
6. **Entregue:** invalidação e recompilação quando feedback de origem for
   revogado/superado ou fonte operacional for purgada.

O reranking atua somente sobre candidatos previamente autorizados e acima do
limiar individual. Exemplos de roteamento são aplicados por hash exato da consulta.
`EVALUATION_CASES` e `ANSWER_EXEMPLARS` não são tratados como evidência de runtime.

Configurações adicionais: `RAG_LEARNING_EVALUATION_K`,
`RAG_LEARNING_MAX_REGRESSION`, `RAG_LEARNING_CANARY_PERCENT`,
`RAG_LEARNING_ONLINE_MIN_SAMPLES` e
`RAG_LEARNING_ONLINE_MAX_NEGATIVE_RATE`.

## Regras de aplicação

- ajustes de feedback acontecem depois de autorização, vigência e limiar individual;
- nenhum boost faz uma fonte abaixo do limiar entrar no contexto;
- feedback positivo não torna todas as fontes automaticamente relevantes;
- feedback negativo não despublica documento nem altera outro tenant;
- correção humana sem fontes válidas pode orientar estilo ou virar caso negativo,
  mas não resposta de referência fundamentada;
- conteúdo livre nunca compõe instruções de sistema;
- aprendizado global exige outro processo, anonimização, autorização e aprovação.

## Contratos

- `POST /assistente/consultas/{consultaId}/feedback`;
- `GET /assistente/consultas/{consultaId}/feedback`;
- `GET /assistente/feedback?estado=...`;
- `PATCH /assistente/feedback/{feedbackId}/moderacao`;
- `POST /assistente/feedback/{feedbackId}/promover-avaliacao`;
- `POST /assistente/aprendizado/execucoes`;
- `GET /assistente/aprendizado/execucoes`;
- `GET /assistente/aprendizado/artefatos`;
- `GET /assistente/aprendizado/artefatos/{artefatoId}`;
- `POST /assistente/aprendizado/artefatos/{artefatoId}/avaliacao`;
- `POST /assistente/aprendizado/artefatos/{artefatoId}/ativacao`;
- `POST /assistente/aprendizado/artefatos/{artefatoId}/rollback`.

Todos os contratos estão implementados.

## Critérios de conclusão

- histórico imutável e reversível de feedback por tenant;
- nenhuma influência cruzada entre tenants, inclusive no worker e cache;
- prompt injection em comentário/correção resulta em quarentena;
- fontes julgadas pertencem à consulta, versão e tenant informados;
- artefatos são reproduzíveis, versionados e explicáveis;
- candidato e baseline são avaliados antes da ativação;
- ajuste não ignora ACL, jurisdição, vigência, estado ou limiar;
- rollback restaura a versão anterior atomicamente;
- purge ou revogação invalida e recompila artefatos dependentes;
- métricas e alertas permitem detectar regressão e abuso.
