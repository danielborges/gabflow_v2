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
    Então o sistema deve preservar avaliação, comentário e resposta corrigida
    E deve registrar quem revisou e quando a revisão ocorreu
    E o feedback deve permanecer restrito ao tenant

  Cenário: Impedir contaminação de aprendizado entre tenants
    Dado que o tenant A corrigiu uma resposta
    Quando o tenant B fizer uma consulta semelhante
    Então a correção privada do tenant A não deve influenciar a resposta do tenant B

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
