# Requisitos de IA, LLM e RAG

## Triagem

- **RIA-001** Classificar categoria e subcategoria.
- **RIA-002** Sugerir prioridade, impacto e urgência.
- **RIA-003** Extrair entidades: endereço, bairro, órgão, data, serviço, pessoas e protocolo.
- **RIA-004** Sugerir órgão ou secretaria competente.
- **RIA-005** Identificar texto potencialmente ofensivo sem bloquear o relato.
- **RIA-006** Detectar risco, emergência ou ameaça e acionar fluxo humano.
- **RIA-007** Produzir resumo de texto, áudio ou conversa.
- **RIA-008** Detectar duplicidade por similaridade semântica, proximidade geográfica e temporal.
- **RIA-009** Transcrever áudio preservando o arquivo original.
- **RIA-010** Realizar OCR com indicação de confiança.

## Assistência ao atendimento

- **RIA-020** Sugerir resposta ao cidadão com linguagem configurável.
- **RIA-021** Resumir histórico antes do atendimento.
- **RIA-022** Sugerir perguntas faltantes.
- **RIA-023** Identificar documentos necessários.
- **RIA-024** Propor próximos passos.
- **RIA-025** Nunca enviar resposta sem ação explícita do usuário, salvo automações previamente aprovadas.

## Produção legislativa

- **RIA-030** Gerar minuta com base em fatos selecionados.
- **RIA-031** Recuperar proposições semelhantes.
- **RIA-032** Identificar fundamentação normativa por recuperação tenant-safe, com citações versionadas e confirmação humana antes da aplicação.
- **RIA-033** Sugerir estrutura e justificativa.
- **RIA-034** Marcar trechos não fundamentados.
- **RIA-035** Impedir protocolo automático.

## RAG

- **RIA-040** Indexar documentos com metadados, vigência, órgão, tipo e versão. **Implementado na Release 4.**
- **RIA-041** Aplicar filtros por tenant e nível de acesso antes da recuperação. **Implementado com filtros de aplicação, contexto transacional, RLS forçado e constraints compostas.**
- **RIA-042** Retornar citações por documento, página ou seção. **Implementado no endpoint `/assistente/consultas`.**
- **RIA-043** Exibir data da fonte. **Implementado na gestão da base documental.**
- **RIA-044** Diferenciar conteúdo vigente, revogado, histórico e rascunho. **Implementado na Release 4.**
- **RIA-045** Recusar resposta conclusiva quando a recuperação for insuficiente. **Implementado com limiar mínimo de evidência.**
- **RIA-046** Registrar consulta, documentos recuperados e resposta. **Implementado com registro persistente e auditoria por hash.**
- **RIA-047** Avaliar risco de prompt injection nos documentos. **Implementado com sinalização por fonte recuperada.**
- **RIA-048** Não executar instruções encontradas dentro das fontes. **Implementado com política explícita e sanitização de trechos suspeitos.**
- **RIA-049** Permitir avaliação positiva, negativa e correção pelo usuário. **Implementado no endpoint de avaliação de consultas RAG.**

## RAG hierárquico e aprendizado controlado

- **RIA-050** Manter catálogo global versionado separado das bases privadas dos tenants. **Implementado no schema `rag_global`, com coleções, documentos, versões, chunks e ciclo de publicação auditável.**
- **RIA-051** Compor o contexto efetivo com fontes globais autorizadas e fontes privadas do tenant, sem copiar o catálogo global por padrão. **Implementado com recuperação separada, deduplicação e reranking conjunto.**
- **RIA-052** Aplicar políticas globais obrigatória, padrão, opcional, direcionada, restrita por jurisdição e privada da plataforma. **Implementado com concessões tenant-scoped, vigência e filtros jurisdicionais.**
- **RIA-053** Permitir atualização automática, fixação de versão e fork privado de fonte global com proveniência preservada. **Implementado parcialmente: atualização automática e fixação estão disponíveis; fork privado permanece planejado.**
- **RIA-054** Diferenciar escopo global e privado em toda citação, auditoria e explicação de ranking. **Implementado com escopo, origem, coleção, versão, checksums, proveniência e scores.**
- **RIA-055** Ingerir automaticamente toda informação interna elegível dos módulos no RAG Privado, preservando finalidade, base legal, nível de acesso, retenção e entidade de origem. **Implementado parcialmente para solicitações, interações e minutas legislativas na Release 4.4; os demais módulos permanecem planejados.**
- **RIA-056** Sincronizar APIs globais homologadas por conectores com allowlist, proteção SSRF, snapshots imutáveis e aprovação de publicação. **Planejado.**
- **RIA-057** Impedir promoção automática de conhecimento privado para o catálogo global; promoção explícita exige autorização, anonimização e revisão humana. **Planejado.**
- **RIA-058** Usar feedback positivo, negativo e corrigido em um pipeline tenant-scoped de avaliação e melhoria, sem alterar diretamente o modelo ou contaminar outros tenants. **Especificado na Release 4.7; implementação planejada.**
- **RIA-059** Executar avaliação de recuperação separada por escopo e conjunta, incluindo precisão de citações, groundedness, vazamento entre tenants e aplicabilidade jurisdicional. **Planejado.**

