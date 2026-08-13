# Requisitos Funcionais

## Identidade e acesso

- **RF-001** O sistema deve autenticar usuários por e-mail, senha e, opcionalmente, provedor OIDC.
- **RF-002** O sistema deve suportar perfis e permissões por tenant.
- **RF-003** O sistema deve permitir MFA para perfis privilegiados.
- **RF-004** O sistema deve registrar log de acessos e ações críticas.

## Cidadãos e organizações

- **RF-010** Cadastrar pessoa física com dados mínimos necessários.
- **RF-011** Cadastrar organizações, associações, escolas, empresas e lideranças.
- **RF-012** Permitir múltiplos telefones, e-mails e endereços.
- **RF-013** Exibir histórico consolidado de solicitações e interações.
- **RF-014** Registrar preferências de contato e consentimentos. **Implementado no P1.**
- **RF-015** Permitir pseudonimização e anonimização conforme política de retenção. **Implementado no P1.**
- **RF-CID-001** Disponibilizar cadastro e edição de cidadão em uma área persistente da tela, sem modal, preservando o contexto da agenda e da pessoa selecionada.
- **RF-CID-002** Registrar, no cadastro inicial, foto, nome, nome social, telefone, e-mail, endereço, profissão, data de nascimento, CPF, título de eleitor, canal preferencial, base legal e autorizações independentes de contato e divulgação pública; somente o nome exige entrada do usuário, sem prejuízo de validações condicionais dos valores informados e da resolução da base legal pela política do tenant.
- **RF-CID-003** Permitir obter a foto pela câmera do dispositivo, mediante ação e permissão explícitas, com alternativa de escolher arquivo, reenquadrar, substituir e remover antes de salvar.
- **RF-CID-004** Consultar cidadãos em diretório com aparência de agenda telefônica, pesquisa por nome, nome social, CPF ou contato, agrupamento e navegação alfabética, paginação incremental e estados de carregamento, vazio e erro.
- **RF-CID-005** Alertar sobre homônimos antes da criação e permitir abrir e reutilizar um cadastro existente ou continuar com um novo cadastro após confirmação explícita.
- **RF-CID-006** Impedir CPF duplicado no mesmo tenant e identificar, na resposta de conflito, o cidadão já vinculado ao documento para que o usuário possa abrir o cadastro existente.
- **RF-CID-007** Resolver automaticamente bairro e território a partir do endereço validado, exibi-los como dados derivados somente para consulta e permitir nova tentativa quando a resolução falhar.
- **RF-CID-017** Permitir que administradores mantenham aliases e importem geometrias GeoJSON Polygon/MultiPolygon para territórios, resolvendo o endereço primeiro por ponto-em-polígono e depois por nome ou alias normalizado. **Implementado.**
- **RF-CID-018** Paginar agenda, solicitações e histórico por cursores opacos assinados. **Implementado.**
- **RF-CID-019** Exibir histórico funcional autorizado sem valores pessoais, identificando ação, usuário, horário e nomes dos campos alterados. **Implementado.**
- **RF-CID-020** Impedir sobrescrita silenciosa com ETag/If-Match e orientar releitura quando a versão estiver desatualizada. **Implementado.**
- **RF-CID-021** Registrar métricas do fluxo sem termos de busca nem conteúdo pessoal. **Implementado.**
- **RF-CID-008** Permitir relacionar um cidadão como responsável por uma ou mais organizações por meio de Search-Select acessível.
- **RF-CID-009** Exibir, ao selecionar um cidadão, suas solicitações em ordem decrescente de abertura e permitir abrir uma solicitação na tela de atendimento sem perder o vínculo com o cidadão.
- **RF-CID-010** Permitir iniciar uma nova solicitação a partir de cidadão recém-cadastrado ou selecionado, pré-preenchendo o vínculo e os dados reutilizáveis.
- **RF-CID-011** Exibir como somente leitura a data de cadastro, o último contato e o usuário responsável pelo atendimento mais recente, com estado explícito quando não houver informação.
- **RF-CID-012** Registrar o usuário e o instante da criação e manter histórico auditável de alterações, com ator, instante e campos alterados, sem expor valores pessoais em logs técnicos.
- **RF-CID-013** Permitir marcar e desmarcar cidadão como VIP, representado por estrela com rótulo acessível e alteração auditada.
- **RF-CID-014** Preparar ingestão de mensagens de WhatsApp e e-mail para sugerir criação ou associação de cidadão, exigindo revisão humana antes de persistir novo cadastro ou substituir dados existentes.

