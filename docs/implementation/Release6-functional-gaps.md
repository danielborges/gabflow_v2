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
| Release 6 - Redes sociais | Caixa de entrada tenant-safe para mensagens de redes sociais e conversao humana em solicitacao |
| RF-070 | Cadastro de acao de fiscalizacao |
| RF-071 | Registro de local, fotos, achados e responsaveis |
| RF-072 | Relatorio de fiscalizacao consultavel pela API e interface |
| RF-073 | Fiscalizacao vinculada a orgao externo e solicitacao |
| RF-074 | Providencias decorrentes preservadas como lista estruturada |
| RF-092 | Configuracao tenant-safe de integracoes por tipo, status e configuracao publica |

## Fluxos

1. O usuario cria um compromisso de agenda informando tipo, titulo, local, data e participantes.
2. A agenda exibe roteiros sugeridos pelos territorios ou locais com maior concentracao de demandas abertas.
3. A visita pode ser registrada como realizada, com ata, fotos e pendencias.
4. Uma solicitacao pode ser aberta a partir da visita, reaproveitando local, territorio, cidadao e organizacao vinculados.
5. O usuario registra uma fiscalizacao com achados, responsaveis, fotos e providencias.
6. A fiscalizacao pode ser atualizada ate conclusao e seu relatorio fica disponivel para consulta.
7. Gestores configuram integracoes como WhatsApp, e-mail, formulario publico, redes sociais, sistemas legislativos e protocolos externos.
8. Mensagens de WhatsApp, e-mail e redes sociais entram na caixa de canais por registro manual ou webhook; WhatsApp Cloud API e e-mails Resend entram por endpoints dedicados com validacao de assinatura.
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

## Limites desta entrega

- Integracoes ficam configuraveis e auditadas; envio de e-mail, inbound Resend e inbound WhatsApp Business Cloud API ja possuem conectores especificos quando credenciais e secrets estao configurados.
- Webhooks multicanal recebem payloads normalizados; redes sociais ainda aguardam validacao de assinatura especifica por provedor.
- Redes sociais estao operacionais como inbox governada; automacoes especificas de cada provedor ficam para incrementos de integracao.
- Fotos em agenda e fiscalizacao sao metadados estruturados; upload binario dedicado pode reutilizar o subsistema de anexos em uma proxima fatia.
