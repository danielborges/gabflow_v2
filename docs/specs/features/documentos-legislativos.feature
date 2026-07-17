# language: pt
Funcionalidade: Geração assistida de documentos legislativos

  Cenário: Criar indicação a partir de uma solicitação
    Dado que a solicitação contém fatos, local e órgão competente
    Quando o assessor solicitar uma minuta de indicação
    Então o sistema deve gerar um rascunho
    E deve relacionar a minuta à solicitação
    E deve apontar fontes utilizadas
    E deve exigir revisão humana antes da aprovação

  Cenário: Criar minuta vinculada a múltiplas solicitações
    Dado que existem demandas relacionadas no mesmo tenant
    Quando o assessor selecionar uma solicitação principal e outras relacionadas
    Então o sistema deve vincular de uma a vinte solicitações à minuta
    E deve preservar a identificação da solicitação principal
    E deve enviar ao modelo somente as solicitações explicitamente selecionadas
    E deve impedir IDs repetidos ou pertencentes a outro tenant

  Cenário: Gerenciar templates legislativos visualmente
    Dado que o usuário possui perfil gestor
    Quando cadastrar ou editar o nome, tipo e estrutura de um template
    Então o sistema deve apresentar uma pré-visualização textual segura
    E deve salvar o template somente no tenant atual
    E deve registrar a alteração na auditoria

  Cenário: Desativar template sem apagar o histórico
    Dado que um template já foi utilizado em uma minuta
    Quando um gestor desativar o template
    Então o vínculo histórico deve ser preservado
    E o template não deve aparecer na criação de novas minutas
    E o gestor deve poder consultar e reativar o template

  Cenário: Ausência de fundamentação
    Dado que não há fonte normativa suficiente
    Quando a IA gerar uma minuta
    Então o sistema deve marcar a fundamentação como pendente
    E não deve inventar dispositivo legal

  Cenário: Recuperar fundamentação normativa automaticamente
    Dado que o tenant possui fontes normativas ativas, versionadas e vigentes
    Quando o worker concluir a geração de uma minuta
    Então o sistema deve recuperar fontes por similaridade semântica e lexical
    E deve informar score, modelo, versão, vigência e referência de cada fonte
    E deve tratar o conteúdo recuperado como dado, nunca como instrução
    E não deve aplicar nenhuma fonte automaticamente

  Cenário: Confirmar fundamentação recuperada
    Dado que o sistema sugeriu fontes normativas para uma minuta editável
    Quando o assessor selecionar fontes e informar o motivo
    Então o sistema deve aceitar somente fontes da última recuperação
    E deve validar tenant, ativação e vigência novamente
    E deve incluir citação, versão e checksum na fundamentação
    E deve criar uma nova versão imutável e registrar a decisão na auditoria

  Cenário: Manter recuperação normativa disponível sem embeddings
    Dado que o Ollama ou o modelo de embeddings está indisponível
    Quando o sistema recuperar fundamentação
    Então deve utilizar a similaridade lexical local configurada
    E deve sinalizar o fallback ao usuário
    E não deve consultar fontes de outro tenant

  Cenário: Recuperar proposições semelhantes do mesmo tenant
    Dado que existem proposições legislativas anteriores do gabinete
    Quando a IA concluir uma nova minuta
    Então o sistema deve sugerir proposições semanticamente semelhantes
    E não deve recuperar documentos pertencentes a outro tenant

  Cenário: Pesquisar precedentes por significado
    Dado que o gabinete possui proposições com vocabulários diferentes sobre o mesmo tema
    Quando o usuário pesquisar um problema ou providência em linguagem natural
    Então o sistema deve comparar embeddings locais do conteúdo legislativo
    E deve ordenar os resultados por similaridade semântica
    E deve permitir filtrar por tipo e status da proposição
    E deve informar o modelo, o limiar e os motivos do resultado

  Cenário: Manter a busca disponível sem o modelo de embeddings
    Dado que o Ollama ou o modelo de embeddings está indisponível
    Quando o usuário pesquisar precedentes
    Então o sistema deve utilizar a similaridade lexical local configurada
    E deve informar que o fallback foi utilizado
    E não deve consultar proposições de outro tenant

  Cenário: Revisar e versionar uma minuta
    Dado que uma minuta foi gerada como rascunho
    Quando o assessor editar e salvar o conteúdo
    Então o sistema deve criar uma nova versão imutável
    E deve manter o vínculo com as solicitações de origem
    E deve registrar a decisão na auditoria

  Cenário: Comparar e restaurar uma versão anterior
    Dado que uma minuta editável possui duas ou mais versões imutáveis
    Quando o assessor comparar quaisquer duas versões
    Então o sistema deve destacar os campos e linhas adicionadas ou removidas
    E deve identificar data, motivo e autor de cada versão
    Quando o assessor restaurar uma versão anterior informando o motivo
    Então o sistema deve criar uma nova versão com o conteúdo restaurado
    E deve preservar todos os snapshots anteriores
    E deve registrar a restauração na auditoria

  Cenário: Proteger o histórico de versões
    Dado que uma minuta pertence a outro tenant ou está em estado final
    Então o usuário não deve consultar nem restaurar suas versões
    E a versão atual não deve poder ser restaurada sobre ela mesma

  Cenário: Aprovação humana obrigatória
    Dado que a minuta foi submetida para revisão
    Quando um gestor revisar fatos, competência e fundamentação
    Então o gestor pode aprovar ou rejeitar a minuta
    E trechos sem fundamentação devem exigir confirmação explícita

  Cenário: Impedir protocolo automático
    Dado que a minuta foi aprovada
    Então a minuta deve permanecer sem protocolo
    Quando um gestor informar manualmente um protocolo externo
    Então o sistema deve registrar o número e a data na auditoria
    E nenhuma integração de protocolo deve ser acionada automaticamente

  Cenário: Registrar a tramitação após o protocolo
    Dado que uma minuta aprovada possui protocolo externo
    Quando um gestor registrar uma nova etapa, status e data de ocorrência
    Então o andamento deve ser acrescentado à timeline da minuta
    E o status atual deve refletir o andamento mais recente
    E o registro deve ser associado ao tenant e incluído na auditoria

  Cenário: Preservar o histórico de tramitação
    Dado que uma minuta possui andamentos legislativos registrados
    Então nenhum andamento deve possuir operação de edição ou exclusão
    E uma ocorrência não pode anteceder o protocolo ou o último andamento
    E usuários de outro tenant não podem consultar nem registrar andamentos