## Solicitações

- **RF-020** Registrar solicitação oriunda de atendimento presencial, telefone, WhatsApp, e-mail, formulário, rede social ou visita. **Implementado na Release 6 para caixa multicanal, formulário público e visita.**
- **RF-021** Gerar protocolo único por tenant.
- **RF-022** Classificar por categoria, subcategoria, tema, território e órgão responsável.
- **RF-023** Definir prioridade, impacto, urgência e prazo.
- **RF-024** Atribuir responsável e equipe.
- **RF-025** Registrar localização textual e geográfica.
- **RF-026** Anexar fotos, vídeos, áudios e documentos.
- **RF-027** Registrar histórico imutável de alterações.
- **RF-028** Relacionar solicitações duplicadas ou correlatas.
- **RF-029** Criar tarefas e encaminhamentos.
- **RF-030** Registrar resposta de órgão externo.
- **RF-031** Encerrar solicitação com motivo e evidência.
- **RF-032** Reabrir solicitação quando surgirem novas informações.
- **RF-033** Permitir consulta pública do status por protocolo e chave segura.

## Atendimento e comunicação

- **RF-040** Registrar interações de entrada e saída. **Implementado no P1 e ampliado na Release 6 com caixa multicanal.**
- **RF-041** Utilizar templates de resposta. **Implementado no P1.**
- **RF-042** Agendar retorno. **Implementado no P1.**
- **RF-043** Enviar notificações configuráveis.
- **RF-044** Registrar tentativa de contato.
- **RF-045** Respeitar o canal preferencial do cidadão.
- **RF-046** Manter trilha das mensagens enviadas. **Implementado no P1 e ampliado na Release 6 para mensagens recebidas por canal.**

## Agenda e atuação externa

- **RF-050** Criar compromissos, visitas, reuniões e audiências. **Implementado na Release 6.**
- **RF-051** Relacionar agenda a cidadãos, organizações, bairros e solicitações. **Implementado na Release 6.**
- **RF-052** Sugerir roteiros de visita. **Implementado na Release 6 por concentração de demandas abertas e prioridade.**
- **RF-053** Registrar ata, fotos, participantes e pendências. **Implementado na Release 6.**
- **RF-054** Criar solicitações a partir de uma visita. **Implementado na Release 6.**
- **RF-055** Exibir a agenda institucional nos modos dia, semana e mês, com navegação temporal e identidade visual consistente com o restante do sistema. **Implementado.**
- **RF-056** Permitir criar e editar compromissos com tipo, título, descrição, local, início, fim, presença parlamentar e múltiplos participantes pesquisáveis entre os usuários ativos do gabinete, excluído o Parlamentar. **Implementado.**
- **RF-057** Ao alterar o início de um compromisso, sugerir automaticamente o término uma hora depois, mantendo a validação de término posterior ao início. **Implementado.**
- **RF-058** Gerar PDF executivo dos compromissos da semana de referência, com identidade do gabinete, indicadores, alertas e agenda agrupada por dia. **Implementado.**

## Produção legislativa

