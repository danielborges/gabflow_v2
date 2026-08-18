# P2 - Produção Legislativa

## Fatias entregues

| Spec | Implementação |
| --- | --- |
| RIA-030 | Geração assíncrona de minuta baseada em solicitações e fatos selecionados |
| RIA-031 | Catálogo tenant-safe de proposições semelhantes por conteúdo |
| RIA-032 | Recuperação automática em catálogo normativo tenant-safe, com citações versionadas e confirmação humana |
| RIA-033 | Estrutura e justificativa sugeridas conforme o tipo documental |
| RIA-034 | Marcação de trechos normativos sem fonte e confirmação humana na aprovação |
| RIA-035 | Protocolo automático desabilitado; registro somente por ação explícita de gestor |
| RF-060, RF-061 e RF-065 | Tipos, revisão e aprovação |
| RF-064 | Histórico imutável, comparação campo a campo e restauração como nova versão |
| RF-063 | Vínculo de até 20 solicitações, com principal identificada e seleção visual |
| RF-062 e RF-091 | Gestão visual tenant-safe de templates, com preview, edição e ativação |
| RF-066 | Exportação local para DOCX e PDF |
| RF-067 | Protocolo manual e tramitação append-only, tenant-safe e auditada |
| RF-068 | Busca semântica tenant-safe com embeddings locais, filtros, score explicável e fallback lexical |
| RF-069 | Retificação append-only de protocolo e andamento por evento compensatório auditado |
| RIA-055, RIA-066 a RIA-069 e RF-098 a RF-103 | Projeção governada de minutas, tramitações e fontes normativas no RAG Privado, com outbox V2, versionamento material, retenção, quarentena e purge |
| UX Documentos | Submenu lateral por área e catálogo de minutas paginado, pesquisável, filtrável e ordenável |

## Fluxo

1. O usuário seleciona uma solicitação principal, até 19 relacionadas, o tipo e os fatos relevantes.
   A entrada ocorre pelo submenu `Documentos > Minutas`; Precedentes, Templates e Base normativa possuem páginas próprias.
2. A API cria imediatamente uma minuta com status `RASCUNHO` e geração `PENDENTE`.
3. O worker processa o evento `GeracaoMinutaLegislativa` no Ollama local.
4. Falhas do Ollama usam o fallback `gabflow-legislative-rules-v1` quando habilitado.
5. A versão inicial é persistida com fontes, confiança, guardrails e trechos pendentes.
6. Cada salvamento humano cria uma versão imutável.
7. A minuta precisa ser submetida e aprovada por gestor antes do protocolo manual.
8. O protocolo cria o primeiro evento `PROTOCOLADA` da timeline.
9. Gestores registram os andamentos posteriores, preservando sua ordem cronológica.
10. Na visão Templates, gestores criam, editam, desativam e reativam estruturas legislativas.
11. Somente templates ativos e compatíveis com o tipo aparecem na geração de novas minutas.
12. O detalhe preserva a ordem dos vínculos e destaca qual solicitação originou a minuta.
13. O histórico identifica autor, data e motivo de cada versão e permite consultar seu snapshot.
14. A comparação destaca campos e linhas adicionadas ou removidas entre quaisquer duas versões.
15. A restauração exige motivo e cria uma nova versão, preservando integralmente o histórico anterior.
16. A aba Precedentes pesquisa título, conteúdo, justificativa e fundamentação por significado.
17. A busca usa `nomic-embed-text` no Ollama local e retorna score, modelo e justificativas.
18. Se o modelo estiver indisponível, a pesquisa continua com similaridade lexical local sinalizada.
19. Gestores mantêm um catálogo de fontes normativas com tipo, referência, trecho, versão, vigência, URL e checksum.
20. Ao concluir a minuta, o worker recupera fontes vigentes com embeddings locais e combinação lexical.
21. O assessor pode repetir a busca, revisar score e proveniência e selecionar somente fontes recuperadas.
22. A aplicação exige motivo, revalida tenant e vigência, cria uma nova versão e mantém a citação auditável.
23. O contrato `FoundationRetriever` recupera os chunks normativos projetados no RAG
    Privado e revalida cada resultado no catálogo relacional autoritativo.
