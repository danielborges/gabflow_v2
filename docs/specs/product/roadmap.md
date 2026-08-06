# Roadmap

## Release 1 — Atendimento estruturado

- Cadastro de cidadãos e organizações.
- Solicitações multicanal.
- Categorias e subcategorias.
- Status, prioridade, responsável e SLA.
- Anexos, histórico e comentários.
- Notificações.
- Painel operacional.

### Evolução planejada — Diretório de cidadãos e organizações v2

- Agenda alfabética responsiva com pesquisa por identidade e contato.
- Cadastro e edição no fluxo da página, sem modal, com foto e captura por câmera.
- CPF único por tenant, alerta de homônimos e reaproveitamento de cadastro existente.
- Bairro e território derivados do endereço.
- Vínculo Search-Select entre cidadão responsável e organização.
- Histórico de solicitações, criação de solicitação no contexto do cidadão e navegação direta.
- Rastreabilidade de criação/alterações e marcador VIP.
- Ingestão assistida por WhatsApp e e-mail com envelope idempotente, resolvedor tenant-safe e fila de revisão humana. **Entregue no incremento 9.5, sem criação ou mesclagem automática.**
- Operação do cadastro assistido com responsável, SLA, métricas, confirmação campo a campo,
  vínculo transacional, proveniência e retenção minimizada. **Entregue no incremento 9.6,
  mantendo proibida a criação automática.**
- Gestão cartográfica com visualização da jurisdição, desenho e edição acessível de polígonos,
  múltiplas partes e aliases sincronizados. **Entregue no incremento 9.7.**

## Release 2 — Automação do atendimento

- Transcrição de áudio.
- OCR de documentos e imagens.
- Resumo automático.
- Classificação e sugestão de prioridade.
- Identificação de órgão competente.
- Detecção de solicitações semelhantes.
- Respostas sugeridas.

## Release 3 — Produção legislativa

- Templates de indicação, requerimento, ofício e pedido de informação.
- Criação de minuta a partir de solicitações.
- Fluxo de revisão e aprovação.
- Relação entre demanda e proposição.
- Catálogo de precedentes.

## Release 4 — Assistente RAG

- Base legislativa e institucional.
- Busca semântica.
- Respostas com citações.
- Controle de versão das fontes.
- Avaliação de relevância e confiança.
- Proteção contra prompt injection documental.

### Evolução RAG hierárquica

- Catálogo RAG Geral e administração global.
- RAG Privado alimentado por projeções autorizadas dos módulos.
- RLS, roles segregadas e constraints compostas.
- Políticas de distribuição e jurisdição.
- Recuperação federada global + privada.
- Versão fixada e fork privado.
- Conectores de APIs globais homologadas.
- Pipeline tenant-scoped de avaliação e melhoria por feedback.

### Evolução do conhecimento operacional

- **Entregue parcialmente:** solicitações, interações e minutas legislativas
  concluídas são projetadas de forma versionada no RAG Privado.
- **Entregue:** correção funcional do ranking sem corte por recência, com limiar por
  fonte, compatibilidade de embedding, fallback lexical e sem diversidade forçada.
- **Entregue:** PostgreSQL FTS + `pgvector`, índices GIN/HNSW por dimensão,
  sincronização automática dos vetores e fusão RRF tenant-safe.
- **Entregue:** contrato e registry versionado de projetores para solicitações e
  minutas legislativas, com allowlist e políticas de governança.
- **Entregue:** eventos explícitos V2 de criação, atualização, cancelamento,
  exclusão, anonimização, expiração e reconciliação, sem conteúdo sensível.
- **Entregue:** quarentena pré-indexação, estados operacionais completos,
  despublicação imediata, tombstone, purge físico e reprocessamento.
- **Entregue:** tombstone, purge LGPD, reconciliação e expiração periódica.
- **Entregue:** encaminhamentos e respostas oficiais, tramitação, OCR e
  transcrições revisados, atas concluídas e relatórios de fiscalização concluídos.
- **Entregue:** memórias temáticas agregadas e consultas estruturadas
  tenant-scoped para contagens, estados, prazos, médias e agrupamentos.
- **Entregue:** dataset e execução de avaliação por tenant com `precision@k`,
  `recall@k`, groundedness, precisão de citações, fontes desconexas e recusa.
- **Entregue:** roteamento automático entre o fluxo documental, estruturado e
  híbrido, com decisão e filtros auditáveis.