- **RF-060** Criar minuta a partir de solicitação. **Implementado no P2.**
- **RF-061** Suportar indicação, requerimento, ofício, moção, pedido de informação e projeto de lei. **Implementado no P2.**
- **RF-062** Aplicar templates configuráveis. **Implementado no P2.**
- **RF-063** Relacionar uma proposição a uma ou mais solicitações. **Implementado no P2.**
- **RF-064** Controlar versões. **Implementado no P2 com histórico, comparação e restauração auditável.**
- **RF-065** Implementar revisão e aprovação com matriz explícita de ações por papel e função. **Implementado no P2; matriz consolidada na evolução de retificações legislativas.**
- **RF-066** Exportar para DOCX e PDF. **Implementado no P2.**
- **RF-067** Registrar protocolo e tramitação. **Implementado no P2 pelo adaptador manual; integração externa seguirá a porta canônica definida no [ADR-013](../adr/ADR-013-generic-legislative-integration.md).**
- **RF-067A** Configurar por tenant uma integração legislativa que declare fornecedor, versão, capabilities, mapeamentos canônicos e referência opaca de segredo, mantendo `MANUAL` como padrão obrigatório. **Especificado; pendente.**
- **RF-067B** Executar submissões externas por operação assíncrona, idempotente e auditável, sempre iniciada por ação humana explícita e sem bloquear a gestão interna da minuta. **Especificado; pendente.**
- **RF-067C** Importar andamentos por webhook ou polling somente quando a capability estiver disponível, deduplicando eventos e preservando a timeline append-only. **Especificado; pendente.**
- **RF-067D** Exibir diagnóstico, última sincronização, divergências, eventos não mapeados e reconciliação necessária sem revelar credenciais ou payload sensível. **Especificado; pendente.**
- **RF-068** Pesquisar proposições semelhantes. **Implementado no P2 com embeddings locais, filtros e fallback lexical.**
- **RF-069** Retificar erro material de protocolo ou andamento por evento compensatório append-only, com motivo obrigatório, vínculo ao registro substituído, recálculo do estado vigente e auditoria. **Implementado.**

## Fiscalização

- **RF-070** Criar ação de fiscalização. **Implementado na Release 6.**
- **RF-071** Registrar local, fotos, achados e responsáveis. **Implementado na Release 6.**
- **RF-072** Gerar relatório. **Implementado na Release 6.**
- **RF-073** Relacionar fiscalização a contratos, serviços públicos e solicitações. **Implementado parcialmente na Release 6 com órgão externo e solicitação.**
- **RF-074** Acompanhar providências decorrentes. **Implementado na Release 6.**
- **RF-075** Criar automaticamente uma pendência de relatório quando um compromisso do tipo Fiscalização ultrapassar seu término, visível somente aos participantes do compromisso. **Implementado.**
- **RF-076** Notificar o participante sobre fiscalizações não reportadas ao entrar na aplicação e manter o lembrete até a conclusão válida do relatório. **Implementado.**
- **RF-077** Permitir registrar uma fiscalização diretamente em campo, sem compromisso prévio na agenda, em rascunho ou já concluída. **Implementado.**
- **RF-078** Permitir anexar fotos capturadas pelo dispositivo e documentos, editar a observação de cada evidência e realizar download autorizado, com vínculo opcional a uma solicitação de cidadão. **Implementado.**

## Dashboards e relatórios

