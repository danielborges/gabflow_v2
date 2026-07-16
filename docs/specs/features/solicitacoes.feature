# language: pt
Funcionalidade: Gestão de solicitações

  Cenário: Registrar uma nova solicitação
    Dado que o assessor está autenticado no gabinete
    Quando registrar uma solicitação com origem "WhatsApp" e descrição válida
    Então o sistema deve gerar um protocolo único
    E deve registrar a solicitação com status "NOVA"
    E deve publicar o evento "SolicitacaoCriada"

  Cenário: Agrupar solicitações duplicadas
    Dado que existem solicitações semelhantes no mesmo local e período
    Quando o assessor confirmar que são duplicadas
    Então o sistema deve manter todos os protocolos
    E deve relacioná-los a um agrupamento comum
    E não deve apagar o histórico individual

  Cenário: Encerrar solicitação como resolvida
    Dado que uma solicitação está em atendimento
    Quando o assessor informar resolução e evidência
    Então o sistema deve registrar a data de encerramento
    E deve preservar a evidência
    E deve registrar a alteração na auditoria

  Cenário: Impedir encerramento sem motivo
    Dado que uma solicitação está em atendimento
    Quando o assessor tentar encerrá-la sem motivo
    Então o sistema deve rejeitar a operação
