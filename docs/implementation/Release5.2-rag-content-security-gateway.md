# Release 5.2 — Gateway unificado e estado de segurança

## Resultado

O GabFlow possui um único contrato de avaliação de conteúdo para uploads privados,
catálogo global, projeções dos demais módulos, feedback e conteúdo recuperado. A
consulta do usuário também é avaliada e registrada na telemetria da resposta.

O gateway retorna somente estados fechados:

- `CLEAN / ALLOW`;
- `SUSPICIOUS / QUARANTINE`;
- `MALICIOUS / BLOCK`;
- `INDETERMINATE / RETRY`.

Falha interna nunca resulta em aprovação implícita. Sinais são identificadores
estáveis, e logs/API não repetem o payload potencialmente malicioso.

## Persistência

O mesmo conjunto de campos foi adicionado a:

- `rag_document_versions`;
- `rag_global.document_versions`;
- `rag_knowledge_sources`;
- `rag_query_feedback`.

O estado inclui score, categorias, sinais, versões da política/detector/classificador,
checksum, instante de varredura e código de erro. Registros preexistentes recebem
`INDETERMINATE / RETRY / legacy-unassessed` para exigir reavaliação explícita.

## Cobertura por superfície

- uploads privados e globais: texto extraído e metadados relevantes;
- OCR e transcrição revisados: passam pelo gateway ao entrar pela projeção
  operacional;
- demais módulos e conectores: conteúdo canônico do registry de projetores;
- feedback: comentário, resposta corrigida e filtros esperados;
- retrieval: sequência de chunks e cada sentença usada no contexto;
- consulta: entrada do usuário, sem bloquear a recuperação neste incremento.

## Compatibilidade e limite do incremento

A detecção determinística existente passou a ser uma implementação do gateway,
preservando a compatibilidade de `has_prompt_injection`. O classificador dedicado,
variações ofuscadas e combinação de sinais pertencem ao incremento 5.4.

No marco do 5.2, a decisão era apenas registrada em uploads privados/globais. O
enforcement com quarentena e purge dos derivados foi entregue posteriormente no
incremento 5.3. Projeções operacionais e feedback permanecem fail-closed.

## Configuração

- `RAG_CONTENT_SECURITY_POLICY_VERSION=rag-content-security-v1`
- `RAG_CONTENT_SECURITY_DETECTOR_VERSION=deterministic-v1`

## Evidências de aceite

- contrato unitário para decisões suspeita, limpa e indeterminada;
- persistência e serialização nas quatro entidades de ciclo de vida;
- regressão de upload privado/global, memória operacional e feedback;
- migração PostgreSQL com constraints de status, ação e score;
- dataset adversarial 5.1 preservado como gate de regressão.
