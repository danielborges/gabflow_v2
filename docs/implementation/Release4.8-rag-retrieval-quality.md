# Release 4.8 — Qualidade de retrieval e resposta fundamentada

## Objetivo

Eliminar fontes desconexas e tornar cada evolução de retrieval mensurável antes
de chegar aos usuários. A sequência prevista é:

1. dataset de regressão com perguntas problemáticas;
2. recuperação híbrida com FTS e `pgvector`;
3. reranking neural;
4. classificação de intenção, expansão e filtros temáticos;
5. geração real da resposta com validação cruzada das citações.

## Incremento 4.8.1 — Dataset de regressão

Status: implementado.

O endpoint `POST /api/v1/assistente/avaliacoes/casos-regressao` converte uma
consulta já registrada em caso de avaliação do mesmo tenant. O gestor informa:

- motivos normalizados e severidade;
- tags para segmentação;
- fontes esperadas;
- fontes irrelevantes que apareceram no resultado original;
- expectativa de recusa, rota e filtros, quando aplicáveis.

A operação é idempotente por `tenant_id + consulta_id`. A pergunta, o vínculo
com a consulta, as expectativas e o baseline ficam imutáveis; somente observação
e desativação administrativa podem ser alteradas.

O snapshot do baseline contém hashes, identificadores de documentos, versões e
chunks, scores, modelo de embedding, método, filtros e flags operacionais. Ele
não duplica a resposta, comentários ou trechos das fontes.

Os casos passam imediatamente a participar do executor existente, que mede
`precision@k`, `recall@k`, fontes desconexas, groundedness, precisão de citações,
recusa, hard negatives, rota e filtros.

## Critérios de segurança

- a consulta de origem deve pertencer ao tenant autenticado;
- fontes privadas esperadas devem pertencer ao tenant e estar ativas;
- fontes globais esperadas devem estar disponíveis ao tenant;
- hard negatives devem constar na consulta original;
- referências não podem ser simultaneamente esperadas e irrelevantes;
- o mesmo caso não pode ser duplicado por repetição ou concorrência.

## Incremento 4.8.2 — Recuperação híbrida FTS + pgvector

Status: implementado.

Os chunks privados e globais passam a possuir:

- `search_vector` gerado com configuração portuguesa e índice GIN;
- `embedding_vector` nativo, sincronizado do JSON legado por trigger;
- índices HNSW de distância cosseno para 128 e 768 dimensões.

Cada consulta forma dois rankings independentes no PostgreSQL. O canal FTS
recupera correspondência textual e continua disponível quando o provedor de
embedding falha. O canal `pgvector` considera somente linhas com o mesmo modelo
e dimensão da consulta. As listas são fundidas por Reciprocal Rank Fusion antes
do score final, do limite por documento e da deduplicação por checksum.

Tenant, ACL privada, vigência, retenção, estado de ingestão e publicação do
catálogo global são aplicados dentro das queries de candidatura. O retorno
expõe os canais, a pontuação de fusão e o ranking textual para auditoria.

SQLite e ambientes sem a extensão preservam o caminho local usado pelos testes
e pelo desenvolvimento, sem alterar a semântica de fallback.

## Incremento 4.8.3 — Reranking neural

Status: implementado.

O pool elegível produzido pelo FTS + `pgvector` é ordenado inicialmente pelos
sinais híbridos e, em seguida, os primeiros candidatos são comparados de forma
listwise por um modelo neural. A nota final combina a pontuação base e a
relevância neural com peso configurável. O score de evidência não é alterado.
Candidatos abaixo do limiar neural são vetados; candidatos fora da janela
avaliada não podem substituí-los. Se nenhum candidato permanecer, a resposta é
recusada. O gate também avalia pools com um único candidato.

O reranker não consulta o banco nem recebe liberdade para selecionar fontes:
tenant, ACL, vigência, retenção, publicação, sanitização e limiar mínimo já foram
aplicados. A resposta estruturada deve conter exatamente uma avaliação por ID
opaco conhecido, sem duplicatas, com nota finita entre 0 e 1 e justificativa.
Qualquer violação, timeout ou indisponibilidade preserva integralmente o ranking
híbrido.

Os trechos enviados são sanitizados e limitados em tamanho, declarados no prompt
como dados não confiáveis. A consulta expõe pontuação base, nota neural, modelo,
versão do prompt, justificativa, quantidade avaliada e eventual fallback. As
métricas operacionais contabilizam aplicação e fallback do reranker.

O tamanho da janela, o peso de combinação, o limiar neural, o modelo e o timeout
são configuráveis por ambiente.

## Incremento 4.8.4 — Entendimento, expansão e filtros temáticos

Status: implementado.

Antes da recuperação, a consulta documental passa por um analisador
determinístico e auditável que identifica intenção documental, tema, tipo de
documento, referência normativa e período. Filtros explícitos podem acrescentar
órgão e jurisdição. Valores inferidos ou informados nunca alteram tenant, ACL,
vigência obrigatória, retenção ou publicação.

A consulta original é preservada e pode originar até três expansões controladas
com vocabulário legislativo e temático. Cada consulta participa separadamente do
FTS e do `pgvector`; os pools são novamente fundidos por RRF antes do score de
evidência e do reranker neural. Filtros documentais são aplicados dentro do SQL
PostgreSQL e também no caminho local.

O retorno e a auditoria registram intenção, temas, tipos, referências, consulta
original, expansões, filtros, motivos, quantidade de buscas e canais de
candidatura. As métricas operacionais contabilizam consultas com expansão e com
filtros documentais.

## Incremento 4.8.5 — Geração substantiva e validação de citações

Status: implementado.

Depois dos filtros, limiares e reranking, somente os melhores chunks autorizados
e sanitizados formam o contexto do gerador. O modelo recebe IDs opacos e um
contrato JSON fechado: cada afirmação deve ser autocontida e indicar de uma a
três fontes pertencentes ao contexto. Instruções presentes nos documentos são
tratadas como dados não confiáveis e não podem alterar a política do sistema.

A aplicação valida o retorno antes de exibi-lo: rejeita JSON inválido, IDs
desconhecidos ou repetidos, afirmações sem citação, conteúdo suspeito e
afirmações sem suporte lexical mínimo nos chunks citados. Só então numera as
citações e compõe a resposta substantiva. Falha, indisponibilidade ou rejeição
da validação resultam em recusa conclusiva segura, mantendo as fontes
recuperadas visíveis para inspeção, sem voltar ao antigo texto genérico.

O retorno e a auditoria registram modelo, versão do prompt, aplicação, fallback,
erro minimizado, quantidade de afirmações e o resultado da validação cruzada.
Cada citação aponta para chunk, documento, versão, escopo e afirmações que
sustenta. As métricas contabilizam respostas geradas, fallback e rejeições da
validação; a precisão de citações do dataset passa a considerar os documentos
efetivamente citados, e não todo o pool recuperado.

## Estado da release

Os cinco incrementos planejados para a Release 4.8 estão implementados. A
próxima etapa operacional é calibrar limiares e modelos com o dataset real de
cada tenant antes de ampliar o canário.