- **RF-080** Exibir volume por status, categoria, bairro, canal e período. **Implementado na Release 5.**
- **RF-081** Exibir tempo médio de triagem, primeira resposta e resolução. **Implementado parcialmente na Release 5 com primeira resposta, encaminhamento, encerramento e resolução.**
- **RF-082** Exibir taxa de reabertura e reincidência. **Implementado na Release 5 com contagem de reaberturas e alertas de reincidência.**
- **RF-083** Exibir mapa de calor. **Base implementada na Release 5; consistência integral dos filtros, interação e drill-down planejados para os incrementos 5.1 e 5.2.**
- **RF-084** Permitir filtros e exportação. **Filtros básicos implementados na Release 5; contrato analítico único e exportação agregada permanecem planejados para 5.1 e 5.3.**
- **RF-085** Gerar relatório completo do mandato para intervalo definido por data inicial e data final. **Evoluído a partir do relatório mensal da Release 5.**
- **RF-086** Exibir indicadores por órgão destinatário. **Implementado na Release 5.**
- **RF-087** Exibir solicitações sem retorno ou próximas do prazo. **Implementado na Release 5 para prazos, retornos e fila prioritária.**
- **RF-088** Permitir selecionar relatório Operacional ou Insights do Mandato e apresentar indicadores, gráficos e um semáforo de problemas, avisos e resultados positivos do período. **Implementado.**
- **RF-089** No relatório Operacional, exibir eficiência da equipe sem incluir o Parlamentar, horário de maior atendimento, cidadão mais atuante, regiões e demandas recorrentes, documentos legislativos relacionados e ações geradas. **Implementado.**
- **RF-REP-001** Exportar o relatório selecionado em PDF executivo com composição visual adequada à prestação de contas e apresentação institucional do gabinete. **Implementado.**
- **RF-TERR-001** Aplicar o mesmo contexto de tenant, período, comparação, categoria, canal, território, órgão, status, prioridade e responsável a todas as métricas, rankings, pontos e células do painel territorial.
- **RF-TERR-002** Diferenciar território identificado, coordenada aproximada e coordenada verificada, expondo fonte, método, confiança e data de atualização sem tratar aproximação como verificação.
- **RF-TERR-003** Validar coordenadas contra a jurisdição configurada e encaminhar endereços não resolvidos, ambíguos ou externos para revisão autorizada.
- **RF-TERR-004** Permitir selecionar território, hotspot ou alerta e abrir as solicitações subjacentes autorizadas com período e filtros preservados. **Implementado no incremento 5.2 para território, hotspot e exemplos autorizados.**
- **RF-TERR-005** Exibir comparação com período anterior equivalente, incluindo base, janela, método, tamanho da amostra e estado de amostra insuficiente. **Implementado no incremento 5.2.**
- **RF-TERR-006** Disponibilizar tabela territorial acessível e funcionalmente equivalente ao mapa, com volume, atraso, solução, tempos, tendência e qualidade do dado. **Implementado no incremento 5.2.**
- **RF-TERR-007** Permitir criar tarefa, agenda, visita, roteiro ou encaminhamento a partir de um território ou alerta, preservando proveniência, responsável, prazo, estado e evidência.
- **RF-TERR-008** Controlar o ciclo de vida de alertas territoriais nos estados novo, em análise, com ação, resolvido e descartado com justificativa.
- **RF-TERR-009** Restringir agregados, exemplos, protocolos, pontos e exportações por permissão e limiar de privacidade calculado no menor recorte retornado.
- **RF-TERR-010** Permitir salvar visões territoriais e configurar notificações por território, tema, severidade e frequência sem registrar conteúdo pessoal na telemetria. **Visões salvas implementadas no incremento 5.2; notificações permanecem no 5.4.**
- **RF-TERR-011** Exportar somente dados territoriais agregados e autorizados, incluindo período, filtros, método, qualidade e regras de supressão.
- **RF-TERR-012** Registrar telemetria minimizada do funil de abertura, filtragem, investigação e ação para medir utilidade da feature sem armazenar termos, protocolos ou coordenadas.

## Administração

