# Release 4.2 — Catálogo RAG Geral

## Escopo entregue

Esta entrega implementa os passos 8–11 do plano do RAG hierárquico:

8. criar o domínio de persistência `rag_global`;
9. separar a curadoria global por papel de autorização próprio;
10. ingerir documentos globais com versões imutáveis e proveniência;
11. governar publicação, substituição, suspensão e revogação com auditoria.

Distribuição para tenants, recuperação federada, conectores externos e fork privado
permanecem fora deste recorte.

## Persistência

O schema PostgreSQL `rag_global` contém:

- `collections`;
- `documents`;
- `document_versions`;
- `chunks`.

As tabelas não possuem `tenant_id`: elas pertencem à plataforma, não a um gabinete.
O conteúdo privado existente permanece no domínio protegido por tenant. A outbox
aceita eventos sem tenant exclusivamente para aggregates globais; eventos privados
continuam exigindo e ativando o contexto transacional do gabinete.

## Autorização

O papel `global_knowledge_admin` é o único autorizado nos endpoints de escrita e
leitura administrativa do catálogo global. Ele autentica sem tenant, não acessa a
administração geral da plataforma e recebe `403` ao tentar acessar endpoints do RAG
Privado.

O comando de provisionamento é:

```shell
flask seed-global-knowledge-admin
```

A senha deve ser fornecida por `SEED_GLOBAL_KNOWLEDGE_ADMIN_PASSWORD`.

## Versionamento e publicação

Novos arquivos são armazenados em:

```text
global/rag/{document_id}/{version_id}/{arquivo}
```

Cada upload gera uma versão imutável e um evento
`IngestaoDocumentoRagGlobal`. O worker extrai texto, gera chunks e embeddings e
registra modelo, checksum, páginas e data de indexação. Uma versão só pode ser
publicada após chegar a `INDEXADO`.

Ao publicar uma nova versão, a versão publicada anterior passa automaticamente a
`SUBSTITUIDA`. Versões podem ser `SUSPENSA` ou `REVOGADA` sem exclusão física, para
preservar reproduções e futuras citações históricas.

## API administrativa

Prefixo: `/api/v1/platform/rag-global`

- `GET|POST /colecoes`;
- `GET|PATCH /colecoes/{colecaoId}`;
- `POST /colecoes/{colecaoId}/documentos`;
- `GET /colecoes/{colecaoId}/documentos/{documentoId}`;
- `POST /colecoes/{colecaoId}/documentos/{documentoId}/versoes`;
- `PATCH /colecoes/{colecaoId}/documentos/{documentoId}/versoes/{versaoId}/estado`;
- `POST /colecoes/{colecaoId}/documentos/{documentoId}/versoes/{versaoId}/reprocessar`;
- `GET /colecoes/{colecaoId}/documentos/{documentoId}/versoes/{versaoId}/download`.

## Controles

- política de distribuição e jurisdição são metadados obrigatórios da coleção;
- proveniência é obrigatória em todo documento;
- publicação exige indexação concluída;
- storage key é validada pela aplicação e por constraint PostgreSQL;
- download usa token assinado vinculado ao documento e à versão;
- toda criação, indexação e mudança de publicação gera auditoria global
  (`tenant_id = NULL`);
- o administrador global não recebe acesso implícito ao RAG Privado.

## Validação

- fluxo de autorização, ingestão, publicação e revogação coberto por testes;
- suíte backend local: 115 testes aprovados e 10 condicionais a PostgreSQL;
- migration completa validada em banco PostgreSQL descartável;
- schema, head Alembic, storage constraint e nulabilidade controlada da outbox
  verificados.
