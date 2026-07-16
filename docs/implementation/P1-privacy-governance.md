# P1 - LGPD e Governança

## Escopo entregue

| Spec | Implementação |
| --- | --- |
| RF-014 / RN-018 | Registro append-only de consentimento por finalidade, decisão, base legal, origem e evidência |
| RF-015 | Solicitações de anonimização e anonimização manual já existente, restrita a administradores e gestores |
| RF-094 / RNF-014 | Políticas de retenção por tipo de dado, prazo e ação sujeita a revisão humana |
| RF-004 / RNF-008 | Consulta de auditoria isolada por tenant, com usuário, ação, entidade, IP e diff |
| Cenário LGPD - acesso | Solicitação do titular, validação de identidade e exportação JSON auditada |
| Cenário LGPD - correção | Alterações do cidadão preservadas como `citizen.corrected`, com antes e depois |
| RN-020 | Auditoria permanece fora dos fluxos de anonimização e não é removida |

## Controles de segurança

- acesso à central restrito aos perfis `admin` e `manager`;
- todas as consultas filtradas pelo tenant autenticado;
- exportação somente para solicitações de acesso com identidade validada;
- exportação realizada por `POST` protegido por CSRF;
- consentimento de contato separado do consentimento de divulgação;
- políticas de retenção não executam exclusões automáticas;
- resolução obrigatória para conclusão ou rejeição de solicitações.

## Limites desta entrega

- validação de identidade é registrada pelo usuário autorizado; integração com
  identidade digital ou assinatura eletrônica fica para uma evolução;
- retenção gera governança e parametrização, mas a execução em lote dependerá de
  worker assíncrono e aprovação operacional;
- resposta a incidentes e inventário completo de operações de tratamento serão
  incrementos posteriores.
