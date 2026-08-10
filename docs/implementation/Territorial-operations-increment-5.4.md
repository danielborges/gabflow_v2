# Operação territorial — incremento 5.4

## Objetivo

Converter um sinal da Inteligência Territorial em trabalho rastreável sem perder o território,
os filtros, a comparação histórica e as solicitações autorizadas que deram origem à decisão.

## Entrega implementada

- criação de `TAREFA`, `AGENDA`, `VISITA`, `ROTEIRO` e `ENCAMINHAMENTO` a partir do território
  selecionado;
- atribuição opcional a trabalhador ativo, prazo e descrição operacional;
- estados `PENDENTE`, `EM_ANDAMENTO`, `CONCLUIDA` e `CANCELADA`;
- resultado ou justificativa obrigatórios para concluir ou cancelar;
- até 20 evidências textuais e até 100 solicitações de referência;
- proveniência imutável do recorte em `source_context`, `filters`, `request_ids` e `source_key`;
- prevenção de ação aberta duplicada para o mesmo território, tipo, filtros e alerta de origem;
- criação e sincronização automática de compromisso de agenda para agenda, visita e roteiro;
- isolamento por tenant, RLS no PostgreSQL e auditoria de criação e atualização;
- painel operacional dentro da Inteligência Territorial para criar, iniciar e encerrar ações.

### Incremento 5.4.1 — histórico, prazos e permissões

- histórico server-side com busca, filtros por status, tipo e estado de prazo, paginação em
  10, 25, 50 ou 100 registros e ordenação validada;
- estados derivados `VENCIDA`, `PROXIMA`, `NO_PRAZO`, `SEM_PRAZO` e `ENCERRADA`;
- notificação imediata de atribuição e alertas idempotentes 24 horas antes e após o vencimento;
- Administrador, Gestor, Parlamentar e Chefe de Gabinete gerenciam o gabinete;
- trabalhadores consultam e movimentam somente ações atribuídas a eles, sem reatribuir, alterar
  prazo ou cancelar;
- reatribuição e alteração de prazo auditadas, com reinício seguro dos marcadores de notificação.

### Incremento 5.4.2 — evidências, métricas e alertas

- evidências estruturadas por tipo, título, descrição, data, autor e origem, aceitando URL ou arquivo;
- arquivos submetidos à política de MIME, limite, antivírus, criptografia AES-256-GCM e download
  temporário assinado já utilizados pelo GabFlow;
- evidências imutáveis e auditadas, sem apagar o histórico textual legado;
- métricas por território e escopo do usuário: funil, taxa de conclusão, prazo, cobertura de
  evidências, tempo médio de conclusão e alertas ativos;
- alertas persistentes `ATIVO`, `RECONHECIDO` e `RESOLVIDO`, com reconhecimento, justificativa de
  resolução e trilha de auditoria;
- resolução automática de alertas pendentes quando a ação é encerrada ou seu prazo é redefinido.

## Contratos

- `GET /api/v1/painel/territorial/acoes`
- `POST /api/v1/painel/territorial/acoes`
- `PATCH /api/v1/painel/territorial/acoes/{id}`
- `POST /api/v1/painel/territorial/acoes/{id}/evidencias`
- `GET /api/v1/painel/territorial/evidencias/{id}/download`
- `GET /api/v1/painel/territorial/metricas-execucao`
- `GET /api/v1/painel/territorial/alertas`
- `PATCH /api/v1/painel/territorial/alertas/{id}`

O contrato completo está em `docs/specs/api/openapi.yaml`. A migração reversível é
`d9f1a3c5e7b2_territorial_operations.py`, seguida de
`e1a4c6d8f0b2_territorial_deadline_notifications.py` e
`f2b5d7e9a1c3_territorial_evidence_metrics_alerts.py`.

## Regras de segurança e produto

- território, responsável e solicitações são revalidados no tenant autenticado;
- o agrupamento “Sem território” não permite criar ação;
- nenhuma ação é disparada automaticamente por uma correlação analítica;
- agenda, visita e roteiro exigem data e hora;
- encerrar uma ação nunca apaga sua origem nem seu histórico de auditoria;
- a API retorna páginas de no máximo 100 ações.

## Rollout e rollback

1. aplicar a migração e liberar inicialmente no Gabinete Demonstração;
2. validar criação, atribuição, agenda, início, conclusão e cancelamento com revisão humana;
3. observar duplicidades, tempo até atribuição e percentual de ações encerradas com evidência;
4. para rollback, retirar a interface e o registro do blueprint; a tabela pode permanecer sem
   afetar o painel anterior e ser removida pela reversão Alembic somente após exportar registros.

## Encerramento do Gate D

O Gate D foi **aprovado e formalmente encerrado em 10/08/2026**. O teste autenticado executou
1.000 requisições com 50 usuários virtuais sobre uma massa de 307 cidadãos, 51 organizações e 765
solicitações: não houve erros, o P95 geral foi 452,1 ms e o P95 do painel foi 561,3 ms. A
homologação negocial por perfis `admin` e `staff` aprovou 13 de 13 cenários de atribuição, prazo,
permissões, transições, evidência, resultado, métricas, alertas e auditoria.

A decisão, os critérios e os artefatos reproduzíveis estão em
[`Territorial-intelligence-gate-d-closure.md`](Territorial-intelligence-gate-d-closure.md).
