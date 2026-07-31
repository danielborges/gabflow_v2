# Release 5.8 — Criptografia por tenant e auditoria RLS

Uploads de anexos e documentos RAG são verificados antes da gravação e cifrados
com AES-256-GCM. A derivação inclui o tenant (ou o escopo global), versão da chave e
AAD autenticado. Downloads, OCR, transcrição, antivírus e parsing decifram somente
no processo autorizado e removem o temporário ao concluir.

Objetos anteriores continuam legíveis durante a transição. Depois de elevar
`STORAGE_ENCRYPTION_KEY_VERSION`, a revarredura de segurança recifra somente itens
classificados como limpos, atualizando os metadados de rotação.

A auditoria RLS é solicitada por administrador de plataforma, executada via outbox
e persiste achados sem conteúdo de tenant. Ela verifica RLS/`FORCE RLS`, expressão da
política, isolamento observado e atributos das roles de API/worker.

Endpoints:

- `POST /api/v1/platform/seguranca/auditorias-rls`;
- `GET /api/v1/platform/seguranca/auditorias-rls`;
- `GET /api/v1/platform/seguranca/auditorias-rls/{id}`.