24. Erros materiais de protocolo e tramitação são corrigidos por retificações vinculadas; o registro original nunca é alterado ou apagado.
25. O estado vigente ignora registros substituídos e considera o evento compensatório mais recente da cadeia efetiva.
26. Gestores podem conectar consultas do LexML; o worker executa sincronizações periódicas e também permite execução sob demanda.
27. Conteúdo externo entra em uma fila tenant-safe de revisão e não participa da fundamentação nem do RAG antes da aprovação.
28. A aprovação publica uma nova versão com proveniência, checksum e vínculo à anterior; a rejeição preserva a decisão sem alterar o catálogo ativo.

## Segurança e governança

- consultas, templates, minutas, versões e vínculos são filtrados por tenant;
- a API rejeita coleções de vínculos que não sejam listas, excedam 20 itens ou repitam IDs;
- o modelo recebe somente solicitações vinculadas, fatos selecionados, template e fontes;
- fontes normativas nunca são aceitas da saída gerativa do modelo: entram pela seleção humana ou pelo catálogo governado;
- a recuperação considera somente fontes ativas, vigentes e pertencentes ao tenant autenticado;
- nenhuma sugestão recuperada altera a minuta sem seleção e motivo informados pelo usuário;
- citações confirmadas preservam ID, referência, versão, URL e checksum da fonte;
- o recuperador trata documentos como dados e não executa instruções presentes nos trechos;
- referências legais não presentes nas fontes são marcadas como não fundamentadas;
- toda minuta gerada por IA começa como rascunho;
- aprovação exige perfil `admin`, `manager` ou `representative` e confirmação explícita da fundamentação;
- o protocolo é único no tenant e somente pode ser registrado após aprovação;
- os andamentos não possuem API de edição ou exclusão e não aceitam datas retroativas;
- templates não são excluídos fisicamente; a desativação preserva vínculos de minutas anteriores;
- nomes de templates são únicos no tenant, inclusive sem diferenciação entre maiúsculas e minúsculas;
- a pré-visualização renderiza a estrutura como texto, sem interpretar HTML;
- `admin`, `manager` ou a função `chefe_gabinete` podem rejeitar, protocolar, tramitar e retificar; `representative` possui aprovação política, mas não essas mutações operacionais;
- assessor comum cria, edita e submete minutas, sem permissão para decisões finais, protocolo, tramitação ou retificação;
- cada retificação exige motivo de 10 a 500 caracteres, preserva o registro substituído e gera auditoria com antes e depois;
- não existe chamada automática para sistemas legislativos externos; o modo atual é o
  adaptador `MANUAL`, e integrações futuras devem seguir a porta canônica, capabilities,
  idempotência e reconciliação do
  [ADR-013](../specs/adr/ADR-013-generic-legislative-integration.md);
- geração, edições, aprovação, rejeição, protocolo e novos andamentos geram auditoria.
- versões de outro tenant não podem ser consultadas ou comparadas;
- restaurações são permitidas somente em minutas editáveis e nunca alteram snapshots anteriores;
- restauração da versão atual, restauração sem motivo e restauração após aprovação são bloqueadas.
- a busca semântica seleciona candidatos exclusivamente do tenant autenticado;
- filtros e limites são validados na API e a própria minuta pode ser excluída das sugestões;
- o modelo recebe somente a consulta e textos legislativos já pertencentes ao tenant atual.

## Configuração

```env
AI_LEGISLATIVE_PROVIDER=ollama
AI_LEGISLATIVE_MODEL=qwen2.5:3b
AI_LEGISLATIVE_FALLBACK_MODEL=gabflow-legislative-rules-v1
AI_LEGISLATIVE_PROMPT_VERSION=legislative-v1
AI_LEGISLATIVE_TIMEOUT_SECONDS=120
AI_LEGISLATIVE_FALLBACK_ENABLED=true
AI_PRECEDENT_PROVIDER=ollama
AI_PRECEDENT_SCORE_THRESHOLD=0.60
AI_PRECEDENT_MAX_RESULTS=10
AI_PRECEDENT_CANDIDATE_LIMIT=200
AI_FOUNDATION_PROVIDER=ollama
AI_FOUNDATION_SCORE_THRESHOLD=0.55
AI_FOUNDATION_MAX_RESULTS=5
AI_FOUNDATION_CANDIDATE_LIMIT=200
RAG_OPERATIONAL_MEMORY_ENABLED=true
RAG_OPERATIONAL_MEMORY_MATERIALIZED_SNAPSHOTS=5
```

