# Release 4.3 — Recuperação hierárquica

## Escopo entregue

Esta entrega implementa os passos 12–14 do plano:

12. resolver políticas, jurisdição, concessões e versões globais por tenant;
13. recuperar os escopos global e privado por fronteiras independentes;
14. deduplicar, reranquear e responder com citações de proveniência explícita.

Fork privado, conectores globais e ingestão automática dos demais módulos continuam
fora deste recorte.

## Concessões

A tabela `rag_global_entitlements` pertence ao domínio tenant-scoped e possui:

- `tenant_id` e `collection_id`;
- estado ativo, desativado ou revogado;
- atualização automática ou versão fixada;
- origem da concessão;
- responsável, justificativa e vigência.

A tabela usa RLS forçado. Usuários de gabinete só acessam a linha do próprio tenant.
O curador global ativa um contexto transacional específico para administrar
concessões direcionadas, sem receber acesso ao conteúdo RAG Privado.

## Resolução das políticas

- `OBRIGATORIA`: acesso automático quando a jurisdição é compatível;
- `PADRAO`: acesso automático, permitindo opt-out;
- `OPCIONAL`: exige opt-in do administrador do gabinete;
- `DIRECIONADA`: exige concessão ativa do curador global;
- `RESTRITA_JURISDICAO`: exige compatibilidade de país, UF, município, esfera,
  código IBGE e/ou tipo de casa;
- `PRIVADA_PLATAFORMA`: nunca entra na recuperação do tenant.

Concessões podem acompanhar a versão publicada ou fixar uma versão publicada
anterior. Versões suspensas ou revogadas não são recuperadas.

## Barreira de leitura global

O PostgreSQL expõe a view:

```text
rag_global.tenant_published_chunks
```

Ela utiliza `security_barrier`, o contexto `app.tenant_id`, publicação, vigência,
política e concessão. A aplicação ainda reaplica jurisdição e versão como defesa
adicional antes de carregar os candidatos.

## Recuperação federada

Uma consulta:

1. recupera candidatos privados sob RLS;
2. recupera candidatos globais autorizados pela view;
3. calcula score semântico e lexical em cada candidato;
4. elimina chunks duplicados por checksum;
5. reranqueia conjuntamente;
6. preserva diversidade entre os escopos somente quando ambos têm evidência acima
   do limiar;
7. aplica o limiar de groundedness;
8. registra fontes e escopos na consulta e na auditoria.

Cada fonte informa `escopo`, origem, rótulo, coleção, documento, versão, estado,
checksum do chunk, checksum do documento, jurisdição, proveniência, trecho, página,
modelo de embedding e score. A interface recebe os rótulos “Fonte GabFlow” e “Fonte
do Gabinete”.

## API

Tenant:

- `GET /api/v1/rag/catalogo-global`;
- `PATCH /api/v1/rag/catalogo-global/colecoes/{colecaoId}/adesao`.

Curadoria global:

- `PUT /api/v1/platform/rag-global/colecoes/{colecaoId}/concessoes/{tenantId}`.

## Validação

- políticas obrigatória, opcional, direcionada e privada cobertas;
- incompatibilidade de jurisdição coberta;
- versão fixada e versão automática cobertas;
- recuperação conjunta e ausência de vazamento privado cobertas;
- RLS forçado e view `security_barrier` validados em PostgreSQL;
- migration, downgrade e reaplicação validados.

## Evolução na Release 4.6.1

- O corte por recência antes do score foi removido; os chunks elegíveis são
  percorridos em lotes e o limite é aplicado ao pool já pontuado.
- A diversidade forçada entre escopos foi removida.
- Cada fonte citada precisa satisfazer o limiar mínimo de evidência.
- Embeddings somente são comparados quando o modelo e a dimensão são compatíveis.
- Falha ou incompatibilidade usa score lexical normalizado, sem vetor local
  artificial.
- Autoridade e atualidade participam do reranking sem alterar o score de evidência.

Permanece planejada a migração para PostgreSQL FTS + pgvector, necessária para
evitar varredura exata quando o volume crescer.