## Estado dos controles RAG existentes

RIA-047, RIA-048 e RIA-049 possuem implementação inicial. Para serem
considerados completos no alvo hierárquico:

- RIA-047 e RIA-048 requerem detecção na ingestão, quarentena e cobertura contra
  variações ofuscadas e indiretas;
- RIA-049 requer que o feedback participe de avaliação e melhoria futura; hoje ele
  é apenas persistido e auditado.

## Insights

- **RIA-060** Explicar método, período e base de cálculo. **Implementado na Release 5 com regras e janelas explícitas nos alertas e relatório.**
- **RIA-061** Sinalizar correlação sem afirmar causalidade. **Implementado na Release 5 por alertas determinísticos de crescimento, sem decisão automática.**
- **RIA-062** Apresentar intervalo de confiança ou qualidade do dado. **Implementado parcialmente na Release 5 por cobertura geográfica e agregação mínima; intervalo estatístico fica pendente.**
- **RIA-063** Evitar inferência de preferência político-eleitoral individual. **Implementado na Release 5 por restrição documental e ausência de score individual.**
- **RIA-064** Alertar sobre amostra insuficiente. **Implementado na Release 5 por supressão de grupos pequenos.**
- **RIA-065** Possibilitar auditoria da origem dos dados. **Implementado na Release 5 com relatório mensal e evidências por protocolo.**

## Conhecimento operacional e recuperação híbrida

- **RIA-066** Processar entidades internas somente por projetores registrados, determinísticos e versionados, com campos permitidos por allowlist. **Implementado para solicitações, encaminhamentos/respostas oficiais, minutas, tramitações, OCR/transcrições revisados, atas concluídas, fiscalizações concluídas e memórias temáticas por contrato e registry central.**
- **RIA-067** Emitir evento tenant-scoped sem conteúdo sensível e reler a entidade canônica dentro do contexto do tenant antes de projetá-la. **Implementado pelo contrato V2 do outbox, com módulo, entidade, ação e revisão; o worker continua relendo o aggregate pelo registry.**
- **RIA-068** Tratar criação, atualização, cancelamento, exclusão, anonimização e expiração, mantendo uma única versão vigente e purgando conteúdo derivado quando aplicável. **Implementado com versão anterior preservada durante atualização/falha e purge físico nas ações destrutivas.**
- **RIA-069** Aplicar minimização de PII, ACL, finalidade, base legal, retenção e detecção de prompt injection antes de gerar embeddings. **Implementado nas fontes atuais, incluindo quarentena antes de arquivo, chunks e embeddings.**
- **RIA-070** Marcar sincronizações esgotadas como erro, permitir reprocessamento e reconciliar periodicamente o RAG com o estado canônico. **Implementado com estado `ERRO`, dados de tentativa, endpoint de reprocessamento e scheduler de retenção.**
- **RIA-071** Rotear perguntas quantitativas ou transacionais para consultas estruturadas tenant-scoped e perguntas semânticas para recuperação documental. **Implementado com classificação determinística, composição híbrida e persistência do método, motivos, filtros e resultado estruturado.**
- **RIA-072** Aplicar filtros de tenant, ACL, módulo, entidade, tema, território, período, vigência e estado antes do ranking. **Implementado parcialmente para tenant, nível de acesso, vigência, estado operacional e retenção; os filtros explícitos de intenção permanecem planejados.**
- **RIA-073** Não forçar diversidade de escopo ou fonte abaixo do limiar e medir fontes desconexas, `precision@k`, `recall@k`, groundedness e precisão das citações por tenant. **Implementado com dataset tenant-scoped, execução por `k`, histórico de resultados e métricas de fontes desconexas e recusa.**

## Feedback e reaprendizado controlado

