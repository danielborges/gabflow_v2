# language: pt
Funcionalidade: Atendimento multi-tenant pelo WhatsApp

  Cenário: Conectar o número próprio de um gabinete
    Dado que sou administrador do tenant "Gabinete A"
    E o tenant não possui integração ativa
    Quando concluo o Embedded Signup com uma WABA e número válidos
    Então o GabFlow deve confirmar os objetos diretamente com a Meta
    E deve associar o phone_number_id somente ao "Gabinete A"
    E deve guardar a credencial fora do banco de aplicação
    E a integração deve ficar ativa somente após o teste de saúde

  Cenário: Impedir reutilização de número entre tenants
    Dado que um phone_number_id está ativo no "Gabinete A"
    Quando o "Gabinete B" tenta concluir onboarding com o mesmo phone_number_id
    Então a ativação deve ser recusada
    E nenhum dado do "Gabinete A" deve ser revelado
    E o evento deve ser auditado

  Cenário: Receber primeira mensagem e criar solicitação
    Dado que o cidadão escreveu para o número do "Gabinete A"
    Quando o webhook válido é recebido
    Então o tenant deve ser resolvido pelo phone_number_id
    E o cidadão deve receber o aviso de privacidade aplicável
    Quando ele conclui o Flow de nova solicitação
    Então deve ser criado um protocolo não enumerável no "Gabinete A"
    E a IA deve registrar suas sugestões com confiança e versão
    E o cidadão deve receber a confirmação

  Cenário: Evento duplicado
    Dado que um evento da Meta já foi processado
    Quando o mesmo evento é entregue novamente
    Então o webhook deve responder com sucesso
    E nenhuma nova mensagem, solicitação ou notificação deve ser duplicada

  Cenário: Número desconhecido
    Dado que o webhook contém um phone_number_id sem integração ativa
    Quando o evento é recebido
    Então ele deve ir para quarentena
    E não deve ser associado a um tenant padrão
    E um alerta sem conteúdo sensível deve ser gerado

  Cenário: Assessor assume a conversa
    Dado que o bot está conduzindo uma conversa
    Quando um assessor autorizado inicia o handoff
    Então a conversa deve passar para modo humano
    E respostas automáticas concorrentes devem ser bloqueadas
    E a retomada do bot deve exigir ação explícita ou regra configurada

  Cenário: Opt-out do cidadão
    Dado que o cidadão possui uma conversa ativa
    Quando ele envia "PARAR"
    Então seu opt-out deve ser registrado com data e evidência
    E mensagens não essenciais devem cessar
    E ele deve receber confirmação compatível com a política vigente

  Cenário: IA indisponível
    Dado que o serviço de IA está indisponível
    Quando o cidadão conclui o formulário estruturado
    Então a solicitação deve ser protocolada sem classificação automática
    E deve ser encaminhada à triagem humana
    E nenhuma mensagem deve ser perdida

  Cenário: Bloquear vazamento por identificador
    Dado que um assessor do "Gabinete A" está autenticado
    Quando ele solicita uma conversa pertencente ao "Gabinete B"
    Então o sistema deve responder como recurso inexistente
    E não deve retornar metadados do outro tenant

  Cenário: Mensagem fora da janela permitida
    Dado que a janela de atendimento livre expirou
    Quando o GabFlow precisa notificar o cidadão
    Então somente um template aprovado e adequado deve poder ser enviado
    E a decisão da política deve ser auditada
