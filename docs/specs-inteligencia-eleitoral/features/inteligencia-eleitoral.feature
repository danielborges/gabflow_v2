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
