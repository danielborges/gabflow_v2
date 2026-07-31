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
- Antes da classificação, o conteúdo passa por canonicalização limitada; o
  classificador usa contrato fechado e modelo independente do gerador de respostas.
- Somente versão, provider, modelo, label, score e categorias são persistidos; texto
  analisado e justificativa livre do classificador não entram no estado de segurança.
- Uploads são enviados ao ClamAV por stream antes de serem gravados e têm seu MIME
  real validado; timeout, limite excedido ou resposta inválida bloqueiam a operação.
- Antes do parsing, checksum e antimalware são revalidados. O parser roda em sidecar
  sem rede e segredos, com entradas read-only e contrato de resposta limitado.
- A resposta final passa por validador independente antes de persistência e entrega;
  vazamento de prompt/segredo e alegação de ação externa são sempre bloqueados.
- Sinais adicionais de citação e destino externo entram por rollout tenant-scoped,
  com amostra, taxa de bloqueio, promoção e rollback auditáveis.

## Criptografia por tenant e auditoria RLS

- Objetos privados e anexos são cifrados com AES-256-GCM antes da gravação.
- A chave de dados é derivada da chave mestra, do identificador do tenant e da
  versão; o mesmo ciphertext não autentica sob outro tenant.
- O catálogo compartilhado usa escopo criptográfico global separado.
- Checksum, antivírus e parsing operam sobre plaintext autenticado em arquivo
  temporário efêmero, removido ao final da operação.
- Rotação incrementa `STORAGE_ENCRYPTION_KEY_VERSION` e usa a revarredura para
  recifrar objetos limpos; metadados registram algoritmo, versão e instante.
- A auditoria RLS inspeciona toda tabela RAG tenant-scoped e anexos, exige RLS
  habilitado e forçado, política por `app.tenant_id`, roles sem superuser/bypass e
  executa prova de inexistência de linhas estrangeiras visíveis.

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
- Revarreduras por versão de política congelam um corte do acervo, invalidam alvos
  pendentes e registram cursor, progresso, assinaturas e contadores de purge.
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

## Threat model de conteúdo não confiável

O threat model normativo está em
`architecture/rag-content-security-threat-model.md`. Ele distingue o isolamento de
tenant, já protegido por RLS e constraints, da resistência a prompt injection.
Criptografia, RLS e antivírus são camadas complementares, mas não tornam conteúdo
documental confiável como instrução.

O incremento 5.1 estabelece que todo conteúdo originado de upload, catálogo global,
projeção operacional, OCR, transcrição, feedback, consulta ou conector permanece não
confiável. A aprovação para indexação autoriza uso como dado, nunca como comando. Os
incrementos seguintes devem implementar um gateway uniforme antes de chunks e
embeddings, segunda inspeção no retrieval e validação de saída.
