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

## Produção legislativa

- **RF-060** Criar minuta a partir de solicitação.
- **RF-061** Suportar indicação, requerimento, ofício, moção, pedido de informação e projeto de lei.
- **RF-062** Aplicar templates configuráveis. **Implementado no P2.**
- **RF-063** Relacionar uma proposição a uma ou mais solicitações. **Implementado no P2.**
- **RF-064** Controlar versões. **Implementado no P2 com histórico, comparação e restauração auditável.**
- **RF-065** Implementar revisão e aprovação.
- **RF-066** Exportar para DOCX e PDF.
- **RF-067** Registrar protocolo e tramitação.
- **RF-068** Pesquisar proposições semelhantes. **Implementado no P2 com embeddings locais, filtros e fallback lexical.**

## Fiscalização

- **RF-070** Criar ação de fiscalização. **Implementado na Release 6.**
- **RF-071** Registrar local, fotos, achados e responsáveis. **Implementado na Release 6.**
- **RF-072** Gerar relatório. **Implementado na Release 6.**
- **RF-073** Relacionar fiscalização a contratos, serviços públicos e solicitações. **Implementado parcialmente na Release 6 com órgão externo e solicitação.**
- **RF-074** Acompanhar providências decorrentes. **Implementado na Release 6.**

## Dashboards e relatórios

- **RF-080** Exibir volume por status, categoria, bairro, canal e período. **Implementado na Release 5.**
- **RF-081** Exibir tempo médio de triagem, primeira resposta e resolução. **Implementado parcialmente na Release 5 com primeira resposta, encaminhamento, encerramento e resolução.**
- **RF-082** Exibir taxa de reabertura e reincidência. **Implementado na Release 5 com contagem de reaberturas e alertas de reincidência.**
- **RF-083** Exibir mapa de calor. **Implementado na Release 5.**
- **RF-084** Permitir filtros e exportação. **Filtros implementados na Release 5; exportação pendente.**
- **RF-085** Gerar relatório mensal do mandato. **Implementado na Release 5.**
- **RF-086** Exibir indicadores por órgão destinatário. **Implementado na Release 5.**
- **RF-087** Exibir solicitações sem retorno ou próximas do prazo. **Implementado na Release 5 para prazos, retornos e fila prioritária.**

## Administração

- **RF-090** Parametrizar categorias, territórios, status e SLA.
- **RF-091** Configurar templates. **Implementado no P2.**
- **RF-092** Configurar integrações. **Implementado na Release 6 como cadastro tenant-safe de configurações; conectores externos ficam para incrementos por provedor.**
- **RF-093** Gerenciar bases documentais RAG privadas. **Implementado nas Releases 4 e 4.1 com ingestão assíncrona, versionamento, níveis de acesso, contexto transacional, RLS, constraints compostas e armazenamento segregado.**
- **RF-094** Configurar retenção, anonimização e auditoria. **Implementado no P1.**
- **RF-095** Administrar coleções privadas e selecionar coleções globais opcionais. **Implementado parcialmente: adesão a coleções globais está disponível; coleções privadas administráveis permanecem planejadas.**
- **RF-096** Configurar atualização automática, versão fixada ou fork privado para uma fonte global. **Implementado parcialmente para atualização automática e versão fixada; fork privado permanece planejado.**
- **RF-097** Exibir em respostas e citações se a fonte é global ou privada. **Implementado na recuperação hierárquica.**
- **RF-098** Monitorar e governar a ingestão automática das entidades internas elegíveis no RAG Privado, conforme finalidade, base legal, retenção e nível de acesso. **Implementado para solicitações, interações, encaminhamentos/respostas oficiais, minutas, tramitações, OCR/transcrições revisados, atas concluídas, fiscalizações concluídas e memórias temáticas.**
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
