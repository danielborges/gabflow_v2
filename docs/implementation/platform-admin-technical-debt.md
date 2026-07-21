# Debitos Tecnicos - Administrador da Plataforma

Este documento registra pendencias tecnicas e funcionais do Administrador Geral do GabFlow para retomada futura.

## Ja tratado

- Controle efetivo de modulos em menus, busca global e endpoints tenant-scoped.
- Workflow contratual com motivo obrigatorio, historico administrativo e bloqueio de contratos suspensos/cancelados.
- Area base do Administrador Geral com overview, gabinetes, configuracoes globais, suporte e auditoria.
- Login do perfil `platform_admin` sem vinculo com gabinete.

## Pendencias

### Gestao completa de usuarios por gabinete

- Criar, editar, bloquear e reativar usuarios de gabinete pela plataforma.
- Transferir ou redefinir Administrador do Gabinete com fluxo guiado.
- Consultar administradores e perfis operacionais por gabinete.
- Auditar alteracoes de perfil, status e credenciais.

### Armazenamento real

- Calcular uso real em MB por anexos, documentos RAG, OCR e arquivos gerados.
- Comparar consumo com `storage_limit_mb`.
- Exibir alertas por faixa de uso.
- Bloquear ou limitar upload quando ultrapassar politica definida.

### Modelos globais aplicados aos gabinetes

- Publicar modelos globais versionados.
- Permitir adocao, copia ou override por gabinete.
- Diferenciar modelos globais de modelos tenant-scoped.
- Auditar publicacao e alteracoes de versao.

### Integracoes gerais reais

- Centralizar provedores globais de IA, LLM, OCR, Maps, e-mail, WhatsApp/Meta e mensageria.
- Validar credenciais e testar conexao por provedor.
- Definir fallback por provedor.
- Separar configuracao global de configuracao especifica de gabinete.

### Monitoramento real

- Painel de disponibilidade por servico.
- Status de filas, workers, webhooks, IA, OCR e RAG.
- Alertas de falha por periodo, severidade e tenant afetado.
- Indicadores de SLO e health checks historicos.

### Logs tecnicos

- Tela/API para consulta de logs estruturados.
- Filtros por servico, severidade, periodo, tenant e correlation id.
- Politica de retencao de logs tecnicos.
- Vinculo entre logs, auditoria e suporte.

### Suporte com acesso excepcional

- Implementar modo suporte controlado ou impersonation read-only.
- Exigir registro de suporte valido antes de qualquer acesso interno.
- Definir expiracao, escopo, trilha detalhada e encerramento do acesso.
- Impedir uso fora do escopo autorizado.

### Auditoria administrativa avancada

- Filtros por acao, usuario, periodo, entidade e tenant.
- Visualizacao amigavel de diff.
- Exportacao da trilha administrativa.
- Politica de retencao especifica para auditoria de plataforma.

### Administracao de versoes e funcionalidades

- Cadastro de releases e funcionalidades.
- Feature flags por plano e por gabinete.
- Rollout gradual.
- Kill switch para funcionalidades criticas.

### Indicadores consolidados avancados

- Evolucao historica por gabinete/plano/modulo.
- Uso de IA por provedor/modelo.
- Uso de canais e webhooks.
- Acompanhamento de SLA tecnico.
- Indicadores de receita/contrato, quando houver modulo financeiro.

### Politicas gerais de seguranca e retencao

- Aplicar configuracoes globais de senha, MFA, sessao e expiracao.
- Aplicar politicas globais de retencao, anonimização e exportacao.
- Permitir override controlado por gabinete quando autorizado.
- Auditar alteracoes e aplicacao das politicas.

## Criterio para retomada

Quando solicitado, escolher uma pendencia deste documento, criar testes focados, implementar com isolamento multi-tenant e atualizar este arquivo marcando o item como tratado.
