# ADR-009 — Reaprendizado controlado por feedback

## Status

Aceito para implementação

## Contexto

O GabFlow já registra avaliação positiva, negativa ou corrigida para uma consulta
RAG. O registro atual é útil para auditoria, mas não diferencia falha de retrieval,
roteamento, resposta, citação, vigência ou jurisdição; também não preserva revisões
como eventos imutáveis nem participa do ciclo de melhoria.

Aplicar um clique diretamente no prompt, no índice ou nos pesos do modelo criaria
riscos de envenenamento, prompt injection, oscilação do ranking, perda de
explicabilidade e contaminação entre tenants. Uma resposta corrigida também não é,
por si só, uma fonte probatória.

## Decisão

Adotar um pipeline tenant-scoped de aprendizado controlado em três planos:

1. **Captura:** registrar cada revisão como feedback imutável, ligado à consulta,
   fontes e versões originais. Uma nova revisão substitui semanticamente a anterior,
   sem apagá-la.
2. **Compilação:** validar segurança e autorização, classificar o tipo de falha,
   agregar sinais e produzir artefatos candidatos versionados.
3. **Ativação:** comparar candidato e baseline no dataset do tenant, aprovar,
   ativar por versão e permitir rollback imediato.

O feedback bruto nunca será concatenado ao prompt de sistema, indexado como
conhecimento, usado como citação ou aplicado diretamente aos pesos do modelo.

Sinais exclusivamente estruturados podem ser aprovados automaticamente depois das
validações de tenant, vínculo com a consulta, autorização e anomalia. Texto livre,
resposta corrigida, indicação de fonte ausente e alterações de alto impacto exigem
moderação humana. Feedback sem motivo ou julgamento suficiente continua útil para
métricas de satisfação, mas não gera ajuste comportamental.

## Tipos de sinal

- **Retrieval:** julgamento `RELEVANTE`, `IRRELEVANTE` ou `AUSENTE` por fonte e
  versão, usado para exemplos de ranking e hard negatives.
- **Roteamento:** método esperado `DOCUMENTAL`, `ESTRUTURADO` ou `HIBRIDO` e filtros
  esperados.
- **Resposta:** classificação de problemas e correção humana. A correção pode virar
  referência de avaliação, mas não evidência documental.
- **Segurança:** conteúdo suspeito é colocado em quarentena e não participa de
  compilação ou avaliação.

Os motivos normalizados incluem, no mínimo, `FONTES_IRRELEVANTES`,
`FONTE_AUSENTE`, `RESPOSTA_INCORRETA`, `CITACAO_INCORRETA`,
`FONTE_DESATUALIZADA`, `JURISDICAO_INCORRETA`, `ROTEAMENTO_INCORRETO`,
`FILTROS_INCORRETOS`, `RECUSA_INDEVIDA`, `DEVERIA_RECUSAR` e
`PROBLEMA_DE_ESTILO`.

## Artefatos de aprendizado

Cada artefato possui tenant, tipo, versão, configuração-base, período e feedbacks
de origem, métricas antes/depois, estado, aprovador, ativação e eventual rollback.
Os primeiros tipos serão:

- `RERANK_PROFILE`: ajustes limitados por intenção/consulta e fonte;
- `ROUTING_EXAMPLES`: exemplos aprovados de método e filtros;
- `EVALUATION_CASES`: perguntas, fontes esperadas e expectativa de recusa;
- `ANSWER_EXEMPLARS`: correções fundamentadas usadas apenas para avaliação e
  orientação de forma, nunca como fonte factual.

O perfil de reranking só pode ajustar a ordem de candidatos já autorizados e acima
do limiar mínimo de evidência. Ele não pode recuperar fonte bloqueada, ressuscitar
fonte revogada, atravessar ACL ou tenant, nem transformar baixa similaridade em
evidência. Ajustes têm magnitude máxima, quantidade mínima de sinais, decaimento e
janela temporal configuráveis.

## Promoção e rollback

Um candidato somente pode ser ativado quando:

- possui o mínimo configurado de sinais válidos ou revisão explícita de gestor;
- não contém feedback em quarentena, revogado ou superado;
- passa testes de isolamento, ACL, jurisdição, vigência e prompt injection;
- não regride além das tolerâncias definidas em `precision@k`, `recall@k`,
  groundedness, precisão de citações, fontes desconexas e acurácia de recusa;
- melhora a métrica-alvo ou possui justificativa humana registrada.

Somente uma versão de cada tipo fica ativa por tenant. A troca é atômica; a versão
anterior permanece disponível para rollback. Revogação de um feedback dispara
recompilação dos artefatos dependentes.

## Consequências

### Positivas

- melhoria mensurável e explicável por tenant;
- resistência a cliques acidentais, abuso e prompt injection;
- histórico reproduzível e possibilidade de rollback;
- reaproveitamento do dataset de avaliação já existente;
- separação clara entre evidência documental e preferência humana.

### Custos

- novas entidades, fila de revisão e worker de compilação;
- necessidade de taxonomia e julgamento de fontes na interface;
- latência entre o feedback e sua ativação;
- avaliação periódica e monitoramento de drift por tenant.

## Alternativas rejeitadas

- **Alterar ranking a cada clique:** instável, manipulável e difícil de auditar.
- **Indexar respostas corrigidas no RAG:** transforma opinião ou erro humano em
  falsa evidência e cria ciclos autorreferentes.
- **Fine-tuning automático por tenant:** custo e risco desproporcionais, sem
  resolver primeiro retrieval, roteamento e qualidade das fontes.
- **Usar feedback de todos os tenants em conjunto:** viola isolamento e pode
  transferir preferências ou conteúdo privado.
