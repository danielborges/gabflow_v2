# language: pt
Funcionalidade: Insights operacionais e territoriais

  Cenário: Detectar crescimento de demanda
    Dado que existem dados suficientes dos últimos seis meses
    Quando o volume de uma categoria aumentar acima do limiar configurado
    Então o sistema deve gerar um insight
    E deve informar período, base de comparação e método
    E deve diferenciar correlação de causalidade

  Cenário: Amostra insuficiente
    Dado que um bairro possui poucas solicitações
    Quando o sistema calcular um indicador
    Então deve sinalizar baixa representatividade
    E deve aplicar regra de agregação para proteger a privacidade

  Cenário: Aplicar filtros de forma consistente no painel territorial
    Dado que o usuário selecionou período, categoria, canal e órgão
    Quando o painel territorial for recalculado
    Então indicadores, ranking, hotspots, pontos e mapa de calor devem usar o mesmo recorte
    E a resposta deve informar os filtros e o método aplicados

  Cenário: Diferenciar qualidade da localização
    Dado que existem solicitações com território identificado e coordenadas de origens distintas
    Quando o usuário consultar a cobertura territorial
    Então o sistema deve separar coordenadas aproximadas e verificadas
    E deve informar fonte, método, confiança e pendências de revisão
    E não deve contabilizar coordenada aproximada como verificada

  Cenário: Investigar um hotspot territorial
    Dado que um hotspot elegível foi exibido ao usuário
    Quando o usuário selecionar o hotspot e solicitar os casos relacionados
    Então o sistema deve abrir as solicitações autorizadas com período e filtros preservados
    E deve manter disponível uma alternativa acessível ao uso do mapa

  Cenário: Comparar território com período anterior
    Dado que existem amostras suficientes em dois períodos equivalentes
    Quando o usuário abrir o detalhamento de um território
    Então o sistema deve exibir variação de volume, atraso, solução e tempos
    E deve informar janela, denominadores e método da comparação

  Cenário: Transformar alerta territorial em ação
    Dado que um alerta territorial foi investigado
    Quando o usuário criar uma tarefa, agenda, visita, roteiro ou encaminhamento
    Então a ação deve preservar o território, os filtros, a regra e os casos autorizados de origem
    E deve registrar responsável, prazo, estado e trilha auditável

  Cenário: Proteger ponto individual no menor recorte
    Dado que um usuário não possui permissão ou que uma célula possui amostra insuficiente
    Quando o painel territorial for consultado
    Então o sistema deve retornar somente o agregado elegível
    E não deve expor protocolo, coordenada ou exportação individual

  Cenário: Medir utilidade sem registrar conteúdo pessoal
    Quando o usuário abrir, filtrar, investigar ou criar uma ação territorial
    Então o sistema deve registrar somente o estágio, o tenant e metadados operacionais permitidos
    E não deve registrar termo de busca, protocolo, endereço ou coordenada na telemetria

  Cenário: Proibir score eleitoral individual
    Quando um usuário solicitar previsão de voto de um cidadão
    Então o sistema deve recusar a geração do score
    E deve registrar o motivo da recusa
