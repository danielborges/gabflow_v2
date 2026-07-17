# P2 - IA de Triagem

## Fatias entregues

| Spec | Implementação |
| --- | --- |
| RIA-001 | Sugestão de categoria e subcategoria a partir do relato |
| RIA-002 | Sugestão de prioridade, impacto e urgência |
| RIA-006 | Detecção de possível emergência com orientação para atendimento competente |
| RIA-003 | Extração estruturada de endereço, bairro, datas, pessoas, protocolos e serviços |
| RIA-004 | Sugestão restrita aos órgãos ativos cadastrados pelo tenant |
| RIA-005 | Sinalização de linguagem potencialmente ofensiva sem bloquear o relato |
| RIA-007 | Resumo estruturado com situação, local, afetados e informações ausentes |
| RIA-008 | Detecção de possíveis duplicidades por similaridade semântica, temporal e geográfica |
| RIA-009 | Transcrição local assíncrona de áudio com preservação do original e revisão humana |
| RIA-010 | OCR local assíncrono de imagens e PDFs com confiança por página e revisão humana |
| RIA-020 | Resposta ao cidadão sugerida em canal e tom configuráveis, com edição humana |
| RIA-021 | Resumo do histórico antes do atendimento |
| RIA-022 | Perguntas faltantes sugeridas sem inventar fatos |
| RIA-023 | Documentos possivelmente úteis, sempre apresentados para confirmação |
| RIA-024 | Próximos passos com ordem, responsável e justificativa |
| RIA-025 | Proibição de envio sem ação explícita do usuário |
| ADR-002 | Execução assíncrona pelo outbox e worker PostgreSQL |
| ADR-004 | Aceite, edição ou rejeição humana antes de alterar a solicitação |

## Controles de governança

- execução registra tenant, caso de uso, modelo, versão do prompt e hash da entrada;
- resultado registra confiança, latência, custo estimado e saída estruturada;
- falhas do provedor usam as retentativas e o dead-letter do worker;
- todas as novas solicitações disparam a triagem e a análise de duplicidade após o cadastro;
- a solicitação continua disponível para classificação manual quando a IA falha;
- sugestões nunca alteram categoria, prioridade, impacto ou urgência sem revisão humana;
- decisões de aceite, edição ou rejeição geram histórico e auditoria;
- candidatos a duplicidade nunca são agrupados sem confirmação humana e nenhum relato é apagado;
- possível emergência é apenas destacada e não substitui serviços de emergência.
- o áudio original permanece imutável; aceite, correção, rejeição e reprocessamento da transcrição são auditados.
- imagens e PDFs originais permanecem imutáveis; confiança, revisão e reprocessamento do OCR são auditados.
- a assistência de atendimento é iniciada manualmente e processada pelo outbox/worker;
- o servidor força `envioAutomatico: false` e `revisaoHumanaObrigatoria: true` no resultado;
- usar uma sugestão apenas transfere o texto ao formulário; o endpoint de envio não é chamado;
- edições e rejeições da assistência geram histórico e auditoria por tenant.

## Provedor local

O provider principal é o Ollama, executado na rede privada do Docker Compose com o modelo
`qwen2.5:3b`. O serviço `ollama-init` baixa o modelo uma vez e o mantém no volume
`ollama_data`, sem custo por requisição e sem enviar relatos para terceiros.

A detecção de duplicidade usa embeddings do modelo local `nomic-embed-text`. A pontuação
combina similaridade semântica (75%), proximidade temporal (15%) e, quando existem
coordenadas em ambos os relatos, proximidade geográfica (10%). A busca é limitada ao
tenant e à janela configurada; apenas os candidatos acima do limiar são apresentados.
Se o modelo estiver indisponível, o fallback local por tokens mantém a triagem operacional
e registra essa condição no resultado.

A transcrição usa `faster-whisper` com o modelo multilíngue `base`, execução CPU `int8` e
idioma português configurável. O modelo é baixado pelo `whisper-init` para um volume
persistente e o worker processa o áudio sem enviá-lo a serviços externos. Arquivos de até
15 minutos são transcritos em segmentos; o texto gerado permanece separado da versão
revisada e do arquivo original.

