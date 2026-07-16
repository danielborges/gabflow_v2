# language: pt
Funcionalidade: Direitos do titular e privacidade

  Cenário: Exportar dados do cidadão
    Dado que a identidade do solicitante foi validada
    Quando o titular solicitar acesso aos seus dados
    Então o sistema deve gerar um pacote com os dados aplicáveis
    E deve registrar a operação na auditoria

  Cenário: Corrigir dado pessoal
    Dado que o cidadão solicitou correção de um contato
    Quando um usuário autorizado confirmar a alteração
    Então o dado deve ser atualizado
    E o histórico da correção deve ser preservado

  Cenário: Restringir divulgação
    Dado que o cidadão autorizou contato
    Mas não autorizou divulgação pública de sua imagem
    Quando uma publicação for preparada
    Então o sistema deve alertar que não há consentimento para divulgação
