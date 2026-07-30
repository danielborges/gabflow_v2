# Release 4.6 — Expansão do conhecimento operacional

## Status

Em implementação. A primeira etapa de correção funcional do retrieval e ranking
foi entregue. O contrato e registry de projetores também foram implementados. Os
eventos explícitos e o ciclo de vida completo das fontes operacionais foram
entregues. A expansão para encaminhamentos, tramitação, OCR/transcrição revisados,
agenda concluída e fiscalização concluída foi implementada. Memórias temáticas,
consultas estruturadas e avaliação de retrieval por tenant também foram entregues.
A migração de infraestrutura para busca vetorial indexada permanece planejada.

## Estado de partida

A implementação atual projeta no RAG Privado:

- solicitações e interações;
- minutas legislativas e suas versões, quando concluídas.

O fluxo existente usa outbox transacional, snapshot minimizado, hash idempotente,
versões imutáveis, ingestão assíncrona, proveniência e isolamento por tenant.

As fontes operacionais cobertas são solicitações, encaminhamentos e respostas de
órgãos, minutas, tramitações, OCR e transcrições revisados, atas de agenda
concluídas, relatórios de fiscalização concluídos e memórias temáticas agregadas.
Exclusão física, expiração sem nova alteração, despublicação e purge estão
cobertos para esses projetores.

## Objetivos

1. corrigir seleção e ranking antes de ampliar o volume indexado;
2. formalizar um registry e contrato de projetores por tipo de entidade;
3. emitir eventos explícitos de criação, atualização e exclusão nos serviços;
4. implementar quarentena pré-indexação e ciclo completo de retenção/purge;
5. ampliar fontes em lotes pequenos, medindo qualidade por tenant;
6. separar recuperação documental de consultas analíticas estruturadas.

## Sequência de entrega

### 4.6.1 — Qualidade e fundação

- **Entregue:** seleção de todos os chunks elegíveis em lotes, sem corte por
  recência antes do score;
- **Entregue:** pool limitado somente depois da avaliação de relevância;
- **Entregue:** tenant, ACL, vigência, estado operacional e retenção antes do
  ranking;
- **Entregue:** compatibilidade obrigatória entre modelos de embedding;
- **Entregue:** fallback lexical normalizado, sem comparar vetores incompatíveis;
- **Entregue:** reranking por relevância, autoridade e atualidade;
- **Entregue:** limiar aplicado individualmente a cada fonte citada;
- **Entregue:** remoção de diversidade forçada e limite de chunks por documento;
- **Planejado:** PostgreSQL FTS + pgvector com índices por modelo/dimensão e
  reindexação controlada;
- **Planejado:** filtros explícitos por módulo, entidade, tema, território e período;
- **Entregue:** registry de projetores e contrato canônico de projeção, com
  versão, proprietário, ações, allowlist, finalidade, base legal, ACL, retenção,
  quarentena e purge declarados;
- **Entregue:** sincronização e reconciliação resolvidas exclusivamente pelo
  registry, recusando tipos de entidade não registrados;
- **Entregue:** versão do projetor persistida na fonte operacional e registrada
  na proveniência e auditoria;
- **Entregue:** estados `PENDENTE`, `QUARENTENA`, `ERRO` e `EXCLUIDA`.

### Decisão de infraestrutura desta etapa

O schema atual armazena embeddings em JSON. A imagem PostgreSQL com PostGIS usada
pelo projeto não contém pgvector, e o modelo de produção e o fallback de testes
possuem dimensões diferentes. Por isso, a correção de qualidade preserva JSON e
SQLite e faz varredura exata em lotes. A migração pgvector será separada, com
dual-write, dimensão/modelo registrados, backfill, índices parciais e reindexação;
uma coluna `vector(768)` fixa não será introduzida silenciosamente.

### 4.6.2 — Ciclo de vida e LGPD

- **Entregue:** eventos `CREATE`, `UPDATE`, `CANCEL`, `DELETE`, `ANONYMIZE`,
  `RETENTION_EXPIRED` e `RECONCILE`, com contrato V2 sem conteúdo sensível;
