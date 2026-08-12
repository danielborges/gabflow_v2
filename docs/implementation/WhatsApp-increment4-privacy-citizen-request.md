# WhatsApp Business Platform - Incremento 4

## Objetivo

Concluir a primeira jornada institucional do WhatsApp com transparência, identificação mínima e
criação confirmada de solicitação, sem duplicar o diretório de cidadãos ou a operação de demandas
já existente no GabFlow.

## Privacidade antes da coleta

A primeira mensagem cria uma ordem transacional `WhatsappPrivacyNoticeRequested` no outbox. O
payload contém a versão do aviso, finalidade, base legal e o texto institucional, mas não contém o
número do cidadão nem a mensagem recebida. A evidência persistida em
`whatsapp_privacy_records` é somente um SHA-256 do envelope canônico.

O reconhecimento do aviso é uma ação explícita da caixa de entrada. Consentimento é registrado
somente quando a base aplicável realmente o exige; execução de política pública não é apresentada
como consentimento fictício. A conversa só avança de `PRIVACY_NOTICE` para `IDENTIFICATION`
depois desse registro.

## Cidadão

A busca por WhatsApp:

- normaliza o contato e consulta apenas cidadãos não anonimizados do mesmo tenant;
- retorna sugestões para decisão humana, sem vínculo automático;
- permite cadastro mínimo com nome e WhatsApp confirmados;
- não solicita nem exige CPF;
- projeta a evidência conversacional no histórico de consentimentos do cidadão;
- usa FK composta para impedir vínculo com cidadão de outro gabinete.

## Solicitação e protocolo

`whatsapp_request_drafts` guarda a coleta estruturada antes do protocolo. A confirmação exige:

1. aviso de privacidade reconhecido;
2. cidadão confirmado;
3. descrição mínima revisada;
4. checkbox explícito na interface;
5. `Idempotency-Key` de 8 a 120 caracteres.

A mesma chave retorna a solicitação existente e não cria uma segunda demanda. Uma chave diferente
depois da confirmação é rejeitada. A solicitação usa o domínio principal de `service_requests`,
entra como `WHATSAPP/NOVA` e conserva triagem humana.

O protocolo sequencial existente permanece interno para compatibilidade operacional. O novo
`public_protocol`, obrigatório e único por tenant, usa entropia aleatória e é a referência exibida
ao cidadão. A chave pública de acompanhamento continua armazenada somente como hash.

## API

```text
POST /api/v1/tenants/{tenantId}/conversations/{conversationId}/privacy
POST /api/v1/tenants/{tenantId}/conversations/{conversationId}/citizen
PUT  /api/v1/tenants/{tenantId}/conversations/{conversationId}/request-draft
POST /api/v1/tenants/{tenantId}/conversations/{conversationId}/request-draft/confirm
```

O detalhe da conversa inclui `jornada`, sugestões tenant-safe, rascunho, categorias ativas e o
protocolo criado. Tentativas cross-tenant continuam respondendo como recurso inexistente ou dado
inválido sem revelar metadados.

## Caixa de entrada

A conversa ganhou um trilho visual em quatro etapas: Privacidade, Cidadão, Solicitação e
Protocolo. Cada painel expõe apenas a próxima ação válida, explica as salvaguardas e mantém o
histórico da conversa visível. O formulário oferece categoria opcional para permitir protocolo
mesmo quando a triagem ainda não estiver concluída.

## Critérios de saída

- aviso solicitado uma única vez por conversa e versão;
- evidência minimizada e base legal registradas antes da identificação;
- CPF ausente no cadastro mínimo;
- vínculo e cadastro exigem confirmação humana;
- FKs e consultas impedem referências cruzadas entre tenants;
- confirmação repetida não duplica solicitação;
- protocolo público é aleatório, único e não enumerável;
- opt-out e estados terminais bloqueiam a jornada;
- OpenAPI, AsyncAPI, BDD, migração, UI e testes ficam alinhados.

## Próximo gate

O dispatcher da Cloud API deve consumir `WhatsappPrivacyNoticeRequested` e
`WhatsappProtocolCreated`, resolver a credencial exclusivamente em runtime pelo mecanismo de
segredos aprovado e registrar `provider_message_id` e os status de entrega. Até esse dispatcher
ser promovido, a caixa exige confirmação humana de que o aviso foi apresentado e não afirma envio
automático concluído.
