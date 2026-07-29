# Arquitetura RAG hierárquica

## Objetivo

O GabFlow deve oferecer conhecimento institucional compartilhado sem comprometer a
privacidade de cada gabinete. O contexto efetivo de um tenant é uma composição:

```text
Conhecimento efetivo do gabinete
    = catálogo global autorizado
    + conhecimento privado do tenant
```

Essa composição é realizada durante a recuperação. O catálogo global não é copiado
integralmente para cada tenant e o conteúdo privado nunca é promovido, compartilhado
ou usado por outro tenant de forma implícita.

## Escopos de conhecimento

### RAG Geral

O RAG Geral é um catálogo curado e versionado, administrado exclusivamente por
perfis de conhecimento global. Pode conter legislação, normativas, jurisprudência,
modelos, documentação institucional e conteúdo sincronizado de APIs homologadas.

O catálogo global:

- é somente leitura para usuários de gabinete;
- contém apenas versões publicadas e auditáveis;
- classifica jurisdição, vigência, proveniência e política de distribuição;
- não concede ao administrador global acesso aos dados privados dos tenants;
- não recebe conteúdo privado sem autorização, anonimização, revisão e nova
  publicação explícita.

### RAG Privado

Cada tenant possui uma base privada que recebe documentos enviados pelo gabinete e
projeções governadas das informações internas elegíveis produzidas nos módulos.
Solicitações, interações, encaminhamentos, respostas oficiais, minutas,
tramitações, OCR e transcrições revisados, atas concluídas e relatórios de
fiscalização concluídos possuem cobertura. Cada origem é incorporada somente pelo
respectivo projetor registrado.
Elegibilidade considera aprovação, finalidade, base legal, retenção, sigilo, ACL e
minimização; informação inelegível não deve ser enviada ao modelo.

O RAG Privado:

- possui `tenant_id` obrigatório em toda entidade;
- é protegido por Row-Level Security, constraints compostas e namespace de arquivos;
- não pode ser consultado por outro tenant;
- não altera o catálogo global nem o ranking de outros tenants;
- respeita nível de acesso, finalidade, retenção, base legal e minimização.

“Aprender”, neste contexto, significa incorporar conhecimento recuperável,
versionado e governado. Treinamento ou fine-tuning de modelo é um processo separado
e nunca ocorre implicitamente com dados privados.

## Conhecimento operacional governado

Informações dos módulos não são copiadas diretamente de tabelas para o índice.
Cada tipo de entidade elegível possui um projetor registrado e versionado:

```text
alteração no módulo
  -> evento transacional no outbox, sem conteúdo sensível
  -> worker no contexto RLS do tenant
  -> projetor do tipo de entidade
  -> elegibilidade + allowlist + PII + ACL + segurança
  -> snapshot canônico e hash
  -> versão privada imutável
  -> chunks e embeddings
  -> ativação atômica da nova versão
```

O contrato do registry é composto por `ProjectorDefinition`, `Projection` e pelo
protocolo `OperationalMemoryProjector`. A definição declara módulo, tipo de
entidade, versão semântica, proprietário, ações suportadas, allowlist, finalidade,
base legal padrão, ACL, retenção, quarentena e purge. O registry impede
duplicidade por tipo, valida a saída contra a política registrada e é a única
origem usada pela sincronização e reconciliação.

O projetor relê o aggregate canônico, em vez de confiar no payload do evento.
Eventos repetidos ou fora de ordem devem convergir pelo hash e revisão da origem.
Varredura agendada é mecanismo auxiliar para backfill, reconciliação, expiração e
detecção de divergência, não o caminho primário de ingestão.

Encaminhamentos e respostas oficiais usam o projetor `REQUEST_FORWARDING`. O
snapshot contém somente protocolo e título da solicitação, nome do órgão,
protocolo externo, observações, estado, prazo e resposta registrada. Contatos do
órgão e dados cadastrais do cidadão não são projetados. Alterações na
solicitação-pai e no nome do órgão invalidam o snapshot dependente.