## Integração entregue com o RAG Privado

O P2 participa da memória operacional privada governada. Não se trata mais de uma
compatibilidade futura:

- `LegislativeDraftProjector` registra a origem `LEGISLATIVE_DRAFT`, versão de projetor
  `1.0.0`, com finalidade `MEMORIA_E_PRODUCAO_LEGISLATIVA`, base legal
  `EXERCICIO_DA_FUNCAO_LEGISLATIVA` e acesso `INTERNO`;
- a minuta torna-se elegível quando a geração está `CONCLUIDA`, existe conteúdo e a
  política de retenção do tenant ainda permite a projeção;
- somente tipo, título, conteúdo, justificativa, fundamentação, estado, protocolo e
  estado de geração entram pela allowlist do projetor;
- alterações da minuta ou de suas versões provocam nova avaliação da projeção;
- `LegislativeTramitationProjector` registra a origem `LEGISLATIVE_TRAMITATION`, também
  na versão `1.0.0`, com finalidade `ACOMPANHAMENTO_DA_TRAMITACAO_LEGISLATIVA`;
- um andamento só é elegível quando a minuta pai está aprovada, protocolada e dentro da
  retenção; tipo/título/protocolo da minuta, status, etapa, destino, referência,
  observações e ocorrência formam sua allowlist;
- mudanças na minuta reavaliam suas tramitações dependentes; criação, retificação e
  exclusão de andamento também propagam o ciclo de vida da memória correspondente.
- `NormativeSourceProjector` registra fontes ativas e vigentes como `NORMATIVE_SOURCE`,
  preservando tipo, referência, jurisdição, versão, vigência, URL e checksum no conteúdo
  projetado e nos metadados da versão privada;
- criação, alteração, desativação, reativação, expiração ou exclusão da fonte propagam seu
  ciclo de vida para o índice, sem tornar o RAG a fonte oficial da verdade jurídica.

O evento `SincronizacaoMemoriaOperacional`, schema V2, é gravado no outbox na mesma
transação da mudança. Seu payload contém somente módulo, tipo e ID da entidade, ação e
revisão. O worker relê o aggregate dentro do contexto do tenant, aplica elegibilidade,
minimização, ACL, retenção e segurança de conteúdo e só então produz a versão privada.

A origem operacional preserva versão do projetor, revisão processada, finalidade, base
legal, ACL, retenção, hash e estado de sincronização. Mudança material cria nova versão;
entrega duplicada ou fora de ordem não substitui revisão posterior. Atualização pendente,
em quarentena ou com erro não remove a última versão vigente. Exclusão, anonimização ou
expiração despublica imediatamente e aciona purge idempotente de chunks, embeddings,
texto e objetos derivados, mantendo somente tombstone e auditoria sem conteúdo.

Backfill e reconciliação existem como mecanismos auxiliares. O caminho normal permanece
o outbox transacional, conforme o
[ADR-008](../specs/adr/ADR-008-operational-knowledge-projections.md).

## Recuperação normativa integrada

O `FoundationRetriever` usa o índice persistente do RAG Privado para descoberta
semântica e lexical. Os candidatos retornados são materializados novamente a partir de
`normative_sources`, que permanece o catálogo autoritativo para tenant, ativação,
vigência, versão, URL e checksum. A aplicação de uma citação repete essa validação.

Durante o atraso inicial de indexação ou indisponibilidade do embedding, o recuperador
usa o catálogo relacional como fallback lexical e sinaliza `fallbackUtilizado`,
`erroFallback` e `origemRecuperacao`. Revisão humana, confirmação explícita e tratamento
dos trechos como dados continuam obrigatórios.
