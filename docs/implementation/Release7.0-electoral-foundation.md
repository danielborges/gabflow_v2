# Release 7.0 — Fundação de Inteligência Eleitoral

## Escopo entregue

| Spec | Implementação |
| --- | --- |
| RF-001 / RN-001 | Módulo `inteligencia_eleitoral` opt-in, restrito ao plano Premium e habilitado por tenant |
| RF-002 / RN-002 | Acesso integral do Parlamentar vinculado a mandato ativo no próprio tenant |
| RF-003 / RN-003 | Modelo de delegação granular, temporária e revogável; interface permanece desabilitada |
| RF-004 | Auditoria minimizada de acessos concedidos e negados |
| RN-004 | Administradores não recebem acesso implícito ao conteúdo eleitoral |
| RN-005 / RN-006 | Tenant derivado da sessão, recursos privados tenant-scoped e protegidos por RLS |
| RNF-006 | Testes de módulo, plano, papel, mandato, delegação e isolamento lógico |
| RNF-009 | Blueprint registrado em `/api/v1/electoral` |

## Fluxo implementado

1. O Administrador Geral contrata o plano Premium e habilita o módulo no gabinete.
2. A autenticação só devolve o módulo entre os módulos efetivos quando plano e
   configuração são compatíveis.
3. O menu aparece apenas para `representative`.
4. `GET /api/v1/electoral/disponibilidade` revalida sessão, contrato, plano, módulo,
   tenant, mandato ativo e capacidade.
5. O acesso concedido ou negado é auditado sem conteúdo pessoal ou prompt.
6. A tela informa que a fundação está habilitada e que o catálogo oficial será a
   próxima entrega.

## Modelo e segurança

- `mandates` formaliza o mandato ativo e é sincronizada com o usuário Parlamentar e
  o perfil já existente do tenant;
- `electoral_module_settings` reserva limiar de privacidade e flags das próximas
  capacidades;
- `electoral_access_delegations` exige grantor, grantee e mandato do mesmo tenant por
  chaves estrangeiras compostas;
- as três tabelas usam `ENABLE/FORCE ROW LEVEL SECURITY` no PostgreSQL;
- a migration cria grants explícitos para as roles da API e do worker;
- uma restrição parcial permite somente um mandato ativo por tenant no PostgreSQL.

## Limites desta entrega

- não há dataset, pesquisa, resultado, comparação ou mapa eleitoral;
- a interface de delegação está intencionalmente desabilitada até a decisão de
  produto sobre a exceção ao acesso visual exclusivo do Parlamentar;
- somente o plano Premium possui entitlement nesta primeira política comercial;
- as flags de catálogo, exportação, overlay, IA, cenários e delegação começam falsas.

## Validação

- testes backend cobrem default opt-in, plano, habilitação, mandato, papel, delegação
  e auditoria;
- testes frontend cobrem menu exclusivo e estado da fundação;
- OpenAPI documenta a disponibilidade e a autenticação por cookie;
- AsyncAPI passa a exigir versão e chave de idempotência nos eventos eleitorais.
