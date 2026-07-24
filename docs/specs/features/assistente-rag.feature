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
    Dado que o tenant criou ou atualizou uma solicitação, interação ou documento legislativo
    E a informação é elegível conforme finalidade, base legal, retenção e sigilo
    Quando o evento interno for processado
    Então uma fonte privada versionada deve ser criada ou atualizada
    E os chunks devem permanecer exclusivamente no tenant
    E a entidade e versão de origem devem ser preservadas

  Cenário: Não ingerir informação interna inelegível
    Dado que uma informação foi excluída por minimização, retenção, base legal ou sigilo
    Quando o pipeline privado avaliar o evento
    Então o conteúdo não deve ser enviado ao modelo nem indexado
    E a decisão deve ser auditada sem copiar o dado sensível para o log

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

  Cenário: Não usar fonte global incompatível com a jurisdição
    Dado que uma norma global é restrita a outra jurisdição
    Quando o tenant realizar uma consulta semanticamente semelhante
    Então essa norma não deve compor o contexto

  Cenário: Não há evidência suficiente em nenhum escopo
    Dado que a recuperação global e privada não encontrou fontes confiáveis
    Quando o assistente elaborar a resposta
    Então deve informar que não encontrou fundamento suficiente
    E não deve apresentar uma resposta conclusiva

  Cenário: Documento contém instrução maliciosa
    Dado que uma fonte contém texto tentando alterar o comportamento do modelo
    Quando a fonte for ingerida ou recuperada
    Então o texto deve ser tratado apenas como conteúdo
    E a instrução contida na fonte deve ser ignorada
    E o conteúdo deve ser sinalizado ou colocado em quarentena
    E a instrução maliciosa não deve integrar o contexto de geração

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
