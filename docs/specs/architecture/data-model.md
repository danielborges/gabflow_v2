# Modelo de Dados Conceitual

## Tenant
- id
- nome
- tipo
- timezone
- configurações
- status

## Usuario
- id
- tenant_id
- nome
- email
- perfil
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
