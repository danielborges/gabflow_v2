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

## Fluxo

1. O usuário seleciona uma solicitação principal, até 19 relacionadas, o tipo e os fatos relevantes.
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
23. O contrato `FoundationRetriever` permite substituir o índice relacional por um serviço RAG sem alterar o fluxo de revisão.

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
- aprovação exige perfil `admin` ou `manager` e confirmação explícita da fundamentação;
- o protocolo é único no tenant e somente pode ser registrado após aprovação;
- os andamentos não possuem API de edição ou exclusão e não aceitam datas retroativas;
- templates não são excluídos fisicamente; a desativação preserva vínculos de minutas anteriores;
- nomes de templates são únicos no tenant, inclusive sem diferenciação entre maiúsculas e minúsculas;
- a pré-visualização renderiza a estrutura como texto, sem interpretar HTML;
- somente `admin` ou `manager` registra tramitação; usuários autenticados do tenant podem consultá-la;
- não existe chamada automática para sistemas legislativos externos;
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
```

## Compatibilidade com o futuro RAG

A primeira versão consulta o catálogo relacional e calcula embeddings em lote no Ollama. A interface de recuperação retorna consulta, coleção, modelo, score, fontes e proveniência em um formato estável. O futuro serviço RAG poderá implementar o mesmo contrato, adicionando indexação vetorial, páginas e estados de revogação, sem remover a confirmação humana ou a filtragem por tenant.
