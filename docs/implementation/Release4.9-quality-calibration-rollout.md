# Release 4.9 — Avaliação, calibração e rollout controlado

## Incremento 4.9.1

Status: implementado.

O incremento transforma os thresholds de qualidade do RAG em um artefato
tenant-scoped, versionado e auditável. O endpoint
`POST /api/v1/assistente/calibracoes` aceita somente os parâmetros permitidos:

- limiar de candidatura do retrieval;
- evidência documental mínima;
- limiar do reranker neural;
- suporte lexical mínimo das citações;
- confiança mínima do verificador semântico.

A aplicação completa os valores omitidos com o perfil efetivo, valida intervalos
e consistência e cria o candidato com resposta HTTP `202`. A comparação entre
baseline e candidato é executada de forma assíncrona na fila RAG, pode ser
acompanhada pelos endpoints de execuções e artefatos e é retomável conforme a
política do outbox. Ambos executam no mesmo dataset do tenant. A
avaliação mede também latência p95, rejeita regressão relativa acima da tolerância
e bloqueia candidato que exceda o SLO absoluto. O
artefato `QUALITY_PROFILE` é aprovado somente quando não ultrapassa a tolerância
de regressão e melhora ao menos uma métrica-alvo, salvo justificativa humana
explícita para ausência de melhora. Regressões continuam bloqueantes.

## Entailment semântico

Depois da validação determinística e lexical, cada afirmação e a evidência de
seus chunks citados formam um caso isolado para um segundo modelo. O verificador:

- não recebe acesso ao banco, ferramentas ou fontes adicionais;
- usa contrato JSON fechado com o conjunto exato de casos;
- verifica sujeitos, datas, números, modalidade normativa, negações e
  contradições;
- não pode aprovar uma afirmação reprovada pelos controles determinísticos;
- falha de modo fechado por padrão.

A resposta somente é fundamentada quando todas as afirmações passam pelos dois
níveis. Modelo, prompt, confiança, contradição, justificativa e fallback são
registrados dentro de `geracao.validacaoCruzada.entailmentSemantico`.

## Rollout e rollback

O perfil aprovado utiliza o ciclo já estabelecido de artefatos:

1. ativação inicial em canário por percentual;
2. bucket determinístico por tenant, artefato e usuário;
3. registro do perfil que influenciou cada consulta;
4. expansão monotônica até 100%;
5. rollback manual ou automático para a versão anterior.

Além do feedback negativo, perfis de qualidade monitoram taxa de fallback da
geração e taxa de rejeição semântica. Depois da amostra mínima configurada, a
violação de qualquer gate revoga o candidato automaticamente e restaura a versão
anterior elegível.

## Incremento 4.9.2 — rollout progressivo automatizado

Status: implementado.

Uma calibração aprovada inicia automaticamente o rollout configurado, por padrão
em `5% -> 20% -> 50% -> 100%`. Cada etapa possui janela e amostra mínimas
independentes. O worker agenda avaliações idempotentes e somente avança quando as
taxas de fallback, rejeição semântica, recusa e feedback negativo permanecem
dentro dos limites absolutos e da tolerância de regressão contra o baseline.

Durante o canário, usuários fora do bucket continuam utilizando a versão anterior
do perfil, em vez dos defaults globais. Ao validar a etapa de 100%, o perfil é
marcado como promovido. Qualquer gate reprovado ou falha permanente do
monitoramento revoga o candidato e restaura atomicamente a versão anterior.

`GET /api/v1/assistente/calibracoes` expõe o perfil ativo e o histórico
tenant-scoped: etapa, percentual, métricas, motivos, próxima avaliação e decisão.
Jobs longos renovam seu lease no banco enquanto estão em execução, evitando
reprocessamento concorrente após o timeout original do lock.

## Incremento 4.9.3 — latência e NLI independente

Status: implementado.