- **RF-090** Parametrizar categorias, territórios, status e SLA.
- **RF-091** Configurar templates. **Implementado no P2.**
- **RF-092** Configurar integrações. **Implementado na Release 6 como cadastro tenant-safe de configurações; conectores externos ficam para incrementos por provedor.**
- **RF-093** Gerenciar bases documentais RAG privadas. **Implementado nas Releases 4 e 4.1 com ingestão assíncrona, versionamento, níveis de acesso, contexto transacional, RLS, constraints compostas e armazenamento segregado.**
- **RF-094** Configurar retenção, anonimização e auditoria. **Implementado no P1.**
- **RF-095** Administrar coleções privadas e selecionar coleções globais opcionais. **Implementado parcialmente: adesão a coleções globais está disponível; coleções privadas administráveis permanecem planejadas.**
- **RF-096** Configurar atualização automática, versão fixada ou fork privado para uma fonte global. **Implementado parcialmente para atualização automática e versão fixada; fork privado permanece planejado.**
- **RF-097** Exibir em respostas e citações se a fonte é global ou privada. **Implementado na recuperação hierárquica.**
- **RF-098** Monitorar e governar a ingestão automática das entidades internas elegíveis no RAG Privado, conforme finalidade, base legal, retenção e nível de acesso. **Implementado para solicitações, interações, encaminhamentos/respostas oficiais, minutas, tramitações, fontes normativas, OCR/transcrições revisados, atas concluídas, fiscalizações concluídas e memórias temáticas.**
- **RF-099** Consultar histórico de ingestão, concessões, forks, recuperação e feedback do próprio tenant. **Implementado parcialmente para ingestão, concessões, consultas e feedback; forks e visão administrativa consolidada permanecem planejados.**
- **RF-100** Cadastrar e versionar projetores autorizados por módulo, tipo de entidade e ação, com allowlist de campos e política de elegibilidade. **Implementado como registry em código para todas as fontes operacionais cobertas; administração dinâmica permanece fora do escopo atual.**
- **RF-101** Exibir estado, origem, versão, hash, finalidade, base legal, ACL, retenção, erro e última projeção de cada fonte operacional. **Implementado na listagem administrativa tenant-scoped.**
- **RF-102** Permitir reprocessamento, reconciliação, despublicação e purge autorizados, com auditoria e execução assíncrona. **Implementado para reprocessamento, reconciliação e purge dirigido pelo ciclo de vida da origem; endpoint de purge manual permanece reservado.**
- **RF-103** Propagar criação, atualização, cancelamento, exclusão, anonimização e expiração da entidade para o conhecimento derivado. **Implementado com despublicação imediata, tombstone e purge idempotente.**
- **RF-104** Rotear perguntas entre recuperação documental, consulta estruturada tenant-scoped ou composição híbrida, informando o método usado. **Implementado automaticamente no endpoint principal, preservando também o endpoint estruturado explícito.**
- **RF-105** Consultar contagens, estados, prazos, agrupamentos e indicadores por read models estruturados, com filtros reproduzíveis. **Implementado para solicitações, encaminhamentos, tramitações, agenda e fiscalizações, com método, dataset, métrica, agrupamento, filtros e período no retorno.**
- **RF-106** Gerar memórias temáticas agregadas e anonimizadas por tema, território, período e resultado, respeitando agregação mínima. **Implementado com reconstrução determinística e limiar mínimo configurável por ambiente.**
- **RF-107** Cadastrar perguntas reais e documentos esperados ou expectativa de recusa por tenant, executar avaliação por `k` e preservar o histórico de métricas. **Implementado.**
- **RF-108** Registrar revisões imutáveis de feedback, motivos normalizados, método/filtros esperados e julgamentos por fonte, preservando compatibilidade com a avaliação atual. **Implementado na Release 4.7.**
- **RF-109** Listar e moderar feedback do próprio tenant nos estados pendente, aprovado, quarentena, rejeitado, revogado e superado. **Implementado na Release 4.7.**
- **RF-110** Executar compilação idempotente de sinais aprovados e consultar histórico, métricas, erros e proveniência da execução. **Implementado na etapa 4.7.3.**
- **RF-111** Gerenciar artefatos de aprendizado candidatos, aprovados, ativos, substituídos e revogados por tenant e tipo. **Implementado nas etapas 4.7.3 e 4.7.4.**
- **RF-112** Ativar, aplicar em canário e reverter artefatos de aprendizado com auditoria e apenas uma versão ativa por tenant e tipo. **Implementado na etapa 4.7.4, incluindo rollback automático por regressão online.**
- **RF-113** Exibir na consulta as versões de perfil de ranking, exemplos de roteamento ou outros artefatos que influenciaram a resposta. **Implementado para os artefatos que efetivamente alteram ranking ou roteamento.**
- **RF-114** Promover feedback aprovado de forma explícita e idempotente para o dataset tenant-scoped, preservando proveniência e diagnóstico. **Implementado na Release 4.7.**
- **RF-115** Avaliar documentos esperados, hard negatives, rota, filtros e recusa nos casos curados, sem alterar o comportamento dos casos manuais existentes. **Implementado na Release 4.7.**
- **RF-116** Desativar automaticamente casos curados cujo feedback ou fonte deixe de ser elegível. **Implementado na Release 4.7.**
- **RF-117** Capturar consultas problemáticas como casos de regressão tenant-scoped, com taxonomia, severidade, tags, fontes esperadas, hard negatives e snapshot minimizado e idempotente do baseline. **Implementado no incremento 4.8.1.**
- **RF-118** Formar o pool documental por PostgreSQL FTS e `pgvector`, fundir os canais por RRF e aplicar tenant, ACL, vigência, retenção e publicação antes do ranking final. **Implementado no incremento 4.8.2.**
- **RF-119** Aplicar reranking neural configurável sobre candidatos elegíveis, validar integralmente o retorno do modelo e preservar o ranking híbrido em caso de falha. **Implementado no incremento 4.8.3.**
- **RF-120** Auditar e medir aplicação, modelo, versão do prompt, pontuações, justificativas e fallback do reranker neural. **Implementado no incremento 4.8.3.**
- **RF-121** Entender consultas documentais e aceitar filtros de tema, tipo documental, órgão, jurisdição e período sem afrouxar os filtros obrigatórios de segurança. **Implementado no incremento 4.8.4.**
- **RF-122** Recuperar a consulta original e expansões controladas, fundir seus resultados antes do reranking e expor o plano aplicado. **Implementado no incremento 4.8.4.**
- **RF-123** Produzir resposta substantiva com afirmações vinculadas somente aos chunks autorizados e sanitizados que compõem o contexto do gerador. **Implementado no incremento 4.8.5.**
- **RF-124** Validar as citações de cada afirmação, recusar a resposta quando o contrato ou o suporte falhar e expor citações rastreáveis até chunk, documento, versão e escopo. **Implementado no incremento 4.8.5.**
- **RF-125** Criar calibração tenant-scoped de thresholds permitidos, comparar candidato e baseline no mesmo dataset e preservar parâmetros, métricas, decisão e auditoria. **Implementado no incremento 4.9.1.**
- **RF-126** Versionar a calibração aprovada como `QUALITY_PROFILE` e aplicar seus parâmetros somente às consultas incluídas no canário determinístico. **Implementado no incremento 4.9.1.**
- **RF-127** Submeter cada afirmação gerada a verificação semântica independente e expor modelo, prompt, score, contradição, justificativa e fallback. **Implementado no incremento 4.9.1.**
- **RF-128** Monitorar fallback e rejeição semântica do perfil ativo e restaurar atomicamente a versão anterior quando os gates online forem violados. **Implementado no incremento 4.9.1.**
- **RF-129** Iniciar automaticamente o rollout de um `QUALITY_PROFILE` aprovado nas etapas configuradas e promover somente depois de validar 100% do tráfego. **Implementado no incremento 4.9.2.**
- **RF-130** Servir o perfil baseline fora do bucket candidato durante o canário e preservar decisão e métricas independentes por etapa. **Implementado no incremento 4.9.2.**
- **RF-131** Reverter automaticamente o rollout por regressão de fallback, rejeição semântica, recusa ou feedback negativo. **Implementado no incremento 4.9.2.**
- **RF-132** Listar calibrações com perfil ativo, etapa, próxima avaliação e histórico no painel administrativo do tenant. **Implementado no incremento 4.9.2.**
- **RF-133** Configurar e auditar provider, endpoint, modelo, versão e latência do classificador NLI independentemente do gerador. **Implementado no incremento 4.9.3.**
- **RF-134** Pular o reranker neural quando o ranking híbrido já possuir liderança inequívoca, registrando score, margem e motivo. **Implementado no incremento 4.9.3.**
- **RF-135** Expor tempos de recuperação, geração, validação, NLI e total, juntamente com orçamento e indicador de estouro. **Implementado no incremento 4.9.3.**
- **RF-136** Considerar a taxa de estouro do orçamento de latência nos gates do rollout progressivo. **Implementado no incremento 4.9.3.**
- **RF-137** Validar e executar versões imutáveis do dataset adversarial de prompt injection, separando regressão, holdout, ataques e controles benignos. **Especificado no incremento 5.1.**
- **RF-138** Registrar para cada avaliação de conteúdo a decisão, ação, score, categorias, sinais e versões da política, detector e classificador. **Implementado no incremento 5.2 para versões privadas e globais, fontes operacionais e feedback.**
- **RF-139** Listar conteúdo em quarentena sem expor o payload malicioso, permitir revisão autorizada e reprocessar somente após decisão auditável. **Implementado no incremento 5.3 para bases privadas e catálogo global.**
- **RF-140** Revarrer o acervo por versão da política, despublicar imediatamente conteúdo reclassificado e purgar chunks, embeddings e outros derivados. **Implementado no incremento 5.6 para acervo privado, global e anexos, com progresso consultável e execução retomável.**
- **RF-141** Normalizar mensagens de WhatsApp e e-mail em envelope canônico idempotente por tenant, canal e identificador externo. **Implementado no incremento 9.5.**
- **RF-142** Resolver candidatos a cidadão por contato normalizado exclusivamente dentro do tenant, sem usar nome ou conteúdo livre como prova de identidade. **Implementado no incremento 9.5.**
- **RF-143** Disponibilizar fila autenticada para vincular cidadão existente ou descartar sugestão, registrando usuário, instante e decisão. **Implementado no incremento 9.5.**
- **RF-144** Impedir criação, mesclagem ou sobrescrita automática de cidadão a partir de canais externos. **Implementado no incremento 9.5.**
- **RF-145** Preparar cadastro de cidadão a partir de revisão pendente, preenchendo somente dados mínimos do envelope e exigindo confirmação humana de nome, contato e base legal. **Implementado no incremento 9.6.**
- **RF-146** Concluir o cadastro e vincular atomicamente cidadão, mensagem e revisão, preservando a validação de CPF, o alerta de homônimo e a proveniência minimizada. **Implementado no incremento 9.6.**
- **RF-147** Operar a fila por responsável, canal, estado e vencimento, com SLA, contadores, métricas e reabertura justificada. **Implementado no incremento 9.6.**
- **RF-148** Configurar base legal padrão, SLA e retenção por tenant e minimizar, sob ação autorizada e auditada, os envelopes concluídos vencidos. **Implementado no incremento 9.6.**
- **RF-149** Visualizar em mapa a jurisdição e os polígonos territoriais do tenant, diferenciando seleção e estado ativo. **Implementado no incremento 9.7.**
- **RF-150** Desenhar, editar e remover vértices ou partes de polígonos territoriais no mapa, mantendo importação e edição textual de GeoJSON como alternativas. **Implementado no incremento 9.7.**
- **RF-151** Editar aliases de resolução junto ao mapa e sincronizar a seleção cartográfica com a lista administrativa. **Implementado no incremento 9.7.**
- **RF-152** Exibir barra alfabética A–Z no diretório, habilitando somente iniciais com cidadãos ativos no tenant e filtrando os cartões pela inicial selecionada. **Implementado no aprimoramento da agenda v2.**
- **RF-153** Apresentar no cartão do cidadão nome de exibição, telefone, e-mail, localidade, profissão, canal preferencial e marcador VIP quando disponíveis. **Implementado no aprimoramento da agenda v2.**
