# language: pt
Funcionalidade: Assistente RAG

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
