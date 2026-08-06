# language: pt
Funcionalidade: Diretório de cidadãos e organizações v2
  Para atender pessoas com rapidez sem perder qualidade e rastreabilidade
  Como usuário autorizado de um gabinete
  Quero localizar, cadastrar e atualizar cidadãos no contexto da própria tela

  Contexto:
    Dado que o usuário está autenticado em um gabinete
    E possui permissão para consultar e manter cidadãos

  Cenário: Iniciar cadastro sem abrir modal
    Dado que estou na agenda de cidadãos
    Quando aciono "Novo cidadão"
    Então o formulário vazio deve ocupar a área de detalhe da tela
    E a agenda deve permanecer disponível conforme o espaço do dispositivo
    E o foco deve ir para o campo "Nome"

  Cenário: Usar o mesmo formulário para edição
    Dado que existe o cidadão "João da Silva"
    Quando seleciono "João da Silva" na agenda
    Então o formulário deve carregar seus dados editáveis
    E deve exibir "Cadastrado em", "Último contato" e "Atendido por" somente para leitura
    E deve exibir suas solicitações da mais recente para a mais antiga

  Cenário: Cadastrar apenas com os dados mínimos
    Quando informo o nome "Ana Souza"
    E salvo o cadastro
    Então o sistema deve criar o cidadão
    E deve aplicar a base legal padrão válida configurada para o gabinete
    E deve registrar o usuário e o instante da criação
    E deve manter vazios os campos opcionais não informados

  Cenário: Impedir cadastro mínimo sem política de base legal
    Dado que não selecionei uma base legal
    E o gabinete não possui base legal padrão válida configurada
    Quando tento salvar o cidadão
    Então o sistema não deve escolher uma base legal automaticamente
    E deve orientar a configuração ou seleção necessária para concluir

  Esquema do Cenário: Validar campo opcional preenchido
    Dado que informei um valor inválido em "<campo>"
    Quando tento salvar o cidadão
    Então o cadastro não deve ser persistido
    E o erro deve ser associado ao campo "<campo>"

    Exemplos:
      | campo              |
      | Telefone           |
      | E-mail             |
      | Data de nascimento |
      | CPF                |
      | Título de eleitor  |

  Cenário: Capturar foto pela câmera
    Dado que o dispositivo oferece câmera e a aplicação usa contexto seguro
    Quando aciono "Usar câmera" e autorizo o acesso
    Então devo visualizar a imagem capturada antes de salvar
    E devo poder reenquadrar, substituir ou remover a imagem
    E o fluxo deve oferecer "Escolher arquivo" como alternativa

  Cenário: Negar acesso à câmera
    Quando aciono "Usar câmera" e nego a permissão
    Então nenhum stream deve permanecer ativo
    E devo receber orientação não bloqueante
    E devo poder escolher um arquivo ou continuar sem foto

  Cenário: Bloquear CPF já cadastrado
    Dado que "Maria Oliveira" possui o CPF informado no mesmo gabinete
    Quando tento criar ou atualizar outro cidadão com esse CPF
    Então o sistema deve rejeitar a operação por conflito
    E deve informar que o CPF pertence a "Maria Oliveira"
    E deve oferecer a ação "Abrir cadastro existente"

  Cenário: Alertar sobre homônimo e reutilizar cadastro
    Dado que existe outro cidadão com o mesmo nome normalizado
    Quando saio do campo "Nome" ou tento salvar
    Então devo visualizar os possíveis homônimos com dados mínimos de diferenciação
    E devo poder abrir um cadastro existente
    E, se não for a mesma pessoa, devo poder confirmar a criação do novo cidadão

  Cenário: Derivar bairro e território pelo endereço
    Quando seleciono um endereço validado
    Então o sistema deve geocodificar o endereço
    E deve identificar bairro e território conforme a jurisdição do gabinete
    E deve exibi-los somente para consulta
    E uma falha de resolução não deve apagar o endereço nem impedir o cadastro

  Cenário: Relacionar organizações do cidadão
    Dado que existem organizações acessíveis no gabinete
    Quando pesquiso e seleciono uma organização no campo "Organizações"
    Então o vínculo de responsabilidade deve ser associado ao cidadão
    E o componente deve permitir pesquisa e operação completa por teclado

  Cenário: Marcar cidadão como VIP
    Quando aciono a estrela "Marcar como VIP"
    Então o estado VIP deve ser persistido
    E a alteração deve ser anunciada por texto, além de cor ou ícone
    E a auditoria deve registrar ator e instante

  Cenário: Abrir nova solicitação no contexto do cidadão
    Dado que selecionei ou acabei de cadastrar um cidadão
    Quando aciono "Nova solicitação"
    Então a tela de solicitações deve abrir com o cidadão pré-selecionado
    E os dados compatíveis devem ser reutilizados sem nova digitação

  Cenário: Abrir solicitação existente
    Dado que o cidadão possui solicitações
    Quando seleciono uma solicitação no histórico
    Então a tela de solicitações deve abrir diretamente no identificador escolhido

  Cenário: Navegar pela agenda telefônica
    Dado que existem cidadãos com diferentes letras iniciais
    Quando pesquiso por nome, nome social, CPF ou contato
    Então a lista deve exibir resultados agrupados alfabeticamente pelo nome de exibição
    E a navegação lateral deve habilitar apenas letras com resultados
    E as letras sem cadastro devem permanecer visíveis e desabilitadas
    E a disponibilidade deve considerar todo o diretório, não somente a página carregada
    E cada item deve exibir nome, telefone, e-mail, localidade, profissão e canal preferencial quando disponíveis
    E nenhum documento pessoal deve ser revelado no cartão

  Cenário: Sugerir cadastro a partir de mensagem recebida
    Dado que uma mensagem de WhatsApp ou e-mail foi normalizada pelo conector
    Quando não existe correspondência determinística de cidadão
    Então o sistema deve criar uma sugestão de cadastro com proveniência do canal
    E nenhum cidadão deve ser criado antes da revisão humana

  Cenário: Vincular mensagem a cidadão existente após revisão
    Dado que uma mensagem possui correspondência exata de contato no mesmo gabinete
    Quando um usuário autorizado confirma explicitamente o cidadão sugerido
    Então a revisão deve registrar o vínculo, o usuário e o instante
    E uma solicitação convertida depois da decisão deve usar o cidadão confirmado

  Cenário: Manter nova identidade fora do cadastro definitivo
    Dado que uma mensagem de WhatsApp ou e-mail não possui correspondência
    Quando consulto a fila de revisão humana
    Então devo visualizar que não há correspondência
    E o sistema não deve disponibilizar criação ou mesclagem automática de cidadão

  Cenário: Reprocessar entrega idempotente
    Dado que um conector reenviou o mesmo identificador externo
    Quando o envelope já existe para o tenant e canal
    Então nenhuma nova mensagem ou revisão deve ser criada

  Cenário: Concluir cadastro assistido com confirmação humana
    Dado que uma revisão pendente não possui cidadão correspondente
    E o gabinete configurou uma base legal padrão
    Quando o operador inicia o cadastro e confirma nome, contato e base legal
    Então o cidadão deve passar pelas validações usuais de CPF e homônimo
    E o cidadão e a revisão devem ser vinculados na mesma transação
    E a proveniência deve registrar somente identificadores opacos

  Cenário: Bloquear conclusão assistida incompleta
    Dado que o formulário foi preparado a partir de uma mensagem
    Quando o operador não confirma um dos campos obrigatórios
    Então nenhum cidadão deve ser criado
    E a revisão deve permanecer pendente

  Cenário: Operar SLA e retenção da fila assistida
    Dado que o gabinete configurou SLA, responsável e prazo de retenção
    Quando consulto a fila de revisão
    Então devo visualizar contadores, vencimento e responsável
    E somente um usuário autorizado pode reabrir uma decisão com justificativa
    E a execução de retenção deve minimizar apenas envelopes concluídos vencidos

  Cenário: Desenhar território no mapa administrativo
    Dado que o gabinete possui uma jurisdição configurada
    Quando o administrador marca ao menos três vértices e conclui o desenho
    Então o mapa deve formar um anel GeoJSON fechado
    E o território só deve orientar a resolução automática depois de ser salvo

  Cenário: Editar polígono e aliases de um território
    Dado que um território está visível no mapa
    Quando o administrador o seleciona e move um vértice por arraste ou teclado
    E altera seus aliases de bairro
    Então mapa, formulário e painel de aliases devem permanecer sincronizados
    E o salvamento deve validar colisões no mesmo gabinete e gerar auditoria

  Cenário: Administrar território com múltiplas partes
    Dado que um território possui áreas não contíguas
    Quando o administrador desenha uma nova parte
    Então a geometria deve ser persistida como MultiPolygon
    E cada parte deve poder ser selecionada e removida separadamente

  Cenário: Auditar atualização sem vazar dados em log técnico
    Dado que alterei dados de um cidadão
    Quando salvo as alterações
    Então o histórico funcional deve registrar usuário, instante e campos alterados
    E CPF, título de eleitor, endereço, foto e conteúdo de contato não devem aparecer em logs técnicos
