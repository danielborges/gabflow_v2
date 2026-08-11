# 6. Segurança e LGPD

## Papéis

Em regra, o gabinete/órgão define finalidade e meios essenciais e atua como controlador; o GabFlow atua como operador nos limites contratuais. A qualificação deve ser validada juridicamente para cada contratação. Meta e fornecedores podem exercer papéis próprios conforme seus termos.

## Princípios

- Finalidade clara, adequação, necessidade e transparência.
- Coleta mínima; CPF, documento, saúde, opinião política e outros dados sensíveis não são padrão.
- Segregação por tenant e acesso pelo menor privilégio.
- Privacidade por padrão; campanhas e enriquecimento de perfil desativados.
- Decisões relevantes permanecem revisáveis por pessoa.

## Controles obrigatórios

- OIDC/OAuth2, MFA para administradores e RBAC por tenant.
- Tokens Meta em secret manager, nunca no banco em texto simples ou frontend.
- TLS, criptografia de banco/storage, URLs de mídia curtas e antivírus.
- Assinatura/verificação dos webhooks e proteção contra replay.
- Rate limit por tenant, cidadão, IP e ação sensível.
- Auditoria imutável de conexão, leitura sensível, exportação e exclusão.
- Redação de PII em logs, traces, erros, analytics e prompts sempre que possível.
- DPA/contratos com subprocessadores, localização e retenção documentadas.
- Backups criptografados, restore testado e expiração consistente.
- Testes SAST, dependências, segredo, DAST e pentest antes de escala.

## Aviso conversacional mínimo

Na primeira interação relevante, informar identidade do gabinete, que o atendimento é processado pelo GabFlow, finalidades, possível uso de automação/IA, link para aviso completo e comandos de saída. Consentimento não deve ser usado indiscriminadamente quando outra base legal for aplicável.

## Direitos do titular

Disponibilizar fluxo autenticado/proporcional para confirmação de tratamento, acesso, correção, portabilidade quando aplicável, informação sobre compartilhamentos, oposição/revogação e eliminação quando possível. Pedidos entram em fila com prazo, responsável e evidência.

## Proibições

- Não usar dados de atendimento para propaganda eleitoral ou perfil político sem análise jurídica e consentimentos adequados.
- Não misturar base institucional do mandato com base partidária/campanha.
- Não usar conversas para treinar modelo compartilhado por padrão.
- Não expor solicitações de um cidadão ao consultar apenas um protocolo enumerável.
- Não permitir que prompts ou anexos executem ferramentas sem allowlist e autorização.

## Incidentes

Playbook: detectar, conter, preservar evidências, avaliar escopo/risco, comunicar controlador e autoridades/titulares quando aplicável, corrigir causa e registrar pós-incidente. Incidente multi-tenant deve permitir identificar com precisão os tenants afetados.
