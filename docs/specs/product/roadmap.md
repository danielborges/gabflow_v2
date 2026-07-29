# Roadmap

## Release 1 — Atendimento estruturado

- Cadastro de cidadãos e organizações.
- Solicitações multicanal.
- Categorias e subcategorias.
- Status, prioridade, responsável e SLA.
- Anexos, histórico e comentários.
- Notificações.
- Painel operacional.

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
- **Próximo incremento de infraestrutura:** PostgreSQL FTS + pgvector com índices
  por modelo/dimensão e reindexação controlada.
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
