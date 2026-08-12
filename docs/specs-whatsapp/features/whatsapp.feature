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

  Cenário: Identificação mínima respeita privacidade e confirmação
    Dado que o cidadão iniciou uma conversa no "Gabinete A"
    Quando o aviso de privacidade e a base legal aplicável são registrados
    E um assessor confirma o nome e o WhatsApp informado pelo cidadão
    Então o cadastro mínimo pode ser criado sem CPF
    E a identidade deve permanecer isolada no "Gabinete A"
    E a evidência do aviso deve ser armazenada de forma minimizada

  Cenário: Repetir confirmação não duplica solicitação
    Dado que uma coleta estruturada foi revisada pelo cidadão
    Quando a confirmação é enviada duas vezes com a mesma chave de idempotência
    Então deve existir somente uma solicitação
    E ambas as respostas devem referenciar o mesmo protocolo público não sequencial

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

  Cenário: Mensagem livre dentro da janela é idempotente
    Dado que a janela de atendimento do cidadão está aberta no "Gabinete A"
    Quando o assessor envia duas vezes a mesma mensagem com a mesma chave de idempotência
    Então somente uma mensagem deve ser enviada à Meta
    E a decisão de política deve indicar janela aberta

  Cenário: Template não aprovado não pode iniciar contato
    Dado que a janela de atendimento do cidadão encerrou
    Quando o assessor seleciona um template pendente ou rejeitado
    Então a saída deve ser bloqueada antes do dispatcher

  Cenário: Template transacional aprovado fora da janela
    Dado que a janela de atendimento do cidadão encerrou
    E existe um template de utilidade aprovado pela Meta no mesmo tenant
    Quando o assessor preenche seus parâmetros e confirma o envio
    Então a mensagem deve ser enfileirada pelo outbox
    E seus estados de envio, entrega e leitura devem ser registrados

  Cenário: Opt-out bloqueia mensagem já enfileirada
    Dado que uma mensagem comum está aguardando envio
    Quando o cidadão envia "PARAR" antes do dispatch
    Então a mensagem comum deve ser bloqueada
    E somente uma confirmação de opt-out pode ser enviada

  Cenário: Ativar nova versão sem invalidar respostas em trânsito
    Dado que o Flow de nova solicitação versão 1 está ativo no "Gabinete A"
    E existe uma sessão pendente vinculada à versão 1
    Quando o administrador ativa a versão 2 publicada na Meta
    Então a versão 1 deve ficar aposentada para novos envios
    E a sessão pendente deve continuar validável pela versão 1

  Cenário: Concluir Flow cria uma única solicitação
    Dado que o cidadão reconheceu a privacidade e está vinculado no "Gabinete A"
    E recebeu o Flow ativo de nova solicitação
    Quando a Meta entrega duas vezes o mesmo nfm_reply confirmado
    Então os campos devem ser validados pelo schema da versão enviada
    E deve existir somente uma solicitação com protocolo público não enumerável

  Cenário: Rejeitar campo desconhecido no Flow
    Dado que existe uma sessão de Flow pendente no "Gabinete A"
    Quando a resposta inclui um campo que não pertence ao schema versionado
    Então a submissão deve ser rejeitada sem retry infinito
    E nenhum cadastro ou solicitação deve ser criado

  Cenário: Flow indisponível usa coleta guiada
    Dado que não existe uma versão ativa do Flow no ambiente do "Gabinete A"
    Quando o assessor inicia a coleta estruturada
    Então a conversa deve seguir para coleta de dados
    E o formulário guiado deve permanecer disponível na caixa de entrada

  Cenário: Áudio recebido e transcrito de forma assíncrona
    Dado que o cidadão enviou um áudio para o "Gabinete A"
    Quando o webhook confiável confirma o recebimento
    Então a resposta deve ocorrer antes do download e da IA
    E o arquivo deve ser verificado e armazenado criptografado
    E a transcrição deve apresentar confiança, modelo e revisão humana

  Cenário: Mídia duplicada não cria novo ativo
    Dado que uma mensagem de mídia da Meta já foi processada
    Quando a mesma mensagem é entregue novamente
    Então deve existir somente um ativo de mídia no tenant

  Cenário: Arquivo malicioso é bloqueado
    Dado que uma mídia recebida contém uma ameaça
    Quando a verificação de segurança termina
    Então o arquivo deve ficar bloqueado
    E seu conteúdo não deve ser enviado ao provedor de IA

  Cenário: IA de mídia indisponível não bloqueia protocolo
    Dado que o provedor de transcrição ou classificação está indisponível
    Quando o cidadão confirma a solicitação
    Então o protocolo deve ser criado normalmente
    E a análise deve permitir reprocessamento posterior

  Cenário: Mídia permanece isolada por tenant
    Dado que um assessor do "Gabinete A" está autenticado
    Quando ele solicita a mídia pertencente ao "Gabinete B"
    Então o sistema deve responder como recurso inexistente

  Cenário: Iniciar piloto somente após evidências e saúde aprovadas
    Dado que o gabinete possui todas as aprovações externas
    E cada gate interno possui uma referência de evidência aprovada
    E o semáforo operacional não possui problema crítico
    Quando o administrador inicia o piloto
    Então o estado do piloto deve ser "RUNNING"
    E a decisão deve permanecer registrada na auditoria

  Cenário: Pausar saídas sem interromper recebimento e opt-out
    Dado que o piloto está em execução
    Quando o administrador informa o motivo e pausa as saídas
    Então mensagens comuns devem ser bloqueadas no enfileiramento e no dispatch
    E webhooks recebidos devem continuar sendo persistidos
    E a confirmação de opt-out deve continuar permitida

  Cenário: Operação de outro tenant permanece invisível
    Dado que um administrador do "Gabinete A" está autenticado
    Quando ele consulta o cockpit do "Gabinete B"
    Então o sistema deve responder como recurso inexistente
