# language: pt
Funcionalidade: Classificação assistida por IA

  Cenário: Sugerir classificação
    Dado que existe uma solicitação ainda não classificada
    Quando a classificação por IA for executada
    Então o sistema deve sugerir categoria, subcategoria e prioridade
    E deve informar a confiança
    E deve registrar o modelo e a versão do prompt
    E a sugestão deve permanecer pendente de validação humana

  Cenário: Falha do provedor de IA
    Dado que o provedor de IA está indisponível
    Quando o assessor cadastrar uma solicitação
    Então o cadastro deve ser concluído normalmente
    E a solicitação deve ficar disponível para classificação manual

  Cenário: Identificar possível emergência
    Dado que o relato contém indício de risco imediato à vida
    Quando a triagem for executada
    Então o sistema deve destacar o atendimento
    E deve orientar o assessor a acionar o serviço competente
    E não deve afirmar que o gabinete substitui o serviço de emergência