Tramitações usam `LEGISLATIVE_TRAMITATION`; OCR e transcrições usam
`DOCUMENT_OCR` e `AUDIO_TRANSCRIPTION` somente após revisão humana; atas usam
`AGENDA_EVENT` somente no estado realizado; relatórios de fiscalização usam
`OVERSIGHT_ACTION` somente no estado concluído. Conteúdo bruto, participantes,
fotos e responsáveis identificados permanecem fora das projeções.

Memórias temáticas são agregados persistidos e reprojetáveis por tema, território
e período. Grupos abaixo de `RAG_THEMATIC_MIN_GROUP_SIZE` não são publicados.
Consultas estruturadas operam diretamente sobre dados tenant-scoped e retornam o
método, dataset, métrica, agrupamento, filtros, período e base de cálculo.

O endpoint conversacional classifica a intenção de forma determinística:

- indicadores, contagens, médias, prazos e agrupamentos usam `ESTRUTURADO`;
- pedidos de argumentos, fundamentos, relatos ou evidências usam `DOCUMENTAL`;
- perguntas que combinam ambos usam `HIBRIDO`.

Filtros explícitos podem complementar a extração automática, mas somente chaves
em allowlist são aceitas. Método, motivos de roteamento, filtros aplicados e
resultado estruturado são persistidos na consulta e na auditoria. O modo
estruturado não executa embeddings; o híbrido combina o cálculo reproduzível com
as citações documentais sem transformar contagem em evidência semântica.

A avaliação de retrieval mantém perguntas reais por tenant, documentos esperados
ou expectativa de recusa e execuções históricas por `k`. Os resultados incluem
`precision@k`, `recall@k`, groundedness, precisão das citações, taxa de fontes
desconexas e acurácia de recusa.

O evento operacional V2 transporta somente versão do schema, módulo, tipo e ID da
entidade, ação e revisão de ordenação. A revisão processada é persistida na fonte;
eventos repetidos ou anteriores são descartados antes de reler ou reprojetar o
aggregate. Eventos V1 já persistidos continuam aceitos como reconciliação legada.

Cancelamento, exclusão, anonimização ou expiração despublicam a fonte
imediatamente. Quando a política exigir eliminação, o purge remove chunks,
embeddings, texto extraído, versões derivadas e objeto privado, preservando apenas
auditoria sem conteúdo.

Não são fontes operacionais elegíveis cadastros brutos de cidadãos, consentimentos,
solicitações de privacidade, credenciais, configurações, notificações, auditoria
bruta ou saídas de IA ainda não aprovadas.

## Organização de persistência

O alvo arquitetural utiliza schemas distintos:

```text
rag_global
  collections
  documents
  document_versions
  chunks
  api_sources
  distribution_policies

rag_private
  collections
  documents
  document_versions
  chunks
  knowledge_sources
  assistant_queries
  feedback
  global_entitlements
```

O schema global não concede `SELECT` direto sobre tabelas-base para usuários de
tenant. O consumo ocorre por view `security_barrier` ou função controlada que retorna
somente conteúdo publicado e elegível segundo as concessões do tenant. Concessões
são tenant-scoped e protegidas junto ao domínio privado.

O schema privado aplica RLS com `FORCE ROW LEVEL SECURITY`. API e worker usam roles
`NOSUPERUSER` e `NOBYPASSRLS`; migrations e backup utilizam credenciais separadas.

As relações privadas usam chaves compostas, por exemplo
`FOREIGN KEY (tenant_id, document_id)`, para impedir associações cruzadas mesmo
quando um identificador válido de outro tenant for fornecido.

## Políticas de distribuição global

Uma coleção ou documento global possui uma das políticas:

- `OBRIGATORIA`: habilitada para todos os tenants elegíveis;
- `PADRAO`: habilitada na criação, com possibilidade de desativação;
- `OPCIONAL`: depende de adesão do administrador do tenant;
- `DIRECIONADA`: depende de concessão explícita;
- `RESTRITA_JURISDICAO`: depende de país, UF, município, esfera ou tipo de casa;
- `PRIVADA_PLATAFORMA`: indisponível aos tenants.

