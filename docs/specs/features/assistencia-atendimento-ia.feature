# language: pt
Funcionalidade: Respostas e próximos passos sugeridos pela IA

  Cenário: Preparar assistência completa para o atendimento
    Dado que existe uma solicitação com histórico de atendimento
    Quando o assessor solicitar assistência informando canal e tom
    Então o processamento deve ocorrer de forma assíncrona
    E deve apresentar um resumo do histórico
    E deve sugerir perguntas faltantes e documentos a confirmar
    E deve propor próximos passos com responsável e justificativa
    E deve preparar uma resposta editável no canal e tom informados

  Cenário: Revisar uma resposta sugerida
    Dado que a assistência foi concluída
    Quando o assessor editar e usar o rascunho sugerido
    Então a revisão deve ser registrada no histórico e na auditoria
    E o texto deve ser transferido para o formulário de resposta
    E nenhuma interação de saída deve ser criada automaticamente

  Cenário: Impedir envio autônomo pela IA
    Dado que a IA concluiu uma resposta sugerida
    Quando o usuário ainda não registrar a saída explicitamente
    Então a resposta deve permanecer apenas como rascunho
    E nenhum e-mail ou mensagem deve ser enviado
    E o resultado deve registrar que o envio automático está desabilitado
