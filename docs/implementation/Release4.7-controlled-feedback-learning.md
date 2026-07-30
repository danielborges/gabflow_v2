# Release 4.7 — Feedback e reaprendizado controlado

## Status

Em implementação. A captura confiável (`4.7.1`) e a curadoria para o dataset
(`4.7.2`) foram entregues; compilação de sinais e ativação de artefatos permanecem
planejadas.

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

### Entidades planejadas

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

1. criar job idempotente por tenant e janela;
2. agregar somente feedback aprovado;
3. exigir quantidade mínima ou aprovação explícita;
4. gerar `RERANK_PROFILE`, `ROUTING_EXAMPLES`, `EVALUATION_CASES` e
   `ANSWER_EXEMPLARS`;
5. limitar boosts/penalidades e aplicar decaimento;
6. preservar proveniência até cada feedback.

### 4.7.4 — Avaliação, ativação e rollback

1. executar baseline e candidato no mesmo dataset e configuração;
2. impedir ativação com regressão acima da tolerância;
3. ativar uma versão por tipo e tenant, inicialmente em canário;
4. registrar no resultado da consulta a versão dos artefatos que influenciaram a
   decisão;
5. monitorar métricas online e executar rollback manual ou automático;
6. recompilar quando feedback ou fonte de origem for revogado/purgado.

## Regras de aplicação

- ajustes de feedback acontecem depois de autorização, vigência e limiar individual;
- nenhum boost faz uma fonte abaixo do limiar entrar no contexto;
- feedback positivo não torna todas as fontes automaticamente relevantes;
- feedback negativo não despublica documento nem altera outro tenant;
- correção humana sem fontes válidas pode orientar estilo ou virar caso negativo,
  mas não resposta de referência fundamentada;
- conteúdo livre nunca compõe instruções de sistema;
- aprendizado global exige outro processo, anonimização, autorização e aprovação.

## Contratos planejados

- `POST /assistente/consultas/{consultaId}/feedback`;
- `GET /assistente/consultas/{consultaId}/feedback`;
- `GET /assistente/feedback?estado=...`;
- `PATCH /assistente/feedback/{feedbackId}/moderacao`;
- `POST /assistente/feedback/{feedbackId}/promover-avaliacao`;
- `POST /assistente/aprendizado/execucoes`;
- `GET /assistente/aprendizado/execucoes`;
- `GET /assistente/aprendizado/artefatos`;
- `POST /assistente/aprendizado/artefatos/{artefatoId}/ativacao`;
- `POST /assistente/aprendizado/artefatos/{artefatoId}/rollback`.

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
