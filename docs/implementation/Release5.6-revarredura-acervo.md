# Release 5.6 — Revarredura do acervo e purge dos derivados

## Resultado

Administradores do gabinete podem iniciar uma revarredura do acervo privado e dos
anexos. O curador global possui a operação equivalente para o catálogo compartilhado.
Cada execução congela um corte temporal, registra a política vigente e processa o
acervo em lotes com cursor persistente. Uma segunda execução concorrente no mesmo
escopo é rejeitada.

No início, os alvos do corte são marcados como inconclusivos. Dessa forma, versões
ainda não reavaliadas deixam imediatamente de participar de publicação, distribuição
e retrieval. A execução revalida checksum, MIME, ClamAV e conteúdo pelo gateway de
prompt injection; documentos limpos são reindexados e voltam a ficar elegíveis.

## Quarentena e purge

Malware, adulteração ou decisão de conteúdo diferente de `CLEAN` mantém o objeto
original isolado para investigação, mas elimina fisicamente os derivados:

- chunks e embeddings privados ou globais;
- texto extraído, páginas, modelo e instante de indexação;
- OCR e texto revisado derivados do anexo;
- transcrição, revisão e segmentos derivados do áudio;
- memória operacional projetada a partir do OCR ou da transcrição.

A execução preserva auditoria mínima e contabiliza alvos limpos, em quarentena,
erros, chunks, OCRs e transcrições eliminados.

## Operação

- `POST /api/v1/rag/seguranca/revarreduras` inicia o escopo do tenant.
- `GET /api/v1/rag/seguranca/revarreduras` lista progresso e histórico.
- `POST /api/v1/platform/rag-global/seguranca/revarreduras` inicia o catálogo global.
- `GET /api/v1/platform/rag-global/seguranca/revarreduras` acompanha o catálogo.

Falha temporária do scanner aborta a transação do lote e usa o retry exponencial do
outbox. Após esgotar tentativas, a execução fica em `ERRO` sem promover implicitamente
nenhum alvo pendente.