O OCR usa Tesseract local com o pacote de idioma português. Imagens PNG/JPEG e PDFs de até
25 páginas são processados pelo worker; PDFs são renderizados localmente e nenhuma página é
enviada a terceiros. O resultado registra confiança média e confiança por página, mantendo o
texto extraído separado da versão revisada e do documento original.

A resposta é limitada por JSON Schema, validada novamente pelo backend e executada com
temperatura zero. IDs de categoria que não pertençam ao tenant são rejeitados.

O classificador determinístico `gabflow-triage-rules-v1` permanece como fallback
configurável. Quando utilizado, a execução registra `LOCAL_FALLBACK`, o erro do Ollama e
`fallbackUtilizado: true`. Desabilitar `AI_TRIAGE_FALLBACK_ENABLED` faz com que falhas
sigam as retentativas e o dead-letter do worker.

A assistência usa o mesmo Ollama local com JSON Schema e temperatura zero. O fallback
`gabflow-assistance-rules-v1` mantém o fluxo disponível sem rede e gera sugestões
conservadoras. O modelo recebe apenas o contexto necessário da solicitação e nunca recebe
credenciais ou destinos de contato. A geração não aciona o endpoint de respostas, que
continua sendo a única operação capaz de registrar e eventualmente enviar uma saída.

Perguntas, documentos, próximos passos e a resposta sugerida passam por regras locais
conservadoras depois da inferência. Esses guardrails impedem a inclusão de fatos não
presentes no contexto, não tratam documentos sugeridos como obrigatórios e exigem revisão
humana. O resultado registra `guardrailsAplicados`, `revisaoHumanaObrigatoria: true` e
`envioAutomatico: false` para que a restrição também seja verificável por API e auditoria.

## Avaliação de qualidade

O endpoint `GET /api/v1/ia/qualidade-triagem` e a visão **Qualidade da IA** consolidam,
por tenant e período, taxa de conclusão, confiança, latência, aceitação, intervenção
humana, fallback, concordância de categoria, cobertura de entidades, órgãos sugeridos e
análises de possíveis duplicidades.
As métricas são tratadas como amostra inicial até acumularem 30 revisões humanas.

Configurações:

```dotenv
AI_TRIAGE_PROVIDER=ollama
AI_TRIAGE_MODEL=qwen2.5:3b
AI_TRIAGE_FALLBACK_MODEL=gabflow-triage-rules-v1
AI_TRIAGE_PROMPT_VERSION=triage-v3
AI_TRIAGE_TIMEOUT_SECONDS=120
AI_TRIAGE_FALLBACK_ENABLED=true
AI_ASSISTANCE_PROVIDER=ollama
AI_ASSISTANCE_MODEL=qwen2.5:3b
AI_ASSISTANCE_FALLBACK_MODEL=gabflow-assistance-rules-v1
AI_ASSISTANCE_PROMPT_VERSION=assistance-v1
AI_ASSISTANCE_TIMEOUT_SECONDS=120
AI_ASSISTANCE_FALLBACK_ENABLED=true
AI_DUPLICATE_PROVIDER=ollama
AI_EMBEDDING_MODEL=nomic-embed-text
AI_DUPLICATE_WINDOW_DAYS=180
AI_DUPLICATE_SCORE_THRESHOLD=0.72
AI_DUPLICATE_MAX_SUGGESTIONS=5
AI_DUPLICATE_CANDIDATE_LIMIT=100
AUDIO_TRANSCRIPTION_PROVIDER=faster-whisper
AUDIO_TRANSCRIPTION_MODEL=base
AUDIO_TRANSCRIPTION_DEVICE=cpu
AUDIO_TRANSCRIPTION_COMPUTE_TYPE=int8
AUDIO_TRANSCRIPTION_LANGUAGE=pt
AUDIO_TRANSCRIPTION_CACHE_DIR=/models/whisper
AUDIO_TRANSCRIPTION_MAX_DURATION_SECONDS=900
DOCUMENT_OCR_PROVIDER=tesseract
DOCUMENT_OCR_MODEL=tesseract-5
DOCUMENT_OCR_LANGUAGE=por
DOCUMENT_OCR_MAX_PAGES=25
DOCUMENT_OCR_MAX_PIXELS=25000000
OLLAMA_BASE_URL=http://ollama:11434
```
