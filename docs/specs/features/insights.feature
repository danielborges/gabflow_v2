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

  Cenário: Proibir score eleitoral individual
    Quando um usuário solicitar previsão de voto de um cidadão
    Então o sistema deve recusar a geração do score
    E deve registrar o motivo da recusa
