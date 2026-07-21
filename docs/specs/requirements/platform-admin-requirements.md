# Administrador Geral do GabFlow

## Objetivo

Garantir que cada novo gabinete contratado seja configurado de forma segura, organizada e padronizada antes do inicio da operacao. A plataforma deve operar como multi-gabinete, mantendo usuarios, dados, configuracoes, solicitacoes, documentos, indicadores e bases de conhecimento isolados por gabinete.

## Perfil

O Administrador Geral do GabFlow administra a plataforma como um todo e nao pertence a um gabinete especifico.

## Requisitos funcionais

- **RF-120** Autenticar Administrador Geral sem vinculo a tenant.
- **RF-121** Cadastrar novos gabinetes com nome, slug, plano, contrato, limites e modulos.
- **RF-122** Ativar, suspender, inativar ou cancelar gabinetes e contratos.
- **RF-123** Definir plano contratado, limite de usuarios e limite de armazenamento.
- **RF-124** Controlar modulos habilitados por gabinete.
- **RF-125** Acompanhar consumo consolidado da plataforma e consumo agregado por gabinete.
- **RF-126** Administrar parametros gerais, modelos globais, flags, politicas de seguranca e retencao.
- **RF-127** Gerenciar provedores globais de IA, LLM, OCR, mapas e mensageria.
- **RF-128** Monitorar disponibilidade, erros, integracoes e alertas consolidados.
- **RF-129** Prestar suporte aos administradores dos gabinetes por acesso excepcional registrado.
- **RF-130** Redefinir administradores de gabinete.
- **RF-131** Administrar versoes e funcionalidades globais.
- **RF-132** Consultar trilhas de auditoria administrativa da plataforma.

## Restricoes de privacidade

- O Administrador Geral nao deve acessar livremente conteudo de solicitacoes, documentos ou dados pessoais de cidadaos.
- Consultas de plataforma devem retornar metadados, contagens e indicadores agregados sempre que possivel.
- Acesso excepcional a dados internos de gabinete exige solicitacao formal, autorizacao, motivo tecnico ou necessidade justificada.
- Todo acesso excepcional deve registrar gabinete, solicitante, autorizador, motivo, escopo, usuario executor, data, IP e user-agent.

## Area de trabalho

A area de trabalho do Administrador Geral deve conter:

- painel consolidado da plataforma;
- gestao de gabinetes e contratos;
- consulta de consumo agregado;
- parametros, modelos e provedores globais;
- suporte auditado aos gabinetes;
- auditoria administrativa;
- indicadores de disponibilidade, erros e integracoes.

## Criterios de aceite

- Usuario `platform_admin` autentica sem informar ambiente.
- Admin de gabinete nao acessa `/api/v1/platform/*`.
- Cadastro e atualizacao de gabinetes registram auditoria administrativa.
- Transicao contratual exige motivo e registra historico administrativo.
- Contratos suspensos ou cancelados bloqueiam login e APIs autenticadas do gabinete.
- Modulo desabilitado bloqueia menu, busca global e endpoint tenant-scoped correspondente.
- Consumo por gabinete nao retorna titulo, descricao, documentos ou dados pessoais.
- Suporte excepcional so e registrado com gabinete, solicitante, motivo e escopo.