O verificador semântico passou a possuir provider, endpoint, modelo, timeout e
prompt próprios. Por padrão, o GabFlow usa `qwen2.5:0.5b` no Ollama e exige que
o modelo NLI seja diferente do gerador. Também existe o provider `http`, cujo
contrato fechado recebe pares `premise`/`hypothesis` em `/v1/nli` e aceita
somente os rótulos `ENTAILMENT`, `CONTRADICTION` e `NEUTRAL`. Indisponibilidade,
modelo compartilhado ou resposta fora do contrato continuam causando recusa
quando a política fail-closed está ativa.

O caminho crítico foi reduzido por:

- reranker neural adaptativo para candidato único ou líder híbrido inequívoco;
- contexto limitado a três fontes e 900 caracteres por fonte;
- no máximo cinco afirmações e limites explícitos de tokens/contexto;
- evidência NLI limitada aos chunks efetivamente citados;
- timeouts separados de 8 s para reranking, 20 s para geração e 8 s para NLI;
- manutenção dos modelos carregados no Ollama por `keep_alive`;
- telemetria por etapa para recuperação, geração, validação e NLI.

Cada resposta expõe `latenciaEtapas`, incluindo orçamento, total e eventual
estouro. Rollouts medem a taxa de estouro do orçamento como gate online.

Como o caminho completo pode envolver reranking, geração e verificação em
chamadas distintas, o gateway e o servidor possuem orçamento explícito de 180
segundos. Esse limite evita 504 prematuro, mas não substitui o gate de latência:
configurações lentas continuam inelegíveis para promoção.

## Configuração

- `RAG_ENTAILMENT_ENABLED`
- `RAG_ENTAILMENT_PROVIDER`
- `RAG_ENTAILMENT_MODEL`
- `RAG_ENTAILMENT_PROMPT_VERSION`
- `RAG_ENTAILMENT_TIMEOUT_SECONDS`
- `RAG_ENTAILMENT_MIN_SCORE`
- `RAG_ENTAILMENT_FAIL_CLOSED`
- `RAG_QUALITY_ONLINE_MIN_SAMPLES`
- `RAG_QUALITY_ONLINE_MAX_FALLBACK_RATE`
- `RAG_QUALITY_ONLINE_MAX_SEMANTIC_REJECTION_RATE`
- `RAG_QUALITY_ONLINE_MAX_REFUSAL_RATE`
- `RAG_QUALITY_ROLLOUT_STAGES`
- `RAG_QUALITY_ROLLOUT_MIN_SAMPLES`
- `RAG_QUALITY_ROLLOUT_MIN_WINDOW_SECONDS`
- `RAG_QUALITY_ROLLOUT_CHECK_INTERVAL_SECONDS`
- `RAG_QUALITY_ROLLOUT_MAX_RATE_REGRESSION`
- `WORKER_HEARTBEAT_SECONDS`
- `RAG_NEURAL_RERANK_ADAPTIVE_ENABLED`
- `RAG_NEURAL_RERANK_SKIP_MIN_SCORE`
- `RAG_NEURAL_RERANK_SKIP_MIN_MARGIN`
- `RAG_NEURAL_RERANK_MAX_TOKENS`
- `RAG_ANSWER_MAX_TOKENS`
- `RAG_NLI_ENABLED`
- `RAG_NLI_PROVIDER`
- `RAG_NLI_BASE_URL`
- `RAG_NLI_MODEL`
- `RAG_NLI_PROMPT_VERSION`
- `RAG_NLI_TIMEOUT_SECONDS`
- `RAG_NLI_MIN_SCORE`
- `RAG_NLI_FAIL_CLOSED`
- `RAG_NLI_REQUIRE_DISTINCT_MODEL`
- `RAG_NLI_MAX_EVIDENCE_CHARS`
- `RAG_NLI_MAX_TOKENS`
- `RAG_QUERY_LATENCY_BUDGET_MS`
- `RAG_QUALITY_ONLINE_MAX_LATENCY_BUDGET_RATE`
