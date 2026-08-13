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
- **RIA-047** Avaliar risco de prompt injection nos documentos antes da indexação e novamente antes da composição do contexto. **Implementado: gateway pré-indexação, quarentena/purge em todas as fontes RAG e nova avaliação no retrieval.**
- **RIA-048** Não executar instruções encontradas dentro das fontes. **Implementado parcialmente com política explícita, contexto restrito e sanitização; os controles independentes de entrada e saída permanecem planejados nos incrementos 5.2 a 5.7.**
- **RIA-049** Permitir avaliação positiva, negativa e correção pelo usuário. **Implementado no endpoint de avaliação de consultas RAG.**

## RAG hierárquico e aprendizado controlado

- **RIA-050** Manter catálogo global versionado separado das bases privadas dos tenants. **Implementado no schema `rag_global`, com coleções, documentos, versões, chunks e ciclo de publicação auditável.**
- **RIA-051** Compor o contexto efetivo com fontes globais autorizadas e fontes privadas do tenant, sem copiar o catálogo global por padrão. **Implementado com recuperação separada, deduplicação e reranking conjunto.**
- **RIA-052** Aplicar políticas globais obrigatória, padrão, opcional, direcionada, restrita por jurisdição e privada da plataforma. **Implementado com concessões tenant-scoped, vigência e filtros jurisdicionais.**
- **RIA-053** Permitir atualização automática, fixação de versão e fork privado de fonte global com proveniência preservada. **Implementado parcialmente: atualização automática e fixação estão disponíveis; fork privado permanece planejado.**
- **RIA-054** Diferenciar escopo global e privado em toda citação, auditoria e explicação de ranking. **Implementado com escopo, origem, coleção, versão, checksums, proveniência e scores.**
- **RIA-055** Ingerir automaticamente toda informação interna elegível dos módulos no RAG Privado, preservando finalidade, base legal, nível de acesso, retenção e entidade de origem. **Implementado para solicitações, interações, encaminhamentos/respostas oficiais, minutas, tramitações, fontes normativas, OCR/transcrições revisados, atas concluídas, fiscalizações concluídas e memórias temáticas; novos módulos exigem projetor registrado.**
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

- **RIA-066** Processar entidades internas somente por projetores registrados, determinísticos e versionados, com campos permitidos por allowlist. **Implementado para solicitações, encaminhamentos/respostas oficiais, minutas, tramitações, fontes normativas, OCR/transcrições revisados, atas concluídas, fiscalizações concluídas e memórias temáticas por contrato e registry central.**
- **RIA-067** Emitir evento tenant-scoped sem conteúdo sensível e reler a entidade canônica dentro do contexto do tenant antes de projetá-la. **Implementado pelo contrato V2 do outbox, com módulo, entidade, ação e revisão; o worker continua relendo o aggregate pelo registry.**
- **RIA-068** Tratar criação, atualização, cancelamento, exclusão, anonimização e expiração, mantendo uma única versão vigente e purgando conteúdo derivado quando aplicável. **Implementado com versão anterior preservada durante atualização/falha e purge físico nas ações destrutivas.**
- **RIA-069** Aplicar minimização de PII, ACL, finalidade, base legal, retenção e detecção de prompt injection antes de gerar embeddings. **Implementado para projeções operacionais, uploads privados/globais, OCR/transcrição revisados e conectores registrados.**
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
- **RIA-093** Verificar semanticamente se cada afirmação é integralmente sustentada pelos chunks citados, considerando contradições, negações, sujeitos, datas, números e modalidade normativa. **Implementado no incremento 4.9.1.**
- **RIA-094** Manter a validação determinística e lexical como requisito anterior ao entailment e recusar a resposta quando o verificador obrigatório estiver indisponível ou abaixo do limiar. **Implementado com política fail-closed configurável no incremento 4.9.1.**
- **RIA-095** Avaliar perfis candidatos de thresholds no mesmo dataset e tenant do baseline, bloqueando regressões além da tolerância antes da ativação. **Implementado no incremento 4.9.1.**
- **RIA-096** Aplicar perfis de qualidade em canário determinístico, medir fallback e rejeição semântica e executar rollback quando os gates online forem violados. **Implementado no incremento 4.9.1.**
- **RIA-097** Iniciar automaticamente o perfil aprovado em etapas progressivas tenant-scoped, exigindo janela e amostra mínimas antes de cada expansão. **Implementado no incremento 4.9.2.**
- **RIA-098** Manter o baseline anterior atendendo o tráfego fora do bucket durante todo o canário e registrar métricas e decisão por etapa. **Implementado no incremento 4.9.2.**
- **RIA-099** Promover automaticamente após a validação de 100% e executar rollback atômico quando houver regressão de fallback, rejeição semântica, recusa ou feedback negativo. **Implementado no incremento 4.9.2.**
- **RIA-100** Renovar o lease de avaliações longas e expor administrativamente etapa, histórico, próxima avaliação e motivo da promoção ou rollback. **Implementado no incremento 4.9.2.**
- **RIA-101** Executar a validação semântica em provider e modelo NLI independentes do gerador, recusando configuração que reutilize o mesmo modelo quando a separação for obrigatória. **Implementado no incremento 4.9.3.**
- **RIA-102** Suportar classificador NLI dedicado por contrato fechado de premissa, hipótese, rótulo e confiança. **Implementado no incremento 4.9.3.**
- **RIA-103** Reduzir o caminho crítico por reranking adaptativo e limites de fontes, contexto, afirmações e tokens, preservando os gates existentes. **Implementado no incremento 4.9.3.**
- **RIA-104** Medir latência por etapa e bloquear rollout cuja taxa de estouro do orçamento exceda o limite tenant-scoped. **Implementado no incremento 4.9.3.**

