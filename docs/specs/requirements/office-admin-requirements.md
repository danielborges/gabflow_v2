# Administrador do Gabinete

## Objetivo

Permitir que cada gabinete configure e opere sua propria estrutura interna com isolamento por tenant. O Administrador do Gabinete pertence a um gabinete especifico e e responsavel pelos parametros administrativos daquele gabinete, sem acesso a administracao global da plataforma.

## Perfil

O perfil pode ser atribuido ao vereador, ao chefe de gabinete ou a outro assessor formalmente designado. Somente usuarios com papel `admin` no gabinete podem visualizar o menu de configuracao administrativa do gabinete.

## Requisitos funcionais

- **RF-140** Cadastrar dados do vereador, incluindo nome parlamentar, nome civil, partido e contato institucional.
- **RF-141** Cadastrar informacoes do mandato, legislatura, cargo e periodo.
- **RF-142** Cadastrar assessores e demais usuarios do gabinete.
- **RF-143** Designar o chefe de gabinete.
- **RF-144** Criar usuarios e atribuir perfis e permissoes internas.
- **RF-145** Bloquear, desativar ou reativar usuarios do gabinete.
- **RF-146** Configurar categorias de solicitacoes e prazos de SLA.
- **RF-147** Configurar canais de atendimento e integracoes autorizadas do gabinete.
- **RF-148** Configurar templates de mensagens por canal e categoria.
- **RF-149** Configurar documentos legislativos e parametros de agenda.
- **RF-150** Configurar notificacoes e preferencias operacionais.
- **RF-151** Gerenciar bases documentais para RAG dentro do gabinete.
- **RF-152** Consultar auditoria interna do gabinete.
- **RF-153** Administrar consentimentos e politicas de privacidade do gabinete.
- **RF-154** Personalizar identidade visual do gabinete.
- **RF-155** Criar usuario proprio para vereador, no caso de Camaras Municipais, ou deputado estadual, no caso de Assembleias Legislativas.
- **RF-156** Permitir ao vereador/deputado estadual visualizar painel estrategico, indicadores, solicitacoes, demandas prioritarias, agenda, relatorios e prestacao de contas do mandato.
- **RF-157** Permitir ao vereador/deputado estadual aprovar documentos e comunicacoes sem liberar configuracoes tecnicas e administrativas.

## Restricoes

- Administradores de um gabinete nao podem acessar dados, configuracoes ou usuarios de outro gabinete.
- Administradores de gabinete nao podem acessar endpoints globais `/api/v1/platform/*`.
- Gestores e usuarios operacionais nao devem visualizar o menu administrativo do gabinete.
- Vereador/deputado estadual nao deve visualizar o menu administrativo do gabinete, salvo se tambem receber formalmente perfil de Administrador do Gabinete.
- Toda alteracao administrativa relevante deve registrar auditoria interna.
- A criacao de usuarios deve respeitar o limite contratado configurado pelo Administrador Geral.
- Integracoes e modulos so podem ser configurados quando estiverem habilitados para o contrato do gabinete.

## Area de trabalho

A area de trabalho do Administrador do Gabinete deve conter:

- perfil institucional do gabinete;
- gestao de usuarios, perfis e bloqueios;
- categorias, prazos e SLA;
- jurisdicao e territorio;
- canais e integracoes autorizadas;
- templates de mensagens;
- documentos legislativos e agenda;
- notificacoes;
- bases RAG;
- privacidade, consentimentos e retencao;
- identidade visual;
- auditoria interna.

## Criterios de aceite

- Usuario `admin` do gabinete ve o menu de configuracao administrativa.
- Usuario `manager` ou `staff` nao ve o menu administrativo e recebe 403 nos endpoints administrativos.
- Usuario `representative` ve areas executivas, consulta solicitacoes e indicadores, aprova minutas em revisao e recebe 403 nos endpoints administrativos.
- Administrador do Gabinete cria usuarios sem ultrapassar limite contratado.
- Administrador do Gabinete bloqueia usuario e a alteracao fica registrada em auditoria.
- Administrador do Gabinete salva dados do vereador, mandato, identidade visual e chefe de gabinete.
- Categorias, territorios, orgaos, templates e integracoes ficam isolados por tenant.
- Auditoria interna lista apenas eventos do proprio gabinete.
