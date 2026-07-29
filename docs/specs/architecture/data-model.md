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
- modelo_embedding

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
- criada_em

## FeedbackAssistente
- id
- tenant_id
- consulta_id
- avaliacao
- comentario
- resposta_corrigida
- revisado_por
- revisado_em

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
- espera_recusa
- observacoes
- ativa
- criada_por
- criada_em

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
