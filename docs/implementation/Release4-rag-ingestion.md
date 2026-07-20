# Release 4 - Gestão e ingestão da base RAG

## Escopo entregue

- RF-093: gestão tenant-safe de documentos e versões;
- RIA-040: extração, chunking e embeddings locais;
- RIA-041: filtro por tenant e nível de acesso já aplicado nas APIs e na consulta RAG;
- RIA-042 e RIA-043: chunks preservam página; versões expõem origem e vigência; a consulta retorna citações por documento, versão e página;
- RIA-044: estados `RASCUNHO`, `VIGENTE`, `HISTORICO` e `REVOGADO`;
- RIA-045: o assistente recusa resposta conclusiva quando a melhor evidência fica abaixo do limiar configurado.

## Pipeline

1. O gestor envia PDF, DOCX, TXT, PNG ou JPEG com metadados.
2. A API valida tipo, tamanho, malware conhecido, URL, vigência e unicidade.
3. Arquivo e checksum são preservados em volume separado por tenant.
4. O outbox agenda `IngestaoDocumentoRag` com retentativas.
5. TXT e DOCX usam extração nativa; PDF e imagem reutilizam o OCR local.
6. O texto é dividido por página com tamanho e sobreposição configuráveis.
7. O Ollama gera embeddings em lote com `nomic-embed-text`.
8. Chunks, páginas, checksums, vetores e modelo são persistidos.
9. O gestor publica uma versão indexada; a vigente anterior torna-se histórica.

Os vetores são armazenados em JSON nesta fatia para manter os testes SQLite e a portabilidade. A busca híbrida já combina similaridade vetorial e lexical sobre os chunks vigentes. Uma evolução futura poderá materializar o mesmo conteúdo em `pgvector` sem repetir a extração.

## Consulta assistida

1. `POST /api/v1/assistente/consultas` recebe `consulta` e `limite`.
2. A recuperação considera apenas documentos ativos, indexados, vigentes, dentro da vigência e acessíveis ao papel do usuário.
3. O score híbrido combina embedding local/Ollama e similaridade lexical.
4. Se a melhor fonte não atingir `RAG_RETRIEVAL_MIN_EVIDENCE_SCORE`, a resposta é recusada como não conclusiva.
5. A consulta, resposta, fontes, modelo usado, fallback e decisão de evidência são persistidos em `rag_assistant_queries`.
6. A auditoria registra hash da consulta e referências recuperadas.

## Segurança e revisão humana

1. Cada fonte recuperada é avaliada contra padrões de prompt injection.
2. Instruções encontradas dentro das fontes são tratadas apenas como dados, nunca como comando do sistema.
3. Trechos suspeitos são sanitizados antes de aparecerem na resposta da API.
4. O retorno informa `promptInjectionDetectado`, fontes com risco, instruções ignoradas e a política aplicada.
5. `PATCH /api/v1/assistente/consultas/{consultaId}/avaliacao` registra avaliação `POSITIVA`, `NEGATIVA` ou `CORRIGIDA`.
6. Correções humanas preservam comentário, resposta corrigida, revisor e data de revisão para auditoria e melhoria futura.
