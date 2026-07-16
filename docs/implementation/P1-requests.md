# P1 - Solicitações e Atendimento

## Gestão principal de solicitações

Esta entrega mantém contrato, regras de negócio, persistência, interface e testes
evoluindo juntos em fatias verticais.

| Spec | Implementação |
| --- | --- |
| RF-020 | Cadastro pelas sete origens previstas no contrato |
| RF-021 / RN-001 | Protocolo sequencial e único por tenant |
| RF-023 | Status e prioridade operacionais |
| RF-025 | Endereço, latitude e longitude |
| RF-027 | Histórico imutável por solicitação e auditoria global |
| RF-031 / RN-005 / RN-006 | Encerramento exige motivo; resolução exige evidência ou justificativa |
| RF-040 / RF-046 | Interações de entrada, saída ou internas preservadas na solicitação |
| ADR-002 | Eventos `SolicitacaoCriada` e `SolicitacaoAtualizada` em outbox transacional |
| ADR-005 / RNF-007 | Consultas e gravações filtradas pelo tenant autenticado |

## Fatias operacionais complementares

| Spec | Implementação |
| --- | --- |
| RF-010 a RF-015 | Diretório de cidadãos e organizações, múltiplos contatos e endereços, nome social, canal preferencial, base legal, consentimentos separados, histórico e anonimização |
| RF-022 / RF-024 | Categoria, subcategoria, tema, território, órgão, impacto, urgência, responsável e SLA |
| RF-026 / RN-007 | Responsável por solicitação, histórico da troca e notificação ao novo responsável |
| RF-028 / RN-009 | Agrupamento de duplicidades sem exclusão das solicitações ou dos históricos |
| RF-029 | Tarefas com responsável, prioridade, prazo e estado de conclusão |
| RF-030 | Encaminhamento a órgão externo, protocolo e resposta preservada como interação |
| RF-032 | Reabertura com motivo, histórico e auditoria |
| RF-033 | Consulta pública mínima por protocolo e chave segura armazenada somente como hash |
| RF-043 | Central interna, leitura e preferências por usuário para atribuição, tarefa, SLA e sistema |
| RF-044 / RF-045 | Tentativas de contato com canal, destino, resultado, responsável, próxima tentativa e justificativa obrigatória ao divergir do canal preferencial |
| RF-080 / RF-087 | Painel por status, categoria e território, com atrasos, demandas próximas do prazo e fila prioritária |
| Segurança de anexos | Namespace por tenant, limite de tamanho, allowlist de MIME, SHA-256, bloqueio da assinatura EICAR e URL temporária assinada |

## Interface entregue

- lista, cadastro, detalhes, status e interações de solicitações;
- diretório alternável entre cidadãos e organizações;
- parametrização de categorias e SLA para administradores e gestores;
- vínculo de cidadão, organização, categoria e responsável;
- situação e prazo de SLA no acompanhamento;
- criação e conclusão de tarefas;
- upload e download protegido de anexos;
- agrupamento explícito de solicitações duplicadas;
- central de notificações no cabeçalho.
- preferências configuráveis de alertas internos;
- registro estruturado das tentativas de contato e retornos agendados;
- painel operacional com indicadores e fila prioritária;
- parametrização de territórios e órgãos externos;
- encaminhamento, resposta externa, reabertura e chave de acompanhamento público.

## Limites desta entrega

- a verificação de anexos usa controles locais e a assinatura EICAR; a implantação
  produtiva deve conectar o fluxo a um scanner dedicado, como ClamAV ou equivalente;
- notificações externas por e-mail ou mensageria permanecem desacopladas;
- templates de resposta, agendamento de retorno e notificações externas ficam para
  incrementos posteriores de comunicação.
