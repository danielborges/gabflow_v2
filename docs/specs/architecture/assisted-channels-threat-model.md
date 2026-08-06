# Threat model — canais assistidos por WhatsApp e e-mail

## Escopo e objetivo

O incremento 9.5 recebe mensagens externas, sugere possíveis cidadãos e exige decisão
humana. O objetivo é impedir que conteúdo não confiável crie, mescle ou vincule cidadãos,
atravesse tenants, contamine auditoria ou induza ações automáticas.

## Fronteiras de confiança

```text
[Meta/Resend/remetente não confiável]
          |
          v
[assinatura + tenant + idempotência + limites]
          |
          v
[ChannelMessage: envelope canônico não confiável]
          |
          v
[normalização determinística de contato]
          |
          v
[sugestão tenant-scoped] -- sem escrita em Citizen --> [fila humana]
                                                        |
                                      vincular existente | descartar
                                                        v
                                               [auditoria mínima]
```

## Ativos protegidos

- identidade e cadastro do cidadão;
- separação entre gabinetes;
- contatos, conteúdo e metadados de mensagens;
- solicitações vinculadas ao cidadão correto;
- credenciais e segredos dos provedores;
- integridade e minimização dos logs de auditoria.

## Ameaças e controles

| ID | Ameaça | Controle implementado |
|---|---|---|
| CH-001 | Webhook forjado | HMAC/Svix, tolerância temporal e integração ativa |
| CH-002 | Replay ou entrega duplicada | unicidade por tenant, canal e ID externo |
| CH-003 | Associação por nome falso/homônimo | nome e conteúdo não participam da decisão |
| CH-004 | Telefone/e-mail falsificado | resultado é sugestão; vínculo exige usuário autenticado |
| CH-005 | Vazamento entre tenants | consultas tenant-scoped, FKs compostas e RLS forçado |
| CH-006 | Mass assignment/criação automática | preparação separada da persistência, confirmações explícitas e criação transacional pelo endpoint normal de cidadãos |
| CH-007 | Conteúdo malicioso em logs | auditoria registra IDs e decisão, nunca mensagem ou contato |
| CH-008 | Exposição de payload do provedor | allowlist de metadados; `raw`, destinatários e BCC não são serializados |
| CH-009 | Corrida de revisores | estado só transita a partir de `PENDENTE`; segunda decisão é rejeitada |
| CH-010 | Vínculo a cidadão de outro gabinete | seleção exige cidadão ativo no mesmo tenant |
| CH-011 | Prompt injection em mensagem | conteúdo é exibido como dado não confiável e não aciona IA/ferramentas |
| CH-012 | Enumeração de contato | fila autenticada e contato mascarado na resposta de revisão |
| CH-013 | Abuso de volume | rate limit dos webhooks e limite de 100 itens por consulta |
| CH-014 | Anexo malicioso | somente metadados limitados são exibidos; anexo não é processado neste fluxo |

## Invariantes

1. Receber mensagem nunca cria nem altera `Citizen`.
2. Correspondência única nunca equivale a vínculo aprovado.
3. Revisão pendente nunca preenche `ServiceRequest.citizen_id`.
4. O resolvedor não consulta outro tenant.
5. Logs não contêm mensagem, contato, endereço, CPF ou payload bruto.
6. Toda decisão final possui usuário e instante.
7. Replay não cria nova mensagem nem nova revisão.
8. Conteúdo externo permanece não confiável depois da revisão de identidade.
9. Preparar um formulário nunca persiste um cidadão.
10. A conclusão assistida exige base legal configurada e confirmações de nome, contato e base legal.
11. A proveniência usa IDs opacos; conteúdo e contato não entram no histórico ou log técnico.
12. Retenção nunca minimiza envelope com revisão pendente.

## Riscos residuais e próximos controles

- posse do telefone/e-mail não prova identidade civil;
- contatos compartilhados podem gerar ambiguidade;
- filas extensas ainda exigirão paginação por cursor e alertas externos; SLA, atribuição e
  contadores operacionais já são aplicados;
- anexos exigirão o gateway antimalware antes de qualquer leitura;
- posse do contato continua exigindo conferência do operador mesmo no cadastro pré-preenchido.

## Critérios de aceite

- zero criação ou mesclagem automática de cidadão;
- zero vínculo cross-tenant nos testes negativos;
- replay idempotente para IDs externos;
- decisão duplicada rejeitada;
- contato mascarado e payload bruto ausente da API;
- trilha de auditoria sem conteúdo livre da mensagem.
- cadastro assistido bloqueado sem base legal ou confirmação dos campos mínimos;
- vínculo atômico da revisão somente após criação válida do cidadão;
- retenção restrita a envelopes concluídos além do prazo configurado.
