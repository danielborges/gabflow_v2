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

## Conhecimento operacional

- Eventos transportam somente tenant, tipo, ID, ação e revisão; conteúdo sensível é
  relido pelo worker no contexto RLS.
- Projetores usam allowlist de campos e omitem cadastros pessoais, endereços e
  identificadores que não sejam necessários à finalidade.
- Conteúdo interno passa por avaliação de PII e prompt injection antes do embedding
  e novamente antes de compor o contexto.
- ACL, finalidade, vigência e estado são aplicados antes da busca e do ranking.
- Exclusão, anonimização e expiração despublicam imediatamente a fonte e propagam
  purge para todos os artefatos derivados.
- Reconciliação periódica detecta fontes órfãs, expiradas ou divergentes.
- Consultas estruturadas usam os mesmos filtros de tenant e autorização do domínio
  transacional; o modelo não recebe acesso SQL irrestrito.

## Feedback e aprendizado

- Comentário e resposta corrigida são entradas não confiáveis, sujeitas a limite de
  tamanho, normalização, minimização de PII e detecção de prompt injection.
- Feedback suspeito fica em `QUARENTENA`; texto bruto não entra em prompt, embedding,
  log, métrica, payload de evento ou artefato de aprendizado.
- Todo julgamento de fonte é validado contra as fontes/versões da consulta e contra
  a autorização atual do tenant.
- Compiladores e caches usam `tenant_id` na chave, contexto RLS transacional e
  credenciais `NOBYPASSRLS`.
- Limites por usuário e período, quantidade mínima de sinais e detecção de anomalias
  reduzem envenenamento coordenado ou acidental.
- Artefatos possuem schema fechado, checksum, proveniência, aprovação e rollback.
- Correções não são promovidas ao catálogo global ou a datasets compartilhados sem
  processo separado de autorização, anonimização e revisão.
- A promoção ao dataset privado copia somente pergunta, IDs/versionamentos,
  julgamentos e expectativas estruturadas; comentário e resposta corrigida não
  integram o caso de avaliação.
- Casos curados usam FK composta com feedback e tenant, e são reconciliados antes
  de listagem ou execução para impedir uso de sinal revogado ou fonte inacessível.
