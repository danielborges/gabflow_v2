# language: pt
Funcionalidade: Assistente RAG hierárquico

  Cenário: Ingerir documento privado versionado
    Dado que um gestor selecionou PDF, DOCX, TXT ou imagem permitida
    Quando informar tipo, órgão, acesso, versão, vigência e finalidade
    Então o sistema deve associar documento, versão, chunks e arquivo ao tenant
    E deve validar o arquivo e registrar seu checksum
    E deve extrair texto nativo ou aplicar OCR local
    E deve avaliar malware, PII e risco de prompt injection
    E deve criar fragmentos com página e gerar embeddings
    E deve registrar o processamento de forma assíncrona e auditável

  Cenário: Negar consulta privada sem contexto de tenant
    Dado que uma transação não possui o contexto app.tenant_id
    Quando tentar consultar documentos, versões, chunks ou feedback privado
    Então o banco deve negar por padrão
    E nenhum dado privado deve ser retornado

  Cenário: Impedir acesso cruzado mesmo sem filtro da aplicação
    Dado que existem documentos privados dos tenants A e B
    E a conexão está no contexto do tenant A
    Quando uma consulta sem filtro explícito de tenant acessar a tabela privada
    Então somente linhas do tenant A podem ser retornadas
    E uma inserção ou atualização apontando para o tenant B deve falhar

  Cenário: Não vazar contexto pelo pool de conexões
    Dado que uma conexão processou uma transação do tenant A
    Quando a mesma conexão for reutilizada em uma transação do tenant B
    Então o contexto anterior não deve permanecer ativo
    E a consulta deve retornar somente dados do tenant B

  Cenário: Processar ingestão privada no worker
    Dado que existe um evento de ingestão associado ao tenant A
    Quando o worker iniciar o processamento
    Então deve ativar o tenant A antes de carregar a versão privada
    E deve rejeitar aggregate cuja versão pertença a outro tenant

  Cenário: Governar versões de fonte privada
    Dado que um documento privado possui uma versão indexada
    Quando o gestor publicar essa versão como vigente
    Então outra versão vigente deve passar para histórica
    E o sistema deve distinguir rascunho, vigente, histórico e revogado
    E deve preservar arquivo, checksum, vigência e modelo de embeddings

  Cenário: Ingerir automaticamente informação interna elegível
    Dado que o tenant criou ou atualizou uma entidade coberta por um projetor registrado
    E a informação é elegível conforme finalidade, base legal, retenção e sigilo
    Quando o evento interno for processado
    Então uma fonte privada versionada deve ser criada ou atualizada
    E os chunks devem permanecer exclusivamente no tenant
    E a entidade e versão de origem devem ser preservadas
    E o evento não deve transportar o conteúdo sensível da entidade

  Cenário: Não ingerir informação interna inelegível
    Dado que uma informação foi excluída por minimização, retenção, base legal ou sigilo
    Quando o pipeline privado avaliar o evento
    Então o conteúdo não deve ser enviado ao modelo nem indexado
    E a decisão deve ser auditada sem copiar o dado sensível para o log

  Cenário: Projetar encaminhamento e resposta oficial minimizados
    Dado que uma solicitação foi encaminhada para um órgão externo
    Quando o gabinete registrar o encaminhamento ou a resposta oficial
    Então uma fonte privada REQUEST_FORWARDING deve ser criada ou versionada
    E deve conter somente os campos autorizados do encaminhamento, da solicitação e do órgão
    E contatos do órgão e dados cadastrais do cidadão não devem integrar o snapshot
    E o cancelamento ou a anonimização da solicitação deve alcançar a fonte derivada

  Esquema do Cenário: Publicar somente conteúdo operacional aprovado
    Dado que existe uma entidade do tipo "<tipo>"
    Quando ela atingir o estado "<estado>"
    Então o projetor "<projetor>" deve criar uma fonte privada versionada
    E conteúdo automático não revisado, fotos e listas de pessoas não devem integrar o snapshot

    Exemplos:
      | tipo                         | estado                 | projetor                 |
      | tramitação legislativa       | minuta protocolada      | LEGISLATIVE_TRAMITATION  |
      | OCR                          | aceito ou editado       | DOCUMENT_OCR              |
      | transcrição                  | aceita ou editada       | AUDIO_TRANSCRIPTION       |
      | compromisso de agenda        | realizado com ata       | AGENDA_EVENT              |
      | relatório de fiscalização    | concluído com relatório | OVERSIGHT_ACTION          |

  Cenário: Gerar memória temática sem expor indivíduos
    Dado que um tenant possui solicitações agrupáveis por tema, território e período
    Quando o gestor reconstruir as memórias temáticas
    Então somente grupos acima do limiar mínimo devem ser publicados
    E a memória deve conter apenas contagens e síntese agregada
    E protocolos, cidadãos e conteúdo individual não devem integrar o agregado

  Cenário: Consultar indicador estruturado
    Dado que o usuário está autenticado em um tenant
    Quando consultar uma contagem agrupada por tema e período
    Então o resultado deve informar o método ESTRUTURADO
    E deve registrar dataset, métrica, agrupamento, filtros e período
    E nenhuma linha de outro tenant deve participar do cálculo

  Cenário: Avaliar retrieval com perguntas reais do tenant
    Dado que o tenant cadastrou perguntas com documentos esperados ou expectativa de recusa
    Quando executar a avaliação com um valor de k
    Então devem ser persistidos precision@k, recall@k e groundedness
    E devem ser persistidas precisão das citações, fontes desconexas e acurácia de recusa
    E perguntas, documentos e execuções não devem cruzar tenants

  Cenário: Recuperar candidatos por FTS e pgvector
    Dado que existem fontes antigas e recentes elegíveis no tenant
    Quando uma pergunta documental for consultada
    Então o PostgreSQL deve formar candidatos por busca textual e vetorial
    E deve fundir as posições dos canais por Reciprocal Rank Fusion
    E somente embeddings do mesmo modelo e dimensão devem ser comparados
    E a data de indexação não deve eliminar uma fonte antes da relevância
    E ACL, vigência, retenção, publicação global e tenant devem ser filtrados no banco

  Cenário: Continuar operando quando o embedding estiver indisponível
    Dado que o provedor de embeddings não respondeu
    Quando a consulta documental for executada
    Então o canal PostgreSQL FTS deve continuar disponível
    E nenhuma comparação vetorial incompatível deve ser realizada
    E a resposta deve informar o fallback lexical

  Cenário: Capturar consulta problemática no dataset de regressão
    Dado que uma consulta do tenant retornou uma fonte desconexa
    Quando o gestor informar a fonte esperada, a fonte irrelevante e o motivo da falha
    Então deve ser criado um caso de origem REGRESSAO vinculado à consulta
    E o baseline deve preservar identificadores, scores, rota, filtros e hashes
    E o baseline não deve armazenar a resposta nem os trechos recuperados
    E repetir a captura da mesma consulta deve retornar o mesmo caso

  Cenário: Impedir contaminação e alteração dos sinais de regressão
    Dado que uma consulta problemática pertence a outro tenant
    Quando o gestor tentar capturá-la como caso de regressão
    Então o sistema deve responder como recurso não encontrado
    E uma fonte irrelevante deve ter participado da consulta original
    E pergunta, expectativas, motivos e baseline devem permanecer imutáveis

  Cenário: Reprocessar evento operacional de forma idempotente
    Dado que a versão canônica de uma entidade já foi projetada e indexada
    Quando o mesmo evento for entregue novamente ou fora de ordem
    Então o worker deve reler a entidade no contexto do tenant
    E não deve criar nova versão quando o hash material não mudou
    E deve permanecer somente uma versão vigente

  Esquema do Cenário: Propagar eliminação da origem
    Dado que uma fonte operacional privada está vigente
    E a política de retenção determina eliminação dos artefatos derivados
    Quando a origem sofrer "<acao>"
    Então a fonte deve deixar de participar da recuperação imediatamente
    E chunks, embeddings, texto extraído, versões derivadas e objeto privado devem ser purgados
    E a auditoria remanescente não deve conter o conteúdo descartado

    Exemplos:
      | acao                  |
      | exclusão              |
      | anonimização          |
      | expiração de retenção |

  Cenário: Despublicar fonte operacional cancelada
    Dado que uma fonte operacional privada está vigente
    Quando sua entidade de origem for cancelada
    Então a fonte deve deixar de participar da recuperação imediatamente
    E os artefatos devem seguir a retenção configurada para esse tipo de dado

  Cenário: Colocar projeção operacional suspeita em quarentena
    Dado que um texto originado em módulo contém instrução para alterar o comportamento do modelo
    Quando o projetor avaliar a entidade antes de gerar embeddings
    Então a fonte deve ser colocada no estado QUARENTENA
    E a instrução maliciosa não deve integrar chunks publicados
    E a decisão deve ser auditada sem registrar o conteúdo perigoso

  Cenário: Materializar erro definitivo de sincronização
    Dado que o processamento operacional esgotou suas retentativas
    Quando o worker encerrar a tentativa
    Então a fonte deve ser marcada no estado ERRO
    E o administrador do tenant deve poder identificar e reprocessar a falha
    E a versão anterior válida não deve ser substituída por conteúdo incompleto

  Cenário: Reconciliar fontes operacionais
    Dado que existem entidades criadas antes da captura automática ou fontes divergentes
    Quando a reconciliação periódica for executada
    Então o estado projetado deve convergir para o estado canônico do tenant
    E fontes órfãs ou expiradas devem ser despublicadas
    E o processamento deve ser idempotente

  Cenário: Publicar coleção no RAG Geral
    Dado que um administrador global de conhecimento cadastrou uma coleção
    E informou jurisdição, vigência e política de distribuição
    Quando publicar uma versão validada
    Então a versão deve ficar disponível somente aos tenants elegíveis
    E usuários de tenant devem possuir somente leitura
    E documento, versão, checksum e publicação devem ser auditados

  Esquema do Cenário: Distribuir coleção global
    Dado que uma coleção possui política "<politica>"
    Quando um tenant elegível for criado ou consultar suas concessões
    Então o acesso deve seguir o comportamento "<comportamento>"

    Exemplos:
      | politica             | comportamento                                  |
      | OBRIGATORIA          | habilitada automaticamente                     |
      | PADRAO               | habilitada com possibilidade de desativação    |
      | OPCIONAL             | depende de adesão do tenant                     |
      | DIRECIONADA          | depende de concessão explícita                  |
      | RESTRITA_JURISDICAO  | depende da jurisdição e tipo de casa            |
      | PRIVADA_PLATAFORMA   | indisponível aos usuários de tenant             |

  Cenário: Fixar versão global
    Dado que um tenant possui acesso a uma coleção global
    Quando o administrador do tenant fixar uma versão publicada
    Então consultas futuras devem utilizar essa versão até nova aprovação
    E a decisão deve ser auditada

  Cenário: Criar fork privado de documento global
    Dado que um tenant possui acesso a uma versão global
    Quando um gestor criar um fork privado
    Então uma nova fonte privada deve ser criada para o tenant
    E deve preservar documento, versão e checksum de origem
    E alterações privadas não devem modificar o catálogo global

  Cenário: Recuperar conhecimento global e privado
    Dado que o usuário está autenticado em um tenant ativo
    E o contexto transacional do tenant foi configurado
    E existem fontes globais autorizadas e fontes privadas relevantes
    Quando o usuário realizar uma consulta
    Então o sistema deve recuperar os dois escopos separadamente
    E deve aplicar acesso, jurisdição, vigência e finalidade antes do reranking
    E deve combinar e reranquear os resultados
    E cada citação deve informar escopo, coleção, versão, checksum e origem

  Cenário: Não forçar fonte desconexa para diversificar escopos
    Dado que apenas o escopo privado possui fonte acima do limiar de evidência
    E o escopo global possui documentos semanticamente fracos
    Quando o sistema reranquear os candidatos
    Então deve retornar somente as fontes acima do limiar
    E não deve incluir documento global apenas para representar os dois escopos

  Esquema do Cenário: Rotear consulta pelo método adequado
    Dado que o usuário está autenticado em um tenant
    Quando fizer a pergunta "<pergunta>"
    Então o assistente deve usar o método "<metodo>"
    E deve registrar método, filtros, período e fontes aplicáveis

    Exemplos:
      | pergunta                                                       | metodo      |
      | Quais argumentos aparecem nos pedidos sobre iluminação?        | DOCUMENTAL  |
      | Quantas solicitações de iluminação existem por bairro?         | ESTRUTURADO |
      | Quais temas recorrentes podem fundamentar uma indicação?       | HIBRIDO     |

  Cenário: Não usar fonte global incompatível com a jurisdição
    Dado que uma norma global é restrita a outra jurisdição
    Quando o tenant realizar uma consulta semanticamente semelhante
    Então essa norma não deve compor o contexto

  Cenário: Não há evidência suficiente em nenhum escopo
    Dado que a recuperação global e privada não encontrou fontes confiáveis
    Quando o assistente elaborar a resposta
    Então deve informar que não encontrou fundamento suficiente
    E não deve apresentar uma resposta conclusiva

  Cenário: Colocar documento malicioso em quarentena durante a ingestão
    Dado que uma fonte contém texto tentando alterar o comportamento do modelo
    Quando a fonte for avaliada antes da indexação
    Então a versão deve ser colocada no estado QUARENTENA
    E nenhum chunk dessa versão deve ser publicado

  Cenário: Sanitizar instrução maliciosa detectada na recuperação
    Dado que uma fonte legada recuperada contém texto tentando alterar o comportamento do modelo
    Quando o contexto de geração for montado
    Então o texto deve ser tratado apenas como conteúdo
    E a instrução contida na fonte deve ser removida ou neutralizada
    E a instrução maliciosa não deve integrar o contexto de geração
    E o risco deve ser registrado na fonte recuperada

  Cenário: Sincronizar API global homologada
    Dado que um conector possui domínio e rotas em allowlist
    Quando executar a sincronização
    Então deve aplicar timeout, limite de conteúdo e proteção contra SSRF
    E deve gerar snapshot imutável com checksum e proveniência
    E o conteúdo deve ser validado antes da publicação

  Cenário: Bloquear destino externo não autorizado
    Dado que um conector global recebeu URL fora da allowlist ou para endereço privado
    Quando tentar sincronizar
    Então a requisição deve ser bloqueada
    E a tentativa deve ser auditada sem expor o segredo

  Cenário: Avaliar e corrigir resposta do assistente
    Dado que o assistente registrou uma consulta RAG
    Quando o usuário avaliar a resposta como positiva, negativa ou corrigida
    Então o sistema deve criar uma revisão imutável de avaliação, comentário e resposta corrigida
    E deve registrar quem revisou e quando a revisão ocorreu
    E o feedback deve permanecer restrito ao tenant

  Cenário: Substituir avaliação sem apagar o histórico
    Dado que uma consulta possui uma avaliação anterior
    Quando o usuário enviar uma nova avaliação
    Então uma nova revisão deve referenciar a revisão anterior
    E a revisão anterior deve permanecer auditável no estado SUPERADO

  Cenário: Classificar uma resposta negativa
    Dado que o usuário recebeu fontes desconexas e uma rota inadequada
    Quando avaliar negativamente a resposta
    Então deve poder informar FONTES_IRRELEVANTES e ROTEAMENTO_INCORRETO
    E deve poder julgar cada fonte como RELEVANTE ou IRRELEVANTE
    E deve poder indicar o método e os filtros esperados

  Cenário: Validar julgamento de fonte
    Dado que uma consulta do tenant A possui fontes versionadas registradas
    Quando o usuário tentar julgar uma versão não presente ou não acessível
    Então o feedback deve ser rejeitado
    E nenhuma referência de outro tenant deve ser persistida

  Cenário: Colocar feedback malicioso em quarentena
    Dado que o comentário ou a correção tenta instruir o modelo ou exfiltrar dados
    Quando o feedback passar pela validação de segurança
    Então seu estado deve ser QUARENTENA
    E o texto não deve compor prompt, embedding, evento, log ou artefato

  Cenário: Compilar somente sinais aprovados
    Dado que existem feedbacks aprovados, rejeitados, revogados e em quarentena
    Quando o worker executar a compilação do tenant
    Então somente feedbacks aprovados e não superados devem participar
    E o artefato candidato deve registrar configuração, checksum e proveniência
    E a execução deve ser idempotente para a mesma janela e configuração

  Cenário: Não aprender com clique sem diagnóstico
    Dado que um usuário avaliou negativamente sem informar motivo ou fonte
    Quando o pipeline selecionar sinais para compilação
    Então a avaliação deve compor somente a métrica de satisfação
    E não deve produzir boost, penalidade, rota ou exemplar

  Cenário: Exigir revisão humana de texto livre
    Dado que um feedback contém comentário, resposta corrigida ou fonte ausente
    Quando passar pelas validações automáticas
    Então deve permanecer PENDENTE_REVISAO até decisão de um gestor
    E a futura ativação não deve depender somente do autor do feedback

  Cenário: Promover feedback aprovado para o dataset
    Dado que um feedback aprovado possui fonte relevante, fonte irrelevante, rota e filtros esperados
    Quando o gestor promover o feedback para avaliação
    Então deve ser criado um único caso tenant-scoped ligado à revisão do feedback
    E a fonte relevante deve integrar as fontes esperadas
    E a fonte irrelevante deve integrar os hard negatives
    E rota, filtros, curador e proveniência devem ser preservados

  Cenário: Não promover feedback sem diagnóstico
    Dado que um feedback positivo não possui motivo, julgamento, rota, filtro ou expectativa de recusa
    Quando o gestor tentar promovê-lo para avaliação
    Então a promoção deve ser recusada
    E o clique deve permanecer disponível somente para métricas de satisfação

  Cenário: Desativar caso curado inelegível
    Dado que um feedback aprovado originou um caso ativo no dataset
    Quando o feedback for superado ou revogado ou uma fonte referenciada for eliminada
    Então o caso deve ser desativado antes da próxima execução
    E o motivo deve ser preservado sem apagar o histórico

  Cenário: Avaliar rota, filtros e hard negatives
    Dado que o dataset possui um caso curado com rota, filtros e hard negatives
    Quando o gestor executar a avaliação
    Então devem ser medidas acurácia de roteamento e de filtros
    E deve ser medida a taxa de recuperação dos hard negatives
    E casos manuais sem esses sinais devem manter a avaliação documental anterior

  Cenário: Não promover correção humana a evidência
    Dado que um usuário escreveu uma resposta corrigida
    Quando a correção for aprovada como exemplar
    Então ela pode orientar avaliação e estrutura da resposta
    Mas não deve ser indexada como fonte nem apresentada como citação

  Cenário: Impedir boost abaixo do limiar
    Dado que um perfil de reranking ativo favorece determinada fonte
    E a fonte está abaixo do limiar mínimo de evidência
    Quando o assistente ordenar os candidatos
    Então a fonte não deve compor o contexto
    E o perfil não deve ultrapassar tenant, ACL, vigência, jurisdição ou estado

  Cenário: Avaliar candidato antes da ativação
    Dado que uma compilação produziu um artefato candidato
    Quando o gestor solicitar sua ativação
    Então candidato e baseline devem ser executados no mesmo dataset do tenant
    E regressões acima das tolerâncias devem impedir a ativação
    E métricas, decisão e aprovador devem ser auditados

  Cenário: Reverter artefato de aprendizado
    Dado que um artefato novo está ativo e existe uma versão anterior
    Quando ocorrer regressão ou o gestor solicitar rollback
    Então a versão anterior deve ser restaurada atomicamente
    E consultas posteriores devem registrar a versão restaurada

  Cenário: Revogar feedback já compilado
    Dado que um feedback aprovado originou um artefato ativo
    Quando o feedback for revogado ou sua fonte for eliminada
    Então o artefato dependente deve ser invalidado
    E uma recompilação tenant-scoped deve ser agendada

  Cenário: Impedir contaminação de aprendizado entre tenants
    Dado que o tenant A corrigiu uma resposta
    Quando o tenant B fizer uma consulta semelhante
    Então a correção privada do tenant A não deve influenciar a resposta do tenant B

  Cenário: Entender e expandir consulta documental
    Dado que o usuário pergunta por um decreto sobre transporte
    Quando o assistente formar o pool documental
    Então deve preservar a consulta original
    E pode gerar expansões legislativas e temáticas controladas
    E deve fundir os pools por RRF antes do reranking neural
    E deve auditar intenção, referências, expansões e filtros

  Cenário: Filtros inferidos não afrouxam segurança
    Dado que o entendimento identificou tema, tipo documental e período
    Quando os filtros forem aplicados
    Então devem restringir os candidatos antes do ranking
    Mas não devem alterar tenant, ACL, vigência, retenção ou publicação

  Cenário: Gerar resposta substantiva com citações validadas
    Dado que o retrieval aprovou chunks autorizados, pertinentes e sanitizados
    Quando o gerador produzir afirmações estruturadas
    Então cada afirmação deve citar somente IDs presentes no contexto
    E a aplicação deve validar o suporte da afirmação nos chunks citados
    E a resposta deve expor citações rastreáveis até chunk, documento e versão

  Cenário: Recusar resposta cuja citação não seja validada
    Dado que o gerador citou uma fonte desconhecida ou sem suporte para a afirmação
    Quando a aplicação validar o retorno estruturado
    Então a resposta substantiva deve ser descartada integralmente
    E o assistente deve emitir recusa conclusiva segura
    E as fontes recuperadas podem permanecer visíveis para inspeção

  Cenário: Tratar instruções dos documentos como dados
    Dado que um chunk recuperado contém uma instrução maliciosa
    Quando o contexto for preparado para a geração
    Então o trecho deve ser sanitizado e limitado
    E a instrução não deve alterar o contrato, as fontes ou a política do sistema

  Cenário: Rejeitar contradição apesar da semelhança lexical
    Dado que a fonte proíbe uma conduta
    E a resposta afirma que a mesma conduta é permitida
    Quando a validação lexical encontrar palavras em comum
    Então o verificador semântico deve marcar a afirmação como contradita
    E o assistente deve recusar a resposta substantiva

  Cenário: Exigir verificador NLI independente
    Dado que o gerador e o verificador NLI estão habilitados
    Quando ambos forem configurados com o mesmo modelo
    Então a validação NLI deve ser considerada indisponível
    E a resposta deve ser recusada pela política fail-closed

  Cenário: Evitar reranking neural desnecessário
    Dado que o ranking híbrido possui um único candidato ou líder inequívoco
    Quando o assistente preparar as fontes
    Então não deve chamar o reranker neural
    E deve registrar score, margem e motivo do skip adaptativo

  Cenário: Medir orçamento de latência ponta a ponta
    Dado que uma consulta documental percorreu recuperação, geração e NLI
    Quando a resposta for registrada
    Então deve expor a latência de cada etapa e o tempo total
    E deve indicar se o orçamento foi excedido
    E o rollout deve usar a taxa de estouro como gate online

  Cenário: Calibrar perfil de qualidade contra baseline
    Dado que o tenant possui um dataset de avaliação ativo
    Quando o administrador propuser novos thresholds permitidos
    Então baseline e candidato devem executar sobre o mesmo dataset
    E regressões acima da tolerância devem rejeitar o perfil
    E um perfil aprovado deve iniciar automaticamente o rollout governado

  Cenário: Promover progressivamente um perfil de qualidade
    Dado que o perfil candidato venceu o baseline offline
    Quando cada etapa atingir sua janela e amostra mínimas sem regressão
    Então o tráfego deve avançar por 5%, 20%, 50% e 100%
    E usuários fora do canário devem continuar no perfil baseline
    E o perfil deve ser promovido somente após validar a etapa de 100%
    E métricas e decisões de cada etapa devem permanecer auditáveis

  Cenário: Reverter rollout progressivo por regressão online
    Dado que um perfil de qualidade está em rollout automatizado
    Quando fallback, rejeição semântica, recusa ou feedback negativo violar um gate
    Então o candidato deve ser revogado sem aguardar a próxima expansão
    E a versão anterior elegível deve ser restaurada atomicamente
    E o histórico deve registrar métricas e motivos do rollback

  Cenário: Reverter canário por rejeições semânticas
    Dado que um perfil de qualidade está ativo em canário
    Quando a taxa de rejeição semântica exceder o gate após a amostra mínima
    Então o perfil deve ser revogado automaticamente
    E a versão anterior elegível deve ser restaurada atomicamente

  Cenário: Promover conhecimento privado para o catálogo global
    Dado que o tenant autorizou formalmente o compartilhamento
    E o conteúdo foi anonimizado e revisado
    Quando o administrador global aprovar a promoção
    Então uma nova fonte global deve ser criada
    E o chunk privado original não deve ser reutilizado diretamente
    E consentimento, revisão, proveniência e publicação devem ser auditados

  Cenário: Administrador global não acessa o RAG Privado
    Dado que um administrador global gerencia o catálogo GabFlow
    Quando tentar consultar conteúdo privado de um tenant sem concessão de suporte
    Então o acesso deve ser negado

  Cenário: Acesso excepcional de suporte
    Dado que existe concessão válida com tenant, motivo, escopo e expiração
    Quando o usuário de suporte acessar o RAG Privado
    Então deve acessar somente o tenant e o escopo autorizados
    E cada consulta e download deve ser auditado
