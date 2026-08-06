# ADR-010 — Identidade assistida em mensagens de WhatsApp e e-mail

## Status

Aceito para o incremento 9.5.

## Contexto

WhatsApp e e-mail são origens externas, não autenticadas como identidade civil. Nome,
telefone, endereço de e-mail, conteúdo e metadados podem ser falsificados, reutilizados ou
encaminhados. Criar ou mesclar cidadãos diretamente a partir de uma mensagem produziria
risco de duplicidade, associação indevida, fraude e tratamento de dados sem revisão.

O GabFlow já recebe WhatsApp Business pela Meta Cloud API e e-mail inbound pelo Resend.
Esses adaptadores validam assinatura, origem configurada e identificador externo.

## Decisão

1. `ChannelMessage` é o envelope canônico de entrada. O identificador do provedor é
   idempotente por tenant e canal.
2. Somente WhatsApp e e-mail geram `ChannelIdentityReview`. Redes sociais e formulários
   permanecem fora deste resolvedor.
3. O resolvedor é determinístico e tenant-scoped. Nesta etapa ele compara apenas telefone
   ou e-mail normalizados; nome e conteúdo livre nunca decidem identidade.
4. Uma correspondência única é somente uma sugestão pré-selecionada. Zero ou múltiplas
   correspondências permanecem pendentes.
5. Apenas usuários `admin`, `manager` ou `staff` podem vincular um cidadão existente ou
   descartar a sugestão. Não existe endpoint de criação ou mesclagem automática.
6. A mensagem bruta não é copiada para a revisão nem para logs de auditoria. A revisão
   guarda estado, IDs opacos, critério de correspondência, revisor e instante.
7. Ao converter uma mensagem em solicitação, um vínculo humano já aprovado pode preencher
   `citizen_id`; uma sugestão pendente nunca o faz.
8. O piloto é habilitado pelo módulo `canais` do tenant. Ativação de novos provedores exige
   configuração explícita da integração e segredo fora do banco de configuração pública.

## Provedores e responsabilidades

- Meta WhatsApp Cloud API: autenticação HMAC e verificação do `phoneNumberId` configurado.
- Resend inbound: autenticação Svix, tolerância temporal e recuperação autenticada do e-mail.
- GabFlow: controlador do fluxo cadastral e responsável pela decisão humana, retenção,
  autorização, auditoria, idempotência e isolamento de tenant.
- Provedor: operador/suboperador conforme contrato e instruções documentadas do gabinete.

## Operação

- replay com o mesmo ID retorna a mensagem existente;
- falha de assinatura ou integração inativa falha fechada;
- indisponibilidade do resolvedor não cria cidadão e mantém a mensagem revisável;
- mensagens podem virar solicitações sem identidade, preservando o atendimento;
- métricas operacionais não devem conter contato nem conteúdo;
- retenção e atendimento de direitos seguem a política LGPD do tenant.

## Consequências

- reduz associação indevida e mantém rastreabilidade;
- exige capacidade operacional para tratar a fila;
- correspondências ficam limitadas a contatos já cadastrados e podem exigir pesquisa manual;
- criação assistida de um novo cidadão e mesclagem são decisões futuras, com novo ADR.