- **Entregue:** feedback imutável, taxonomia de falhas, julgamentos por fonte,
  validação, minimização, quarentena e moderação tenant-scoped.
- **Entregue:** curadoria explícita para o dataset, expected sources versionadas,
  hard negatives, expectativas de rota/filtros/recusa e invalidação automática.
- **Entregue:** compilação idempotente de sinais aprovados em artefatos candidatos
  versionados, limitados, reproduzíveis e com proveniência por feedback.
- **Entregue:** avaliação de candidato contra baseline, gates de regressão,
  aprovação, ativação tenant-scoped em canário, métricas online e rollback.
- **Entregue:** captura idempotente de consultas problemáticas em dataset de
  regressão tenant-scoped, com taxonomia, severidade, fontes esperadas,
  hard negatives e snapshot minimizado do baseline.
- **Entregue:** reranking neural listwise sobre o pool híbrido elegível, com
  contrato estruturado, proteção contra instruções nos documentos, explicabilidade
  e fallback para a ordem base.
- **Entregue:** entendimento documental determinístico, filtros temáticos
  pré-ranking, expansões controladas e fusão multi-query por RRF.
- **Entregue:** geração substantiva por afirmações, contrato fechado de fontes,
  validação cruzada das citações e recusa segura em caso de falha.
- **Entregue:** verificação semântica independente de entailment, calibração
  tenant-scoped de thresholds, avaliação contra baseline, rollout em canário e
  rollback por regressão operacional.
- **Entregue:** rollout automatizado `5% -> 20% -> 50% -> 100%`, baseline real
  fora do bucket, gates por etapa, promoção/rollback automáticos, lease renovável
  e acompanhamento administrativo tenant-scoped.
- **Entregue:** classificador NLI independente do gerador, provider HTTP
  dedicado, reranking adaptativo, contexto compacto, limites de tokens e
  telemetria/orçamento de latência por etapa.
- **Entregue no incremento 5.1:** threat model de conteúdo não confiável, correção
  do estado dos controles existentes, contrato JSON Schema e dataset adversarial v1
  com ataques multilíngues/ofuscados e controles benignos.
- **Entregue no incremento 5.2:** gateway único e fail-closed, contrato fechado de
  decisão, estado persistente e exposição segura para versões privadas/globais,
  fontes operacionais, feedback e consultas.
- **Entregue no incremento 5.3:** enforcement `CLEAN/ALLOW` pré-derivação e
  pré-publicação, quarentena privada/global, purge imediato, revisão humana
  vinculada ao checksum e reprocessamento auditável.
- **Entregue no incremento 5.4:** canonicalização limitada de Unicode, HTML,
  URL encoding, Base64, hexadecimal, espaçamento e tipoglicemia; classificador dedicado
  independente do gerador, contrato fechado, fail-closed e regressão adversarial executável.
- **Entregue no incremento 5.5:** ClamAV com assinaturas atualizáveis, varredura
  `INSTREAM` fail-closed, validação de MIME real, nova inspeção por checksum antes
  do parsing e sidecar de parsing sem rede, segredos, escrita ou capabilities.
- **Entregue no incremento 5.6:** revarredura assíncrona e retomável do acervo
  privado, global e dos anexos; invalidação fail-closed, reclassificação pela
  política vigente e purge de chunks, embeddings, OCR, transcrições e memórias
  operacionais derivadas.
- **Entregue no incremento 5.7:** validação independente da resposta final, bloqueio
  fail-closed de vazamento de instruções, segredos e ações não executadas,
  validação de citações/destinos, métricas tenant-scoped e rollout progressivo com
  promoção e rollback automáticos.
- **Entregue no incremento 5.8:** AES-256-GCM em repouso com chave derivada e AAD por
  tenant, versionamento/rotação pela revarredura do acervo e auditoria assíncrona
  das políticas RLS, `FORCE RLS` e roles de runtime `NOBYPASSRLS`.

## Release 5 — Inteligência territorial

- Geocodificação.
- Mapa de calor.
- Tendências por tema, região e período.
- Alertas de recorrência.
- Planejamento de visitas.
- Relatórios do mandato.

## Release 6 — Ecossistema e canais

- WhatsApp Business.
- E-mail.
- Formulário público.
- Redes sociais.
- Aplicativo móvel.
- Integração com sistemas legislativos e protocolos externos.
