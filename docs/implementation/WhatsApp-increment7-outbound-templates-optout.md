# WhatsApp Business Platform - Incremento 7

## Objetivo

Governar toda saída do WhatsApp com política determinística, templates transacionais aprovados,
idempotência, rastreabilidade de entrega e opt-out imediato.

## Política de saída

- dentro da janela de 24 horas, um operador pode enviar texto livre ou template aprovado;
- fora da janela, somente template `APPROVED` da mesma integração e tenant;
- templates `MARKETING` permanecem bloqueados por padrão;
- contato em opt-out não recebe novas saídas, exceto a confirmação única do próprio opt-out;
- a política é reavaliada no momento do dispatch para bloquear corridas entre fila e opt-out;
- destinatário e número remetente vêm do domínio servidor-side, nunca do frontend.

## Templates oficiais

`whatsapp_message_templates` mantém nome, idioma, categoria, versão, corpo, parâmetros, status da
Meta e motivo de rejeição. Uma nova versão nasce `PENDING`; somente a sincronização pelo adaptador
de runtime pode torná-la `APPROVED`. Edição não altera uma versão já usada.

## Entrega e status

`whatsapp_messages` passa a armazenar conteúdo de saída, template, parâmetros, chave de
idempotência, decisão da política, ator e timestamps de envio, entrega, leitura e falha. O comando
`SendWhatsappMessageRequested` é transacional. Reentrega com a mesma chave retorna a mesma
mensagem. Webhooks da Meta avançam o status monotonicamente.

## Opt-out

`PARAR`, `SAIR`, `CANCELAR`, `STOP` e `DESCADASTRAR` continuam determinísticos. Na mesma transação,
o contato e a conversa ficam terminais e uma confirmação transacional única é enfileirada. Toda
mensagem comum já enfileirada volta a validar o opt-out antes de acessar o adaptador.

## Segurança operacional

O adaptador real deve receber a credencial da Cloud API somente em runtime pelo mecanismo aprovado
com AWS Secrets Manager. Payloads e logs não carregam token, telefone em claro ou conteúdo da
mensagem. Sem o gate de runtime, eventos entram em retry controlado e preservam auditoria.

## Interface

A Caixa de Entrada mostra a regra vigente, bloqueia o compositor em opt-out, exige template quando
a janela encerra e coleta os parâmetros nomeados. A Administração cria versões transacionais,
acompanha aprovação/rejeição e solicita atualização de status diretamente à integração.

## Critérios de saída

- texto livre bloqueado fora da janela;
- somente template transacional aprovado pode iniciar contato;
- template e contato de outro tenant são inacessíveis;
- idempotência impede envio duplicado;
- opt-out bloqueia novas mensagens e gera uma confirmação única;
- status `SENT`, `DELIVERED`, `READ` e `FAILED` são rastreáveis;
- API, interface, migração, OpenAPI, AsyncAPI, BDD e testes estão alinhados.
