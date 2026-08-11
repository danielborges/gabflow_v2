# Release 6 - Lacunas funcionais de operacao

## Escopo entregue

| Spec | Implementacao |
| --- | --- |
| RF-050 | Cadastro de compromissos, visitas, reunioes e audiencias na agenda do tenant |
| RF-051 | Agenda vinculada a cidadao, organizacao, territorio e solicitacao quando informado |
| RF-052 | Roteiros de visita sugeridos por concentracao de demandas abertas, prioridade e territorio/local |
| RF-053 | Registro de ata, fotos, participantes e pendencias de visitas e compromissos |
| RF-054 | Criacao de solicitacao a partir de visita realizada, com origem `VISITA` |
| Release 6 - WhatsApp | Caixa de entrada tenant-safe para mensagens WhatsApp, inbound real via WhatsApp Business Cloud API com handshake Meta, assinatura `X-Hub-Signature-256` e conversao humana em solicitacao |
| Release 6 - E-mail | Caixa de entrada tenant-safe para mensagens de e-mail, inbound real via webhook Resend assinado com Svix e resposta por e-mail ja integrada ao outbox/Resend quando configurado |
| Release 6 - Formulario publico | Formulario publico por slug do tenant, controlado por integracao ativa e com criacao direta de solicitacao |
| Release 6 - Redes sociais | Caixa de entrada tenant-safe para Facebook/Instagram via Meta Webhooks, com handshake, assinatura `X-Hub-Signature-256`, deduplicacao e conversao humana em solicitacao |
| RF-070 | Cadastro de acao de fiscalizacao |
| RF-071 | Registro de local, fotos, achados e responsaveis |
| RF-072 | Relatorio de fiscalizacao consultavel pela API e interface |
| RF-073 | Fiscalizacao vinculada a orgao externo e solicitacao |
| RF-074 | Providencias decorrentes preservadas como lista estruturada |
| RF-092 | Configuracao tenant-safe de integracoes por tipo, status e configuracao publica |

## Evolucoes posteriores de Agenda e Fiscalizacao

### Agenda institucional

- visualizacao nos modos dia, semana e mes, com navegacao inspirada em agendas de mercado;
- criacao e edicao de compromissos com tipo, titulo, descricao, local, datas, horarios,
  presenca parlamentar e participantes;
- participantes selecionados por busca multipla entre usuarios ativos do gabinete, sem o
  Parlamentar; o seletor fecha ao selecionar ou clicar fora;
- compromissos com presenca parlamentar recebem cor distinta;
- ao alterar o inicio, o termino e sugerido para uma hora depois;
- o botao principal segue o padrao visual azul e usa o rotulo `+ Compromisso`;
- PDF executivo da semana de referencia, com capa institucional, indicadores, ritmo,
  alertas e compromissos agrupados por dia.

Endpoint do PDF semanal:

```text
GET /api/v1/agenda/relatorio-semanal.pdf?data=YYYY-MM-DD
```

### Fiscalizacao orientada pela agenda

- compromissos do tipo `FISCALIZACAO` vencidos alimentam a lista de relatorios pendentes;
- somente os participantes do compromisso visualizam a pendencia e recebem lembrete na
  aplicacao;
- a pendencia permanece ate a fiscalizacao vinculada ser concluida com relatorio, quando
  o evento e marcado como realizado e as notificacoes sao resolvidas;
- a tela tambem permite registrar fiscalizacao direta, inclusive durante a atividade, sem
  agenda previa;
- a fiscalizacao pode ser salva como rascunho, concluida e vinculada a uma solicitacao;
- fotos podem ser capturadas pelo dispositivo e fotos ou documentos podem ser enviados
  como evidencias com observacao editavel e download autorizado;
- evidencias usam armazenamento privado, isolamento por tenant, verificacao antimalware,
  integridade e protecao criptografica.

Endpoints principais:

```text
GET   /api/v1/fiscalizacoes/pendentes-relatorio
POST  /api/v1/fiscalizacoes
PATCH /api/v1/fiscalizacoes/{id}
POST  /api/v1/fiscalizacoes/{id}/evidencias
PATCH /api/v1/fiscalizacoes/evidencias/{id}
GET   /api/v1/fiscalizacoes/evidencias/{id}/download
```

