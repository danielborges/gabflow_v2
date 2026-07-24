# Segurança, Privacidade e LGPD

## Princípios

- minimização;
- finalidade;
- necessidade;
- transparência;
- segurança;
- prevenção;
- não discriminação;
- responsabilização.

## Controles

- RBAC e, quando necessário, ABAC.
- MFA para administradores.
- Criptografia em trânsito e repouso.
- Segregação por tenant.
- Logs de auditoria.
- Varredura de anexos.
- URLs assinadas.
- Retenção configurável.
- Anonimização.
- Gestão de consentimento.
- Registro de base legal.
- Exportação de dados do titular.
- Correção de dados.
- Resposta a incidentes.
- Inventário de tratamento.
- Política de uso de IA.

## Restrições para IA

- não enviar dados além do necessário;
- permitir provedores com retenção desabilitada;
- mascarar PII quando possível;
- registrar o modelo utilizado;
- bloquear uso de dados do tenant para treinamento externo sem autorização;
- revisar prompts e outputs;
- limitar acesso da IA a ferramentas;
- impedir ações destrutivas autônomas.

## Isolamento do RAG privado

- RLS com negação por padrão, `USING`, `WITH CHECK` e `FORCE ROW LEVEL SECURITY`.
- Contexto `app.tenant_id` local à transação, definido após validação do usuário.
- API e worker executados como `NOSUPERUSER` e `NOBYPASSRLS`.
- Migração, aplicação, worker e backup usam credenciais distintas.
- Filtros de aplicação permanecem obrigatórios como defesa adicional.
- Foreign keys privadas incluem `tenant_id`.
- Reutilização de conexão não pode preservar contexto entre tenants.
- Workers ativam o tenant antes de carregar qualquer aggregate privado.
- Objetos privados usam namespace e autorização vinculados ao tenant.

## Fronteira global e privada

- O catálogo global é somente leitura para tenants e contém apenas versões
  publicadas e elegíveis.
- Administradores globais não possuem acesso implícito ao RAG privado.
- Promoção de conteúdo privado exige autorização, anonimização, revisão e criação
  de nova fonte global.
- O RAG de um tenant nunca influencia outro tenant.
- Acesso excepcional de suporte é temporário, escopado e auditado.

## Conectores de conhecimento

- Domínios e rotas externas usam allowlist.
- Endereços privados, metadata services e redirecionamentos indevidos são
  bloqueados para prevenir SSRF.
- Credenciais permanecem em cofre de segredos e nunca entram em chunks.
- Conteúdo sincronizado passa por validação, quarentena e publicação versionada.
- Prompt injection é avaliado na ingestão e na recuperação.
