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

- **RF-020** Registrar solicitação oriunda de atendimento presencial, telefone, WhatsApp, e-mail, formulário, rede social ou visita.
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

- **RF-040** Registrar interações de entrada e saída.
- **RF-041** Utilizar templates de resposta. **Implementado no P1.**
- **RF-042** Agendar retorno. **Implementado no P1.**
- **RF-043** Enviar notificações configuráveis.
- **RF-044** Registrar tentativa de contato.
- **RF-045** Respeitar o canal preferencial do cidadão.
- **RF-046** Manter trilha das mensagens enviadas.

## Agenda e atuação externa

- **RF-050** Criar compromissos, visitas, reuniões e audiências.
- **RF-051** Relacionar agenda a cidadãos, organizações, bairros e solicitações.
- **RF-052** Sugerir roteiros de visita.
- **RF-053** Registrar ata, fotos, participantes e pendências.
- **RF-054** Criar solicitações a partir de uma visita.

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

- **RF-070** Criar ação de fiscalização.
- **RF-071** Registrar local, fotos, achados e responsáveis.
- **RF-072** Gerar relatório.
- **RF-073** Relacionar fiscalização a contratos, serviços públicos e solicitações.
- **RF-074** Acompanhar providências decorrentes.

## Dashboards e relatórios

- **RF-080** Exibir volume por status, categoria, bairro, canal e período.
- **RF-081** Exibir tempo médio de triagem, primeira resposta e resolução.
- **RF-082** Exibir taxa de reabertura e reincidência.
- **RF-083** Exibir mapa de calor.
- **RF-084** Permitir filtros e exportação.
- **RF-085** Gerar relatório mensal do mandato.
- **RF-086** Exibir indicadores por órgão destinatário.
- **RF-087** Exibir solicitações sem retorno ou próximas do prazo.

## Administração

- **RF-090** Parametrizar categorias, territórios, status e SLA.
- **RF-091** Configurar templates. **Implementado no P2.**
- **RF-092** Configurar integrações.
- **RF-093** Gerenciar bases documentais RAG. **Implementado na Release 4 com ingestão assíncrona, versionamento e níveis de acesso.**
- **RF-094** Configurar retenção, anonimização e auditoria. **Implementado no P1.**