## Segurança de conteúdo e prompt injection

- **RIA-105** Manter threat model versionado com ativos, atores, fronteiras de confiança, vetores diretos, indiretos, ofuscados, multimodais e persistentes, além de invariantes de falha fechada. **Especificado no incremento 5.1.**
- **RIA-106** Manter dataset adversarial versionado, separado do RAG factual, com ataques multilíngues, codificados, distribuídos entre chunks e controles benignos para medir falsos positivos. **Especificado e populado inicialmente no incremento 5.1.**
- **RIA-107** Submeter upload, catálogo global, projeção operacional, OCR, transcrição, feedback e conteúdo de conector a um gateway unificado antes de chunks e embeddings. **Implementado nos incrementos 5.2 e 5.3.**
- **RIA-108** Produzir decisão fechada `CLEAN`, `SUSPICIOUS`, `MALICIOUS` ou `INDETERMINATE`, com ação validada, score, categorias, sinais, política, detector e classificador versionados. **Implementado no incremento 5.2.**
- **RIA-109** Impedir chunks, embeddings, publicação e recuperação para qualquer decisão diferente de `CLEAN`; indisponibilidade de controle obrigatório deve resultar em retry sem aprovação implícita. **Implementado no incremento 5.3 com purge imediato e filtros de defesa em profundidade.**
- **RIA-110** Combinar canonicalização limitada, detector determinístico multilíngue e classificador dedicado independente do gerador, preservando revisão humana para conteúdo suspeito. **Implementado no incremento 5.4 com canonicalização defensiva limitada, contrato fechado de classificação, modelo independente, falha fechada e dataset adversarial executável.**
- **RIA-111** Revalidar a saída do modelo contra prompt leakage, segredos, destinos externos, ações não autorizadas e contrato de citações antes de retorná-la ou encaminhá-la a outra capacidade. **Implementado no incremento 5.7 com decisão fechada, bloqueio crítico fail-closed, métricas e rollout tenant-scoped com promoção/rollback.**
- **RIA-112** Verificar uploads com antimalware real antes do armazenamento e novamente antes do parsing, validar o MIME real e executar parsers de conteúdo não confiável sem rede, segredos, escrita ou capabilities. **Implementado no incremento 5.5 com ClamAV/INSTREAM, checksum, sidecar isolado e limites de CPU, memória, processos, arquivo, saída e timeout.**
- **RIA-113** Revarrer versões privadas, catálogo global e anexos após mudança de política ou assinaturas, invalidando preventivamente o retrieval e purgando chunks, embeddings, OCR, transcrições e memórias operacionais derivados de conteúdo reclassificado. **Implementado no incremento 5.6 com execução assíncrona, corte estável, lotes retomáveis, cursor, RLS, auditoria e contadores de purge.**
- **RIA-114** Cifrar documentos privados e anexos em repouso com chave autenticada derivada por tenant e versionada; auditar automaticamente RLS forçado, políticas de tenant e roles de runtime sem bypass. **Implementado no incremento 5.8 com AES-256-GCM, rotação pela revarredura e auditoria assíncrona via outbox.**

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
