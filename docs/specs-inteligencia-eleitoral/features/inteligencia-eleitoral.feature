# language: pt
Funcionalidade: Inteligência eleitoral e territorial do GabFlow
  Como Parlamentar
  Quero analisar dados eleitorais oficiais e a cobertura agregada do mandato
  Para tomar decisões baseadas em evidências sem expor dados pessoais

  Contexto:
    Dado que o módulo está habilitado para o gabinete
    E que existe uma carga eleitoral oficial publicada

  Cenário: Parlamentar consulta votação por território
    Dado que estou autenticado como "PARLAMENTAR"
    Quando seleciono uma eleição e meu candidato
    E escolho o nível "bairro"
    Então devo visualizar votos absolutos, percentuais e ranking
    E devo visualizar a fonte, a versão e o denominador

  Cenário: Usuário sem permissão tenta acessar
    Dado que estou autenticado sem permissão para o módulo
    Quando acesso uma rota de inteligência eleitoral
    Então o sistema deve responder com status 403
    E deve registrar a tentativa sem armazenar conteúdo pessoal desnecessário

  Cenário: Parlamentar delega análise a assessor
    Dado que estou autenticado como "PARLAMENTAR"
    Quando concedo ao assessor a permissão "comparar_candidatos" por 7 dias
    Então o assessor pode criar comparativos durante o período
    E não pode exportar relatórios sem permissão específica
    E a concessão deve ser auditada

  Cenário: Comparar candidatos
    Dado que selecionei uma eleição e um cargo
    Quando escolho entre 2 e 5 candidatos
    Então o sistema deve comparar o desempenho no mesmo recorte territorial
    E deve aplicar o mesmo denominador a todas as séries

  Cenário: Impedir comparação inválida
    Quando tento comparar 6 candidatos
    Então o sistema deve rejeitar a operação
    E deve explicar o limite permitido

  Cenário: Proteger grupos pequenos
    Dado que uma métrica do mandato tem menos de 10 ocorrências no território
    Quando abro a camada integrada do mandato
    Então o valor deve ser ocultado
    E a interface deve informar "suprimido por privacidade"

  Cenário: Gerar briefing territorial agregado
    Dado que existe um snapshot reproduzível do mandato
    Quando abro o briefing de um território operacional
    Então devo visualizar somente fatos e compromissos agregados
    E o conteúdo deve ser marcado como rascunho sujeito a revisão
    E a ausência de crosswalk eleitoral deve ser informada sem inferir correspondência

  Cenário: Configurar alertas territoriais
    Dado que estou autorizado a ver as camadas do mandato
    Quando escolho os tipos, canais e frequência dos alertas
    Então as preferências devem ficar isoladas por usuário e gabinete
    E o feed deve usar o snapshot mais recente
    E baixa votação nunca deve gerar alerta operacional

  Cenário: Bloquear inferência individual de voto
    Dado que estou na conversa com o assistente de IA
    Quando pergunto em quem um cidadão identificado provavelmente votou
    Então o sistema deve recusar a inferência
    E deve explicar que resultados eleitorais não revelam voto individual
    E deve registrar o bloqueio de forma minimizada

  Cenário: Gerar insight explicável
    Quando solicito uma análise de candidato
    Então o insight deve separar fatos, cálculos, hipóteses e limitações
    E toda afirmação quantitativa deve citar a versão do dataset
    E o conteúdo deve ser marcado como rascunho sujeito a revisão

  Cenário: Criar simulação
    Dado que informei uma eleição-base
    Quando crio um cenário com premissas territoriais
    Então o cenário não deve alterar o resultado oficial
    E deve exibir autor, data, premissas e aviso de simulação

  Cenário: Gerar relatório auditável
    Quando solicito um relatório PDF
    Então o processamento deve ocorrer de forma assíncrona
    E o PDF deve conter fonte, versão, filtros, autor e marca d'água
    E o download deve gerar evento de auditoria

  Cenário: Isolamento entre gabinetes
    Dado que um relatório pertence a outro tenant
    Quando tento acessá-lo com seu identificador
    Então o sistema deve responder com status 404 ou 403 conforme política
    E nenhum metadado do outro gabinete deve ser revelado

  Cenário: Gerar insight explicável e contestável
    Dado que o parlamentar selecionou uma eleição publicada e uma candidatura
    Quando solicitar uma análise explicável
    Então o processamento deve ocorrer de forma assíncrona
    E o resultado deve separar fatos, cálculos, hipóteses e limitações
    E toda afirmação quantitativa deve citar fonte, hash, versão e filtros
    E o conteúdo deve ser marcado como rascunho sujeito a revisão
    E uma contestação deve ocultar o insight e registrar a versão do modelo

  Cenário: Simular sem alterar o resultado oficial
    Dado que o parlamentar abriu o resultado territorial de uma candidatura
    Quando informar uma premissa territorial explícita e criar um cenário
    Então o sistema deve preservar o snapshot oficial usado como baseline
    E deve persistir autoria, premissas, fórmulas e versão da metodologia
    E deve identificar o resultado como simulação hipotética
    E não deve alterar os resultados eleitorais oficiais

  Cenário: Recusar inferência individual sem reter o prompt
    Quando pergunto quem votou em determinada candidatura
    Então a pergunta deve ser recusada antes do enfileiramento
    E a auditoria deve conter apenas hash, tamanho, categoria e versão da política
    E o texto bruto da pergunta não deve ser persistido

  Cenário: Responder pergunta com evidência oficial e documental
    Dado que selecionei uma candidatura e existem documentos RAG autorizados
    Quando faço uma pergunta eleitoral permitida
    Então os fatos eleitorais devem citar dataset, hash, versão e filtros
    E afirmações documentais devem citar documento, versão, página e checksum
    E os números devem ser validados contra a evidência citada
    E o insight deve aguardar revisão humana

  Cenário: Parlamentar decide uma contestação
    Dado que um insight foi contestado e está oculto
    Quando o parlamentar confere as evidências e restaura o insight
    Então a decisão deve registrar justificativa, responsável e data
    E deve preservar o hash dos fatos e a versão do modelo revisado

  Cenário: Copiar cenário sem alterar o original
    Dado que existe um cenário baseado em snapshot oficial
    Quando o parlamentar cria uma cópia com novas premissas
    Então um novo cenário deve referenciar o cenário de origem
    E o snapshot oficial deve permanecer idêntico
    E nenhum resultado eleitoral oficial deve ser alterado

  Cenário: Compartilhar cenário somente para leitura
    Quando o parlamentar gera um link de cenário válido por sete dias
    Então o token bruto não deve ser persistido
    E o acesso deve exigir usuário autorizado no mesmo gabinete
    E a resposta deve ser marcada como somente leitura
    E o parlamentar deve poder revogar o link

  Cenário: Comparar cenários compatíveis
    Dado que selecionei entre dois e cinco cenários com o mesmo snapshot oficial
    Quando solicito a comparação
    Então o sistema deve persistir totais e diferenças por cenário e território
    E deve rejeitar cenários com eleição, candidatura, recorte, versão ou hash diferentes

  Cenário: Analisar sensibilidade e incerteza sem alegar confiança estatística
    Quando informo amplitudes e número ímpar de passos para um cenário
    Então o sistema deve persistir a grade determinística de sensibilidade
    E deve exibir limites inferior, central e superior
    E o nível de confiança deve ser nulo
    E a interface deve informar que a faixa não é previsão nem intervalo estatístico

  Cenário: Abrir compartilhamento em experiência somente leitura
    Dado que recebi um link válido e estou autorizado no mesmo gabinete
    Quando abro a URL compartilhada no GabFlow
    Então devo visualizar premissas, metodologia, totais e resultados territoriais
    E não devo visualizar ações de cópia, edição, comparação ou sensibilidade
    E um link expirado ou revogado deve apresentar indisponibilidade

  Cenário: Gerenciar links sem recuperar tokens
    Dado que emiti compartilhamentos de um cenário
    Quando abro a gestão de links
    Então devo visualizar status, validade, quantidade e último acesso
    E devo poder revogar links ativos
    Mas o sistema não deve reconstruir nem exibir tokens antigos

  Cenário: Editar premissas antes de copiar cenário
    Quando escolho copiar e editar um cenário
    Então devo revisar nome, deltas, incertezas e justificativas
    E a confirmação deve criar um novo cenário ligado à origem
    E o cenário de origem deve permanecer imutável

  Cenário: Criar portfólio de cenários compatíveis
    Dado que existem cenários da mesma eleição, candidatura, nível e snapshot
    Quando crio um portfólio com até vinte alternativas
    Então o sistema deve agrupá-las sem alterar seus resultados
    E deve rejeitar uma alternativa incompatível
    E deve marcar a primeira alternativa como referência comparativa não preditiva

  Cenário: Avaliar metas agregadas e territoriais
    Dado que um portfólio possui metas explícitas de votos ou participação
    Quando abro sua avaliação
    Então devo visualizar valor, diferença e percentual de atingimento por cenário
    E metas territoriais devem aceitar apenas territórios do snapshot comum
    E a avaliação deve permanecer identificada como simulação hipotética

  Cenário: Preservar histórico do portfólio
    Quando adiciono ou removo cenário, substituo metas, mudo referência ou arquivo o portfólio
    Então um evento append-only deve registrar ator, data, tipo e metadados mínimos
    E uma remoção de cenário deve ser lógica

  Cenário: Exportar portfólio com finalidade
    Quando informo uma finalidade válida e exporto o portfólio
    Então o CSV deve incluir cenários, faixas, metas, diferenças, dataset e metodologia
    E deve conter aviso de simulação hipotética
    E a exportação deve gerar auditoria e evento no histórico

  Cenário: GabIA Eleitoral gera análise somente sobre evidências autorizadas
    Dado que a funcionalidade de IA eleitoral está habilitada com provedor generativo
    E existe um resultado eleitoral oficial publicado para a candidatura
    Quando o Parlamentar solicita uma análise com a GabIA
    Então toda afirmação gerada deve citar uma evidência fornecida
    E números e causalidade devem passar pela validação automática
    E as hipóteses devem aparecer somente como perguntas de investigação
    E provedor, modelo, prompt e eventual fallback devem permanecer auditáveis

  Cenário: Parlamentar explora uma simulação antes de salvar
    Dado que a funcionalidade de cenários está habilitada
    Quando escolho eleição, candidatura e nível dentro do simulador
    E adiciono premissas para um ou mais territórios
    Então devo visualizar base oficial, total simulado, diferença e faixa de incerteza
    E a prévia não deve persistir um cenário
    Quando informo um nome e confirmo o salvamento
    Então o cenário deve preservar exatamente a base, as premissas e a metodologia da prévia

  Cenário: Exibir a cobertura histórica sem ocultar ciclos ausentes
    Dado que a matriz oficial cobre eleições municipais e gerais entre 2012 e 2024
    E existem somente recortes parciais publicados para a UF do mandato
    Quando o Parlamentar consulta a cobertura eleitoral
    Então cada ciclo deve ser classificado como completo, parcial ou ausente
    E os cargos ausentes e a granularidade disponível devem ser informados
    E a interface não deve apresentar um recorte parcial como cobertura completa

  Cenário: Substituir recortes parciais por uma carga completa do mesmo ciclo
    Dado que existe uma versão publicada para apenas um cargo de uma eleição e UF
    Quando uma carga oficial validada com todos os cargos do ciclo é publicada
    Então os recortes parciais sobrepostos devem ser marcados como substituídos
    E somente a versão completa deve participar das consultas eleitorais

  Cenário: Rejeitar ano incompatível com o tipo de eleição
    Quando o operador tenta importar 2022 como eleição municipal
    Então a carga deve ser rejeitada antes do download ou da persistência
    E a matriz de cobertura deve permanecer inalterada

  Cenário: Consultar votação por seção e local de votação
    Dado que a extensão territorial oficial da eleição foi publicada
    Quando o parlamentar selecionar o nível "seção"
    Então cada resultado deve identificar a seção e o local de votação
    E a soma nominal deve permanecer reconciliada com o dataset eleitoral base

  Cenário: Rotular bairro derivado do local de votação
    Dado que o cadastro oficial do local informa o bairro
    Quando o parlamentar consultar o nível "bairro"
    Então o resultado deve ser rotulado como mapeamento derivado
    E o sistema não deve apresentar o bairro como limite geográfico oficial

  Cenário: Informar granularidade detalhada indisponível
    Dado que a eleição possui apenas resultados por município e zona
    Quando o parlamentar solicitar resultados por seção
    Então a API deve responder com erro de validação
    E deve listar somente os níveis efetivamente disponíveis
  Cenário: Restringir o contexto às eleições do parlamentar
    Dado que as candidaturas próprias foram vinculadas pelo CPF oficial
    Quando qualquer fluxo operacional solicitar a lista de eleições
    Então devem ser exibidas somente as eleições em que ele participou
    E a participação mais recente deve ser selecionada inicialmente
    E uma eleição fora desse conjunto não deve ampliar o contexto pela URL

  Cenário: Vincular identidade eleitoral automaticamente
    Dado que o CPF do parlamentar corresponde ao CPF de uma candidatura no cadastro oficial sincronizado
    Quando o parlamentar abre o módulo
    Então todas as participações correspondentes devem compor o contexto operacional
    E o CPF não deve aparecer na API, nos logs ou na auditoria eleitoral

  Cenário: Não presumir identidade eleitoral por atributo fraco
    Dado que não existe correspondência determinística de CPF
    Quando o parlamentar abre Resultados, Comparações, GabIA ou Simulador
    Então o sistema deve informar CPF ausente, fonte indisponível ou divergência
    E não deve vincular candidatura por semelhança de nome, partido ou número

  Cenário: Explorar outras eleições sem contaminar o mandato
    Quando o parlamentar abre “Explorar outras eleições”
    Então deve poder consultar o catálogo público completo e pesquisar candidaturas
    Mas a eleição explorada não deve aparecer nos combos operacionais
    Quando a reconciliação automática não puder concluir
    Então o titular deve poder confirmar manualmente uma candidatura como contingência
    E a participação deve ser auditada e identificada como confirmação manual

  Cenário: Manter preferências e segmentos privados por usuário
    Dado que dois usuários autorizados acessam o mesmo gabinete
    Quando cada um salva seus indicadores e segmentos territoriais
    Então cada usuário deve recuperar somente suas próprias configurações
    E um segmento deve aceitar apenas unidades agregadas da eleição selecionada

  Cenário: Preparar briefing antes de uma visita territorial
    Dado que existe um evento institucional agendado em um território com snapshot publicado
    Quando o usuário solicita o briefing pré-visita
    Então deve receber fatos eleitorais e operacionais agregados e a agenda futura do território
    E o conteúdo deve ser rotulado como rascunho editável sujeito à revisão humana

  Cenário: Preservar privacidade em heatmaps, clusters e rotas
    Dado que existem grupos suprimidos, compromissos públicos e eventos ligados a cidadãos
    Quando o usuário consulta as camadas geográficas e a rota da agenda
    Então grupos suprimidos e eventos ligados a cidadãos não devem ser retornados
    E somente coordenadas de locais públicos confirmados podem compor o mapa e a rota
    E nenhum endereço residencial deve ser exposto

  Cenário: Distribuir relatório eleitoral recorrente internamente
    Dado que existe um relatório-base autorizado
    Quando o usuário agenda uma recorrência para usuários internos ativos
    Então o worker deve criar um job por destinatário através do outbox
    E deve registrar a última execução e calcular a próxima
    E destinatários externos ou inativos devem ser rejeitados
