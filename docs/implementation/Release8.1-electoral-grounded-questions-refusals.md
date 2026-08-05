# Release 8.1 — Perguntas fundamentadas e recusas

Data de estabilização: 2026-08-04.

## Escopo entregue

- perguntas em linguagem natural sobre uma a cinco candidaturas da mesma eleição;
- composição de resultados eleitorais oficiais com documentos autorizados pelo RAG;
- política de recusa para voto individual, intenção ou previsão, atributos sensíveis,
  causalidade sem evidência, pequenos grupos e prompt injection;
- recusa síncrona antes do outbox;
- armazenamento minimizado de prompt bloqueado: hash, tamanho, categoria, sinais e versões;
- validação automática de citações, números, fórmulas e linguagem causal;
- recusa de saída quando a validação não fecha;
- fila de revisão parlamentar com aprovação, rejeição ou restauração;
- decisão auditada com justificativa, responsável, data, versão do modelo e hash dos fatos;
- dataset adversarial eleitoral versionado;
- interface para perguntar, entender recusas e revisar resultados.

## Política de evidência

Afirmações eleitorais citam URL, hash e versão do dataset, além dos filtros usados. Uma
afirmação documental só é incorporada quando a geração fundamentada e suas citações são
validadas pelo RAG. A ausência de evidência documental é declarada como limitação e não
impede a apresentação dos fatos eleitorais oficiais reproduzíveis.

## Minimização e privacidade

Prompts recusados não entram na fila e seu texto não é gravado em `request_payload`,
auditoria ou snapshot. Perguntas permitidas são persistidas para reprodução e revisão do
job, mas não são copiadas para citações ou snapshots quantitativos.

## Homologação executada

- 34 testes eleitorais de backend aprovados;
- pergunta segura, cinco famílias de recusa, documento RAG e decisão humana cobertos;
- dataset adversarial com 23 casos, incluindo seis controles benignos;
- 9 testes reais de migration PostgreSQL/PostGIS aprovados, com downgrade/reapply;
- 63 testes de frontend, lint e build aprovados;
- suíte global sem regressão atribuível à release; o teste RAG intermitente de desempate
  falhou na execução conjunta e passou na repetição isolada.