- **Entregue:** módulo de origem, tipo, ID, ação, revisão de ordenação e versão do
  schema no outbox;
- **Entregue:** descarte idempotente de eventos repetidos ou fora de ordem pela
  revisão persistida na fonte operacional;
- **Entregue:** captura transacional de criação, atualização, cancelamento e
  exclusão, propagação de anonimização e emissor de expiração;
- **Entregue:** tombstone e despublicação imediata no mesmo commit que gera o
  evento destrutivo;
- **Entregue:** purge idempotente de chunks, embeddings, texto extraído, versões,
  documento e objeto privado;
- **Entregue:** sweep periódico de retenção no scheduler do worker;
- **Entregue:** falha definitiva materializada como `ERRO`, preservando a versão
  vigente anterior;
- **Entregue:** listagem administrativa tenant-scoped e reprocessamento de fontes;
- **Entregue:** quarentena antes da criação do arquivo, chunks ou embeddings.

### 4.6.3 — Expansão por módulo

Ordem inicial:

1. **Entregue:** encaminhamentos e respostas oficiais;
2. **Entregue:** tramitação legislativa;
3. **Entregue:** OCR e transcrições aceitos ou revisados;
4. **Entregue:** atas de agenda concluídas;
5. **Entregue:** relatórios de fiscalização concluídos.

Cadastros de cidadãos, credenciais, configurações, auditoria bruta e saídas de IA
não revisadas permanecem fora do RAG.

O projetor `REQUEST_FORWARDING` usa somente protocolo e título da solicitação,
nome do órgão, protocolo externo, observações, estado, prazo e resposta oficial.
Contatos do órgão e cadastros pessoais não integram a allowlist. Mudanças no
encaminhamento, na solicitação-pai ou no nome do órgão disparam nova projeção; o
cancelamento ou a anonimização da origem também alcança a fonte derivada.

Os projetores adicionados são:

- `LEGISLATIVE_TRAMITATION`, somente para minutas aprovadas e protocoladas;
- `DOCUMENT_OCR` e `AUDIO_TRANSCRIPTION`, somente após revisão humana aceita ou
  editada, usando exclusivamente o texto revisado;
- `AGENDA_EVENT`, somente após realização e registro de ata;
- `OVERSIGHT_ACTION`, somente após conclusão e registro do relatório.

Participantes, fotos, responsáveis, contatos cadastrais e conteúdo automático não
revisado permanecem fora das allowlists.

### 4.6.4 — Inteligência híbrida

- **Entregue:** endpoint explícito de consultas estruturadas tenant-scoped para
  contagens, prazos, estados, médias e agrupamentos reproduzíveis;
- **Entregue:** memórias temáticas agregadas por tema, território e período, com
  limiar mínimo configurável e sem protocolos ou dados pessoais;
- **Entregue:** registro do método, filtros, período e base de cálculo;
- **Entregue:** dataset de perguntas reais por tenant com documentos esperados ou
  expectativa de recusa;
- **Entregue:** execução versionada por `k`, registrando `precision@k`,
  `recall@k`, groundedness, precisão de citações, fontes desconexas e acurácia de
  recusa;
- **Entregue:** roteador automático e determinístico de intenção documental,
  estruturada ou híbrida no endpoint conversacional único, com decisão, motivos,
  filtros e resultado estruturado persistidos.

## Critérios de conclusão

- catálogo aprovado das fontes elegíveis por módulo;
- sincronização incremental e reconciliação convergem para o mesmo estado;
- criação, atualização, cancelamento, exclusão, anonimização e expiração testadas;
- nenhuma fonte cruza tenant ou ACL;
- conteúdo malicioso não integra o contexto de geração;
- purge comprovado no banco, chunks e armazenamento;
- proveniência reproduzível até a entidade de origem;
- avaliação de `precision@k`, `recall@k`, citações desconexas e recusa por tenant;
- SLO de frescor e backlog monitorados.
