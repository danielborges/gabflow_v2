# Release 8.6 — IA permanente e convergência OpenAPI

## Resultado

A capacidade `ia` deixa de ser uma opção desabilitável por gabinete. Ela permanece
ativa em todos os tenants, sem alterar a fronteira de acesso do módulo: Inteligência
Eleitoral continua disponível somente ao perfil Parlamentar e às capacidades delegadas
previstas no domínio.

A migração `u4e2c9f7a1b3` normaliza configurações existentes, cria a configuração
eleitoral ausente para tenants legados e preserva `ia: true` em downgrade. A API também
força esse invariável ao calcular a disponibilidade, portanto um valor legado
`ia: false` não volta a bloquear os endpoints de IA.

## Convergência do contrato

O contrato eleitoral foi promovido para `8.6.0` e alinhado à aplicação em quatro níveis:

- conjunto exato de caminhos e métodos Flask;
- códigos HTTP explícitos, incluindo atualização idempotente de favoritos e `404`;
- corpos JSON de atualização e evidência de compromissos públicos;
- referências, parâmetros de caminho e `operationId` válidos e únicos.

O schema de disponibilidade agora publica `funcionalidades.ia` e
`iaEleitoral.enabled` como constantes verdadeiras.

## Regressão e homologação

`test_electoral_openapi_contract.py` impede novas diferenças entre implementação e
OpenAPI. O ciclo real de migração foi validado em PostgreSQL descartável com uma
configuração legada `ia: false`, além da suíte eleitoral e da suíte backend completa.
API, worker geral e worker RAG foram reconstruídos e verificados em execução.
