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
- **RF-158** Designar Chefe de Gabinete somente a partir de usuario ativo ja cadastrado no gabinete, com perfil interno de assessor, gestor ou administrador.
- **RF-159** Atribuir ao Chefe de Gabinete permissoes adicionais de supervisao operacional sem converter automaticamente seu papel para `admin`.
- **RF-160** Permitir ao Chefe de Gabinete distribuir solicitacoes, atribuir responsaveis, acompanhar prazos, visualizar todos os atendimentos, aprovar encerramentos operacionais, organizar agenda, acompanhar produtividade, supervisionar documentos, autorizar respostas e gerar relatorios conforme modulos habilitados.
- **RF-161** Permitir que o Chefe de Gabinete supervisione documentos legislativos, incluindo rejeicao de minutas em revisao, registro de protocolo externo e acompanhamento de tramitacao, sem receber automaticamente permissao politica de aprovacao de minutas.

## Restricoes

- Administradores de um gabinete nao podem acessar dados, configuracoes ou usuarios de outro gabinete.
- Administradores de gabinete nao podem acessar endpoints globais `/api/v1/platform/*`.
- Gestores e usuarios operacionais nao devem visualizar o menu administrativo do gabinete.
- Vereador/deputado estadual nao deve visualizar o menu administrativo do gabinete, salvo se tambem receber formalmente perfil de Administrador do Gabinete.
- Chefe de Gabinete nao deve visualizar o menu administrativo do gabinete, salvo se tambem receber formalmente perfil de Administrador do Gabinete.
- Chefe de Gabinete nao deve ser automaticamente transformado em `admin`; a funcao deve ser registrada como designacao adicional auditavel.
- Usuario com perfil `representative` nao pode ser designado como Chefe de Gabinete.
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
- Usuario designado como Chefe de Gabinete permanece com seu papel original e recebe `funcoes=["chefe_gabinete"]` na sessao.
- Usuario Chefe de Gabinete com papel `staff` recebe 403 no menu administrativo, mas consegue registrar protocolo externo e tramitacao de minuta aprovada.
- Usuario `staff` nao designado Chefe de Gabinete continua recebendo 403 em acoes de supervisao legislativa restritas.
- Categorias, territorios, orgaos, templates e integracoes ficam isolados por tenant.
- Auditoria interna lista apenas eventos do proprio gabinete.