Uma concessão registra tenant, coleção, versão fixada quando aplicável, modo de
atualização, concessor, justificativa, vigência e trilha de auditoria.

## Atualização, fixação e fork

- **Atualização automática:** o tenant utiliza a versão global publicada e elegível
  mais recente.
- **Versão fixada:** o tenant permanece em uma versão específica até aprovação de
  atualização.
- **Fork privado:** uma versão global é copiada explicitamente para o RAG Privado e
  passa a evoluir de forma independente.

O fork preserva documento e versão de origem, checksum, data, responsável e
histórico de divergência. Alterações no fork não retornam ao catálogo global.

## Fontes externas e APIs

Uma API externa é cadastrada como fonte controlada, não como instrução executável.
Seu conector deve possuir:

- domínios, métodos, rotas e tipos de conteúdo permitidos;
- autenticação armazenada em cofre de segredos;
- limites de tamanho, paginação, frequência e timeout;
- proteção contra SSRF, redirecionamentos indevidos e conteúdo malicioso;
- histórico de sincronização, checksum e proveniência;
- quarentena e validação antes da publicação.

O resultado de cada sincronização gera uma versão imutável. Respostas já emitidas
continuam apontando para a versão exata que as fundamentou.

## Pipeline de ingestão

1. Resolver escopo global ou privado e autorização de escrita.
2. Receber arquivo, projeção interna governada ou conteúdo de conector homologado.
3. Validar tipo, tamanho, malware, proveniência e finalidade.
4. Extrair texto e aplicar OCR quando necessário.
5. Detectar idioma, estrutura, PII e tentativa de prompt injection.
6. Colocar conteúdo suspeito em quarentena.
7. Extrair metadados, jurisdição, vigência e nível de acesso.
8. Gerar chunks com sobreposição e vínculo à versão imutável.
9. Criar embeddings com modelo e dimensão registrados.
10. Indexar texto, vetores e filtros de autorização.
11. Executar testes de qualidade e segurança.
12. Publicar a versão mediante autorização compatível com o escopo.

## Recuperação federada e roteamento híbrido

Antes da recuperação, um roteador classifica a intenção:

- **documental:** busca fontes e evidências semânticas;
- **estruturada:** executa read model tenant-scoped para contagens, estados, prazos
  e agrupamentos;
- **híbrida:** combina resultado estruturado reproduzível com fontes documentais.

Uma consulta documental autenticada executa duas recuperações independentes:

1. recuperar fontes globais publicadas, vigentes e autorizadas ao tenant;
2. recuperar fontes privadas pertencentes ao tenant e acessíveis ao usuário;
3. aplicar tenant, ACL, módulo, entidade, tema, território, período, vigência,
   finalidade e estado antes do ranking;
4. executar busca vetorial e textual sobre o conjunto elegível;
5. normalizar scores, remover duplicidades e reranquear por relevância, autoridade
   e atualidade;
6. montar contexto com separação explícita entre dados e instruções;
7. gerar resposta fundamentada;
8. verificar groundedness e correspondência das citações;
9. recusar conclusão quando a evidência for insuficiente;
10. registrar consulta, método, filtros, fontes, versões, escopos, modelo e feedback.

Diversidade entre escopos é um critério secundário e nunca pode incluir fonte abaixo
do limiar de evidência. Quando nenhum candidato autorizado e pertinente satisfizer
o limiar, o assistente deve recusar a conclusão.

Cada citação informa no mínimo `escopo`, coleção, documento, versão, checksum,
jurisdição, trecho ou página e pontuação. A interface diferencia “Fonte GabFlow” de
“Fonte do Gabinete”.

## Isolamento transacional

Após validar JWT, usuário, tenant e contrato, a API configura o tenant na transação:

```sql
SELECT set_config('app.tenant_id', :tenant_id, true);
```

Políticas privadas usam esse valor tanto em `USING` quanto em `WITH CHECK`. A
ausência de contexto resulta em negação por padrão. O valor é local à transação para
não vazar entre requisições que reutilizam conexões do pool.

Workers ativam o mesmo contexto antes de carregar qualquer payload privado. Claims
globais da outbox podem ocorrer fora do contexto, mas o processamento do aggregate
é sempre tenant-scoped.

