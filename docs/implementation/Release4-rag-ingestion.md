# Release 4 - Gestão e ingestão da base RAG

## Escopo entregue

- RF-093: gestão tenant-safe de documentos e versões;
- RIA-040: extração, chunking e embeddings locais;
- RIA-041: filtro por tenant e nível de acesso já aplicado nas APIs;
- RIA-042 e RIA-043: chunks preservam página; versões expõem origem e vigência;
- RIA-044: estados `RASCUNHO`, `VIGENTE`, `HISTORICO` e `REVOGADO`.

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

Os vetores são armazenados em JSON nesta fatia para manter os testes SQLite e a portabilidade. A próxima fatia introduzirá a busca híbrida e poderá materializar o mesmo conteúdo em `pgvector` sem repetir a extração.