O modelo foi ampliado com o vinculo opcional e unico
`OversightAction.agenda_event_id` e com a entidade `OversightEvidence`. A migracao
de agenda e `f4c8e2a6d0b1_agenda_google_calendar.py`; a migracao de fiscalizacao e
`a5d9f1b3c7e2_oversight_agenda_evidence.py`.

## Fluxos

1. O usuario cria um compromisso de agenda informando tipo, titulo, local, data e participantes.
2. A agenda exibe roteiros sugeridos pelos territorios ou locais com maior concentracao de demandas abertas.
3. A visita pode ser registrada como realizada, com ata, fotos e pendencias.
4. Uma solicitacao pode ser aberta a partir da visita, reaproveitando local, territorio, cidadao e organizacao vinculados.
5. O usuario registra uma fiscalizacao com achados, responsaveis, fotos e providencias.
6. A fiscalizacao pode ser atualizada ate conclusao e seu relatorio fica disponivel para consulta.
7. Gestores configuram integracoes como WhatsApp, e-mail, formulario publico, redes sociais, sistemas legislativos e protocolos externos.
8. Mensagens de WhatsApp, e-mail e redes sociais entram na caixa de canais por registro manual ou webhook; WhatsApp Cloud API, e-mails Resend e Facebook/Instagram via Meta entram por endpoints dedicados com validacao de assinatura.
9. O usuario revisa cada mensagem recebida e decide se ela deve virar solicitacao.
10. O formulario publico cria solicitacoes diretamente quando a integracao `FORMULARIO_PUBLICO` esta ativa.

## Governanca

- todas as consultas e gravacoes sao filtradas pelo tenant autenticado;
- criacao e atualizacao de agenda, fiscalizacao e integracoes geram auditoria;
- configuracoes de integracao removem campos sensiveis antes de persistir e responder;
- solicitacoes criadas a partir de visitas preservam a origem `VISITA` e publicam o evento de dominio existente;
- vinculos a cidadao, organizacao, territorio, orgao ou solicitacao sao revalidados dentro do tenant.

## Interfaces entregues

- nova entrada de menu para Agenda;
- nova entrada de menu para Fiscalizacao;
- tela de Agenda com criacao, listagem, roteiros sugeridos, registro de visita e criacao de solicitacao;
- tela de Fiscalizacao com criacao, listagem e visualizacao de relatorio;
- secao de Integracoes dentro de Administracao.
- nova entrada de menu para Canais;
- caixa de entrada multicanal com registro manual, listagem e conversao em solicitacao;
- formulario publico em `/publico/formularios/{tenant}`.

## Validacao das evolucoes

- `backend/tests/test_functional_gaps.py` cobre participantes elegiveis, presenca
  parlamentar, edicao, PDF semanal, criacao da pendencia, autorizacao por participante,
  evidencias e resolucao do lembrete;
- `frontend/src/components/AgendaPage.test.jsx` cobre abertura do compromisso para edicao
  e recalculo do termino uma hora apos o inicio;
- as migrations `f4c8e2a6d0b1` e `a5d9f1b3c7e2` devem estar aplicadas antes da
  implantacao desta versao.

## Limites desta entrega

- Integracoes ficam configuraveis e auditadas; envio de e-mail, inbound Resend, inbound WhatsApp Business Cloud API e inbound Facebook/Instagram via Meta ja possuem conectores especificos quando credenciais e secrets estao configurados.
- Webhooks multicanal recebem payloads normalizados; novos provedores podem ser adicionados por endpoint dedicado e assinatura propria.
- Redes sociais estao operacionais como inbox governada para Facebook/Instagram; automacoes especificas de resposta e moderacao ficam para incrementos de integracao.
- Fotos legadas da agenda continuam aceitas como metadados estruturados. Evidencias de
  fiscalizacao ja possuem upload binario dedicado e seguro; a consolidacao futura com o
  subsistema generico de anexos deve preservar o contrato e a trilha existentes.