## Armazenamento

Objetos privados usam chaves construídas exclusivamente pelo servidor:

```text
tenants/{tenant_id}/rag/{document_id}/{version_id}/{arquivo}
```

URLs assinadas vinculam tenant, documento, versão, finalidade e expiração. O
download revalida autorização no banco antes de emitir a URL. Objetos globais usam
namespace e credenciais distintos. Criptografia por tenant pode ser oferecida em
planos de maior garantia.

## Administração e suporte

Os papéis de administração são separados:

- `GLOBAL_KNOWLEDGE_ADMIN`: gerencia apenas o catálogo global;
- `PLATFORM_ADMIN`: administra plataforma, contratos e metadados;
- `TENANT_ADMIN`: administra apenas o RAG Privado de seu gabinete;
- `TENANT_SUPPORT`: acessa um tenant somente por concessão temporária e auditada.

O acesso excepcional exige tenant, solicitante, autorizador, motivo, escopo,
validade e auditoria. Nenhuma role cotidiana utiliza `BYPASSRLS`.

## Segurança contra instruções maliciosas

- Conteúdo recuperado é dado, nunca instrução.
- Conteúdo suspeito é detectado antes da publicação e novamente na recuperação.
- Instruções presentes em documentos não são incluídas em mensagens de sistema.
- Conectores não podem escolher ferramentas, URLs ou comandos fora da allowlist.
- PII é removida ou mascarada quando não necessária ao caso de uso.
- Promoção privado → global exige autorização, anonimização e revisão humana.
- Testes de red team cobrem ofuscação, múltiplos idiomas e ataques indiretos.

## Estratégia de escala

O modelo padrão compartilha infraestrutura com isolamento lógico forte. A busca
vetorial mantém `tenant_id` como filtro obrigatório e pode usar particionamento por
hash quando o volume crescer. Instância, banco, índice e chave dedicados são uma
opção de implantação para tenants enterprise, sem alterar o contrato funcional.

O processamento assíncrono é separado em filas lógicas `default` e `rag`. Cada
fila pode escalar horizontalmente com claims `FOR UPDATE SKIP LOCKED` e índices
parciais de prontidão. O scheduler usa advisory lock e a reconciliação opera em
lotes com commits curtos.

Saúde e SLO globais são derivados do outbox, sem acesso a conteúdo privado.
Groundedness, fallback, feedback e latência permanecem tenant-scoped. Logs
estruturados preservam correlação sem copiar prompts ou chunks.

## Estado atual e alvo

A Release 4 implementou ingestão documental privada, versionamento, chunks,
embeddings, filtros de aplicação, citações e registro de feedback. A Release 4.1
adicionou contexto transacional, RLS forçado, roles segregadas, constraints
compostas, worker tenant-scoped, namespace canônico e download assinado. A Release
4.2 adicionou o schema `rag_global`, curadoria com papel exclusivo, ingestão
assíncrona, versões imutáveis e ciclo auditável de publicação, substituição,
suspensão e revogação. A Release 4.3 adicionou concessões protegidas por RLS,
resolução de política e jurisdição, view global `security_barrier` e recuperação
federada global + privada com proveniência explícita. A Release 4.4 adicionou
memória operacional privada governada para solicitações, interações e minutas
legislativas. A Release 4.5
adicionou filas escaláveis, índices de claim, scheduler com lock, reconciliação em
lotes, logs estruturados, métricas e SLOs. Ainda são alvo arquitetural:

- migração física das tabelas privadas existentes para o schema `rag_private`;
- fork privado de versões globais;
- migração da varredura exata em lotes para PostgreSQL FTS + pgvector, preservando
  o ranking corrigido e usando índices por modelo/dimensão;
- expansão dos projetores e do ciclo de vida já implementado para os demais
  módulos elegíveis;
- ampliação gradual da ingestão para os demais módulos elegíveis;
- roteamento entre recuperação documental e consultas estruturadas tenant-scoped;
- conectores globais controlados;
- uso efetivo do feedback em melhoria de recuperação e resposta.
