# Runbook - piloto WhatsApp

## Princípios

- Não copie payload, telefone, token ou mensagem para tickets, logs ou métricas.
- Preserve idempotência: reprocessar pelo identificador interno, nunca reenviar manualmente o conteúdo.
- Em dúvida sobre impacto, pause as saídas do tenant e mantenha o recebimento ativo.
- Registre decisão, horário, operador, hipótese e critério de retomada.

## Triagem inicial

1. Consulte o cockpit do tenant e o dashboard `gabflow-<ambiente>-whatsapp-operations`.
2. Confirme o semáforo, idade da fila, DLQ, ACK p95 e falhas de entrega.
3. Correlacione por `requestId`, `correlationId` ou identificador interno, sem pesquisar conteúdo pessoal.
4. Classifique o incidente e execute o procedimento correspondente.

## Meta indisponível ou integração suspensa

Pause as saídas, preserve a outbox e confirme o estado da integração. Não repita envios. Após a recuperação, valide token e webhook com operação sem dados reais, acompanhe a fila e retome somente quando a idade estabilizar abaixo do SLO.

## Token revogado

Mantenha a integração degradada, pause as saídas e solicite reconexão por Embedded Signup. Nunca troque token por formulário, ticket ou variável local. Retome depois de health check positivo e validação do cofre.

## IA indisponível

Mantenha coleta estruturada, atendimento humano e criação de protocolo. Não bloqueie mensagem nem protocolo por falha de IA. Reprocesse somente a análise assistiva quando o provedor estabilizar.

## DLQ ou fila envelhecida

1. Pause saídas se houver risco de duplicidade ou comunicação fora de contexto.
2. Identifique o código de erro e corrija a causa.
3. Valide o consumidor com evento sintético.
4. Redirecione as mensagens da DLQ para a fila de origem usando o mecanismo aprovado da AWS.
5. Acompanhe idade, falhas e duplicidades até normalização.

## Assinatura inválida em volume

Trate como possível abuso. Preserve os logs estruturados, verifique origem e configuração da Meta, aplique contenção no perímetro e não reduza a validação criptográfica. Escale para segurança se o volume persistir.

## Número desconhecido

Mantenha o evento em quarentena. Confirme o `phone_number_id` nos ativos da Meta e no cadastro da integração. Nunca associe o evento por nome, telefone textual ou sem confirmação do tenant.

## Suspeita de cruzamento entre tenants

Pause imediatamente as saídas dos tenants potencialmente afetados, preserve evidências e acione segurança e privacidade. Não reclassifique nem mova registros. A retomada exige investigação concluída, teste negativo repetido e aprovação registrada no gate multi-tenant.

## Rollback e encerramento

Pausar é reversível e não interrompe inbound. Para desconexão, use o fluxo administrativo idempotente, preserve a trilha de auditoria e valide retenção. A retomada exige gates externos, internos e operacionais aprovados novamente.
