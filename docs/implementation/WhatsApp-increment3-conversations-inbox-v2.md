# WhatsApp Business Platform - Incremento 3

## Objetivo

Transformar mensagens confiavelmente recebidas em contatos e conversas operacionais, oferecendo
uma Caixa de Entrada 2.0 para a equipe do gabinete assumir, organizar e acompanhar atendimentos
sem perder isolamento por tenant ou permitir concorrencia entre bot e assessor.

## Dominio

O incremento adiciona:

- `whatsapp_contact`: identidade do WhatsApp limitada ao tenant, perfil, vinculo opcional com
  cidadao e estado de opt-out;
- `whatsapp_conversation`: estado, modo `BOT/HUMAN`, responsavel, janela de 24 horas, nao lidas e
  controle de versao;
- `whatsapp_message`: envelope cronologico associado ao `ChannelMessage`, sem copiar conteudo;
- `whatsapp_conversation_transition`: trilha de estado com ator, origem, regra e correlacao.

As FKs compostas impedem contato, conversa, mensagem, responsavel ou cidadao de outro tenant.

## Fluxo de entrada

O worker do Incremento 2, depois de revalidar a rota, cria ou atualiza o contato e uma conversa
por `tenant_id + wa_user_id`. A mensagem recebida:

1. entra no historico uma unica vez;
2. incrementa nao lidas;
3. atualiza a janela de 24 horas apenas de forma monotona;
4. move `NEW` para `PRIVACY_NOTICE`;
5. registra transicao e evento no outbox.

Status da Meta atualizam a mensagem somente de forma monotona. `READ` nao regride para
`DELIVERED` ou `SENT`.

## Estados e comandos deterministas

Fluxo principal:

```text
NEW -> PRIVACY_NOTICE -> IDENTIFICATION -> INTENT -> DATA_COLLECTION
    -> REVIEW -> PROTOCOL_CREATED -> FOLLOW_UP
```

Estados laterais: `HUMAN_HANDOFF`, `OPTED_OUT`, `BLOCKED`, `ERROR_RECOVERY` e `CLOSED`.

No primeiro corte, os comandos `PARAR`, `SAIR`, `CANCELAR`, `STOP` e `DESCADASTRAR` executam
opt-out deterministico. Pedidos como `ATENDENTE`, `ASSESSOR` ou `FALAR COM ASSESSOR` entram em
`HUMAN_HANDOFF`. Essas decisoes nao dependem de IA.

## Handoff

Um assessor pode assumir a conversa pela caixa. A operacao:

- valida o responsavel no mesmo tenant;
- exclui o papel parlamentar da lista de atendentes;
- muda o modo para `HUMAN` e estado para `HUMAN_HANDOFF`;
- registra ator, motivo e auditoria de transicao;
- funciona como trava para qualquer automacao futura.

A retomada do bot exige acao explicita de administrador ou gestor e restaura o estado anterior ao
handoff quando ele for valido. Estados terminais nao permitem handoff ou retomada.

## API

```text
GET  /api/v1/tenants/{tenantId}/conversations
GET  /api/v1/tenants/{tenantId}/conversations/{conversationId}
POST /api/v1/tenants/{tenantId}/conversations/{conversationId}/read
PUT  /api/v1/tenants/{tenantId}/conversations/{conversationId}/assignment
POST /api/v1/tenants/{tenantId}/conversations/{conversationId}/handoff
POST /api/v1/tenants/{tenantId}/conversations/{conversationId}/resume-bot
```

Listagem suporta busca, modo, estado, responsavel e somente nao lidas. Tentativas cross-tenant
retornam `404`. O contato e mascarado na listagem; detalhes integrais permanecem restritos a
usuarios autorizados do gabinete.

## Caixa de Entrada 2.0

A feature Canais passa a abrir com um workspace de duas colunas:

- busca e filtros de modo/nao lidas;
- resumo de conversas, nao lidas e atendimentos humanos;
- lista ordenada pela ultima mensagem;
- historico em bubbles, estado, janela e responsavel;
- acao de assumir atendimento;
- aviso visual de automacao pausada;
- retomada explicita por gestor.

A fila de revisao de identidade e o registro manual existentes permanecem abaixo do novo
workspace para preservar os fluxos assistidos ja entregues.

## Criterios de saida

- primeira mensagem cria contato, conversa e mensagem idempotentes;
- contato se repete somente dentro do mesmo tenant;
- conversa inicia em aviso de privacidade;
- janela e nao lidas sao atualizadas;
- handoff bloqueia automacao concorrente;
- retomada exige papel e acao explicita;
- opt-out e deterministico e terminal;
- vinculo humano da revisao associa o contato ao cidadao;
- outro tenant recebe `404` ao tentar acessar a conversa;
- API, OpenAPI, AsyncAPI, UI e testes estao alinhados.

## Proximo gate

O Incremento 4 pode implementar aviso de privacidade e identificacao guiada, incluindo evidencia
de base legal/consentimento e a primeira resposta transacional pela Cloud API.
