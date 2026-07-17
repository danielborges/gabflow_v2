# language: pt
Funcionalidade: Assistente RAG

  Cenário: Ingerir documento versionado
    Dado que um gestor selecionou PDF, DOCX, TXT ou imagem permitida
    Quando informar tipo, órgão, acesso, versão e vigência
    Então o sistema deve validar o arquivo e registrar seu checksum
    E deve extrair texto nativo ou aplicar OCR local
    E deve criar fragmentos com página e gerar embeddings locais
    E deve registrar o processamento de forma assíncrona e auditável

  Cenário: Governar versões da fonte
    Dado que um documento possui uma versão indexada
    Quando o gestor publicar essa versão como vigente
    Então outra versão vigente deve passar para histórica
    E o sistema deve distinguir rascunho, vigente, histórico e revogado
    E deve preservar arquivo, checksum, vigência e modelo de embeddings

  Cenário: Isolar documentos e níveis de acesso
    Dado que existem documentos internos e restritos em diferentes tenants
    Então nenhum usuário deve consultar documentos de outro tenant
    E documentos restritos devem ser visíveis somente a gestores

  Cenário: Responder com fontes
    Dado que o usuário possui acesso à base legislativa
    E existem documentos relevantes
    Quando perguntar sobre legislação municipal
    Então o assistente deve responder com citações
    E deve indicar documento, versão e página quando disponível
    E deve restringir a recuperação ao tenant e ao nível de acesso

  Cenário: Não há evidência suficiente
    Dado que a recuperação não encontrou fontes confiáveis
    Quando o assistente elaborar a resposta
    Então deve informar que não encontrou fundamento suficiente
    E não deve apresentar uma resposta conclusiva

  Cenário: Documento contém instrução maliciosa
    Dado que uma fonte contém texto tentando alterar o comportamento do modelo
    Quando a fonte for recuperada
    Então o texto deve ser tratado apenas como conteúdo
    E a instrução contida na fonte deve ser ignorada
