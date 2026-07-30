# Modelo de Dados Conceitual

## Tenant
- id
- nome
- tipo
- timezone
- configurações
- status
- chief_of_staff_id

## Usuario
- id
- tenant_id
- nome
- email
- perfil
- funcoes_designadas
- status
- mfa_enabled

## Cidadao
- id
- tenant_id
- nome
- nome_social
- contatos
- preferências
- consentimentos
- flags_privacidade

## Organizacao
- id
- tenant_id
- tipo
- nome
- contatos
- território

## Solicitacao
- id
- tenant_id
- protocolo
- cidadao_id
- organizacao_id
- origem
- título
- descrição
- categoria_id
- subcategoria_id
- prioridade
- impacto
- urgência
- status
- responsável_id
- latitude
- longitude
- bairro_id
- data_abertura
- prazo
- data_encerramento
- motivo_encerramento

## Interacao
- id
- solicitacao_id
- tipo
- canal
- direção
- conteúdo
- autor
- data
- visibility

## Anexo
- id
- tenant_id
- entidade_tipo
- entidade_id
- arquivo
- mime_type
- hash
- classificação
- dados_extraídos

## Encaminhamento
- id
- solicitacao_id
- destino
- responsável
- status
- prazo
- resposta

## Tarefa
- id
- tenant_id
- entidade
- responsável
- status
- prioridade
- prazo

## Proposicao
- id
- tenant_id
- tipo
- título
- conteúdo
- status
- versão
- protocolo_externo

## DocumentoFonte
- id
- tenant_id
- título
- tipo
- órgão
- vigência
- versão
- nível_acesso
- checksum
- status_indexacao

## ExecucaoIA
- id
- tenant_id
- caso_uso
- modelo
- prompt_version
- entrada_hash
- saída
- confiança
- status_revisão
- custo
- latência

## Insight
- id
- tenant_id
- tipo
- período
- filtros
- resultado
- confiança
- método
- gerado_em

## Auditoria
- id
- tenant_id
- usuário
- ação
- entidade
- entidade_id
- antes
- depois
- data
- ip

## ColecaoConhecimentoGlobal
- id
- nome
- descricao
- politica_distribuicao
- jurisdicao
- status
- criado_por
- publicado_em

## DocumentoGlobal
- id
- colecao_id
- titulo
- tipo
- orgao
- jurisdicao
- proveniencia
- nivel_confianca
- status

## VersaoDocumentoGlobal
- id
- documento_id
- versao
- vigencia_inicio
- vigencia_fim
- checksum
- arquivo_ou_snapshot
- status_indexacao
- status_publicacao
- modelo_embedding

## FonteApiGlobal
- id
- colecao_id
- nome
- base_url
- allowlist_rotas
- metodos_permitidos
- referencia_segredo
- politica_sincronizacao
- status
- ultima_sincronizacao

## ConcessaoConhecimentoGlobal
- id
- tenant_id
- colecao_id
- modo_atualizacao
- versao_fixada_id
- concedido_por
- justificativa
- vigencia_inicio
- vigencia_fim
- status

Esta entidade é tenant-scoped e protegida por RLS, embora referencie uma coleção do
catálogo global.

## ColecaoConhecimentoPrivado
- id
- tenant_id
- nome
- finalidade
- nivel_acesso
- politica_retencao
- status

## DocumentoPrivado
- id
- tenant_id
- colecao_id
- titulo
- tipo
- orgao
- nivel_acesso
- fonte_modulo
- entidade_origem_id
- documento_global_origem_id
- versao_global_origem_id
- status

## FonteConhecimentoOperacional
- id
- tenant_id
- modulo_origem
- entidade_tipo
- entidade_id
- versao_projetor
- revisao_origem
- finalidade
- base_legal
- nivel_acesso
- politica_acl
- retencao_ate
- estado
- motivo_elegibilidade
- hash_conteudo
- versao_logica
- documento_privado_id
- versao_privada_atual_id
- ultima_projecao_em
- codigo_erro
- mensagem_erro
- tentativas
- quarentena_em
- excluida_em
- purge_concluido_em
- tombstone_hash

A origem é única por `tenant_id`, módulo, tipo e ID da entidade. Relações com
documento e versão privada usam foreign keys compostas com `tenant_id`. O registro
preserva somente decisão e identificadores após purge; conteúdo sensível não entra
na auditoria nem no evento de sincronização.

## VersaoDocumentoPrivado
- id
- tenant_id
- documento_id
- versao
- vigencia_inicio
- vigencia_fim
- checksum
- storage_key
- status_indexacao
- modelo_embedding

## ChunkGlobal
- id
- versao_global_id
- posicao
- conteudo
- pagina_inicio
- pagina_fim
- secao
- checksum
- embedding
- embedding_vector (`vector`, sincronizado por trigger)
- search_vector (`tsvector`, gerado em português)
- modelo_embedding

## ChunkPrivado
- id
- tenant_id
- versao_privada_id
- posicao
- conteudo
- pagina_inicio
- pagina_fim
- secao
- checksum
- embedding
- embedding_vector (`vector`, sincronizado por trigger)
- search_vector (`tsvector`, gerado em português)
- modelo_embedding

Os dois escopos usam GIN sobre `search_vector` e HNSW de distância cosseno
sobre as dimensões atualmente suportadas (128 e 768). A coluna vetorial não
possui dimensão fixa para permitir coexistência de modelos; consultas e índices
sempre filtram e convertem explicitamente pela dimensão e pelo modelo.