- **RIA-074** Preservar cada avaliação como revisão imutável tenant-scoped, com autor, consulta, fontes e versões originais, motivos normalizados e eventual resposta corrigida. **Implementado na captura confiável da Release 4.7.**
- **RIA-075** Tratar comentário e correção como conteúdo não confiável, aplicando minimização, limites, detecção de prompt injection, quarentena e moderação antes de qualquer uso. **Implementado na captura confiável da Release 4.7.**
- **RIA-076** Permitir julgamento por fonte, rota esperada, filtros esperados e expectativa de recusa para distinguir falhas de retrieval, roteamento e geração. **Implementado nas etapas 4.7.1 e 4.7.2.**
- **RIA-077** Compilar somente feedback aprovado em artefatos tenant-scoped, versionados, reproduzíveis e com proveniência até os sinais de origem. **Implementado na etapa 4.7.3.**
- **RIA-078** Impedir que ajustes derivados de feedback ultrapassem tenant, ACL, finalidade, jurisdição, vigência, estado ou limiar mínimo de evidência. **Implementado; o perfil atua somente após autorização e corte pelo limiar, sem recuperar fontes inelegíveis.**
- **RIA-079** Comparar candidato e baseline no dataset do tenant antes da ativação, registrar as métricas e suportar canário, revogação e rollback atômico. **Implementado na etapa 4.7.4.**
- **RIA-080** Não usar resposta corrigida como fonte factual ou citação; sua promoção limita-se a caso de avaliação ou exemplar aprovado, fundamentado e separado das evidências. **Implementado na compilação candidata; a resposta corrigida é marcada como não factual e não participa do retrieval.**
- **RIA-081** Promover explicitamente feedback aprovado para caso de avaliação, preservando fontes/versionamentos relevantes, hard negatives, rota, filtros, recusa, curador e proveniência tenant-scoped. **Implementado na Release 4.7.**
- **RIA-082** Desativar caso curado antes da execução quando o feedback for superado, revogado ou deixar de ser aprovado, ou quando uma fonte referenciada for eliminada ou ficar inacessível. **Implementado na Release 4.7.**
- **RIA-083** Manter dataset de regressão com consultas problemáticas reais por tenant, preservando expectativas e diagnóstico imutáveis, hard negatives originados da consulta e baseline minimizado sem resposta ou trechos brutos. **Implementado no incremento 4.8.1.**
- **RIA-084** Recuperar candidatos documentais por FTS e similaridade `pgvector`, comparar somente modelo e dimensão compatíveis, fundir canais por RRF e manter fallback FTS quando o embedding estiver indisponível. **Implementado no incremento 4.8.2.**
- **RIA-085** Reordenar e vetar por relevância neural apenas o pool híbrido já autorizado e acima do limiar, usando conteúdo sanitizado, contrato estruturado com conjunto exato de IDs e fallback que preserve a ordem base. **Implementado no incremento 4.8.3.**
- **RIA-086** Expor pontuação base e neural, modelo, versão do prompt, justificativa e fallback do reranking sem alterar o score de evidência ou permitir a introdução de fontes. **Implementado no incremento 4.8.3.**
- **RIA-087** Identificar intenção documental, tema, tipo, referência normativa e período, preservando a consulta original e sem permitir que inferências alterem tenant, ACL, retenção, vigência obrigatória ou publicação. **Implementado no incremento 4.8.4.**
- **RIA-088** Executar expansões controladas nos canais FTS e `pgvector`, fundir os pools por RRF e aplicar filtros documentais antes do ranking e do reranker neural. **Implementado no incremento 4.8.4.**
- **RIA-089** Auditar entendimento, expansões, filtros, motivos e quantidade de consultas, incluindo métricas operacionais e avaliação pelo dataset tenant-scoped. **Implementado no incremento 4.8.4.**
- **RIA-090** Gerar resposta substantiva exclusivamente a partir de chunks autorizados, sanitizados e aprovados pelo retrieval, exigindo contrato estruturado com afirmações e IDs de fontes. **Implementado no incremento 4.8.5.**
- **RIA-091** Validar cada afirmação contra os chunks citados, rejeitar fontes desconhecidas ou afirmações sem suporte e recusar conclusivamente em qualquer falha, sem usar texto genérico como resposta fundamentada. **Implementado no incremento 4.8.5.**
- **RIA-092** Expor e auditar modelo, versão do prompt, afirmações, citações, validação cruzada e fallback, medindo precisão sobre as fontes efetivamente citadas. **Implementado no incremento 4.8.5.**

## Avaliação

Métricas mínimas:
- precisão e recall de classificação;
- taxa de aceitação de sugestões;
- groundedness das respostas;
- precisão das citações;
- taxa de alucinação;
- tempo de resposta;
- custo por execução;
- taxa de intervenção humana;
- desempenho por categoria e canal;
- testes de viés e privacidade.