## ConsultaAssistente
- id
- tenant_id
- usuario_id
- consulta
- resposta
- metodo
- motivos_roteamento
- filtros_aplicados
- resultado_estruturado
- grounded
- fontes_globais
- fontes_privadas
- modelo
- prompt_version
- artefatos_aprendizado
- criada_em

## FeedbackAssistente
- id
- tenant_id
- consulta_id
- avaliacao
- motivos
- comentario
- resposta_corrigida
- metodo_esperado
- filtros_esperados
- estado
- hash_conteudo
- revisao_anterior_id
- revisado_por
- revisado_em
- moderado_por
- moderado_em
- modo_moderacao
- regra_moderacao
- decisao_moderacao
- criado_em

Cada nova avaliação cria uma revisão imutável. `revisao_anterior_id` forma a cadeia
de substituição sem apagar o histórico. Comentário e correção permanecem
não confiáveis até aprovação e não são fontes RAG.

## JulgamentoFonteFeedbackRag
- id
- tenant_id
- feedback_id
- documento_id
- versao_id
- chunk_id
- escopo
- julgamento
- motivo
- posicao_original
- criado_em

Documento, versão ou chunk devem pertencer às fontes registradas na consulta. O
julgamento é `RELEVANTE`, `IRRELEVANTE` ou `AUSENTE`; no último caso, a fonte
esperada pode ser indicada por documento/versão visível ao mesmo tenant.

## ExecucaoAprendizadoRag
- id
- tenant_id
- janela_inicio
- janela_fim
- configuracao
- configuracao_hash
- baseline
- total_feedbacks
- total_aprovados
- total_quarentena
- metricas
- estado
- erro
- iniciada_por
- criada_em
- concluida_em

## ArtefatoAprendizadoRag
- id
- tenant_id
- execucao_id
- tipo
- versao
- payload
- payload_hash
- feedbacks_origem
- baseline
- metricas_antes
- metricas_depois
- detalhes_avaliacao
- estado
- aprovado_por
- aprovado_em
- ativado_por
- ativado_em
- modo_ativacao
- percentual_canario
- metricas_online
- substituido_por_id
- revogado_em
- motivo_revogacao
- criado_em

Tipos iniciais: `RERANK_PROFILE`, `ROUTING_EXAMPLES`, `EVALUATION_CASES` e
`ANSWER_EXEMPLARS`. Existe no máximo um artefato `ATIVO` por tenant e tipo.
O payload usa schema fechado e não contém comentário bruto.

## FeedbackArtefatoAprendizadoRag
- id
- tenant_id
- artefato_id
- feedback_id
- contribuicao
- criado_em

A relação preserva a proveniência de cada sinal por foreign keys compostas com
`tenant_id`. Na etapa 4.7.3, todo artefato nasce em `CANDIDATO`; a compilação não
o aplica ao retrieval, roteamento ou geração.

## MemoriaTematicaRag
- id
- tenant_id
- tema
- territorio
- periodo_inicio
- periodo_fim
- total_solicitacoes
- total_resolvidas
- total_prioridade_alta
- sintese
- gerada_por
- gerada_em

A chave de agregação é única por tenant, tema, território e período. Grupos abaixo
do limiar mínimo não originam documento privado.

## PerguntaAvaliacaoRag
- id
- tenant_id
- pergunta
- documentos_esperados
- fontes_esperadas
- hard_negatives
- espera_recusa
- metodo_esperado
- filtros_esperados
- observacoes
- origem (`MANUAL`, `FEEDBACK` ou `REGRESSAO`)
- motivos_falha
- severidade
- tags
- baseline_snapshot
- baseline_capturado_em
- consulta_origem_id
- ativa
- feedback_origem_id
- curada_por
- curada_em
- motivo_desativacao
- criada_por
- criada_em

Casos `REGRESSAO` são únicos por `tenant_id + consulta_origem_id`. O snapshot
registra apenas hashes, identificadores, scores, método, filtros e metadados
necessários para reproduzir o baseline; resposta e trechos brutos não são
duplicados. Fontes marcadas como irrelevantes precisam ter sido retornadas na
consulta original, e fontes esperadas devem estar visíveis ao mesmo tenant.

Casos manuais mantêm `feedback_origem_id` nulo. Casos curados possuem no máximo
um registro por feedback e usam FK composta com `tenant_id`. Feedback que deixe o
estado `APROVADO`, ou referência eliminada/inacessível, desativa o caso antes da
próxima execução sem apagar seu histórico.

## ExecucaoAvaliacaoRag
- id
- tenant_id
- k
- total_perguntas
- precision_at_k
- recall_at_k
- groundedness
- precisao_citacoes
- taxa_fontes_desconexas
- acuracia_recusa
- acuracia_roteamento
- acuracia_filtros
- taxa_hard_negatives
- resultados_por_pergunta
- criada_por
- criada_em

## Invariantes de tenant

- Toda entidade privada possui `tenant_id` não nulo.
- Relacionamentos privados usam foreign keys compostas que incluem `tenant_id`.
- Uma consulta privada sem contexto transacional de tenant é negada.
- `tenant_id` não pode ser alterado por update.
- Conteúdo global não usa `tenant_id = NULL` em tabelas privadas; ele reside em
  domínio próprio.
- Forks preservam origem global, mas passam a obedecer exclusivamente ao tenant.
- Chunks globais e privados residem em domínios distintos e são identificados por
  escopo nas citações e auditorias.
- Feedback, julgamentos, execuções e artefatos de aprendizado usam foreign keys
  compostas com `tenant_id`; cache e worker também particionam por tenant.
