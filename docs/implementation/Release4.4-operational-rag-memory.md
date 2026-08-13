# Release 4.4 — Memória operacional

## Escopo entregue

Esta entrega implementa os passos 15–18 do plano:

15. registrar fontes internas elegíveis com finalidade, base legal, acesso, retenção e origem;
16. capturar transacionalmente mudanças em solicitações, interações e documentos legislativos;
17. projetar conteúdo minimizado em versões imutáveis do RAG Privado;
18. reconciliar dados preexistentes e validar isolamento, idempotência e descarte.

## Registro governado

`rag_knowledge_sources` é o catálogo privado que liga uma entidade de negócio ao
documento e à versão RAG derivados. A chave única por tenant, módulo, tipo e ID da
entidade impede colisões. A tabela usa RLS habilitado e forçado, incluindo a role
do worker.

Cada registro preserva:

- módulo, tipo e ID da entidade de origem;
- finalidade e base legal;
- nível de acesso e limite de retenção;
- decisão de elegibilidade e motivo;
- hash do conteúdo minimizado;
- versão lógica, documento e versão RAG atual.

## Captura e projeção

Eventos do SQLAlchemy observam a mesma transação que altera `ServiceRequest`,
`RequestInteraction`, `LegislativeDraft` ou `LegislativeDraftVersion`. O evento
`SincronizacaoMemoriaOperacional` é gravado no outbox antes do commit.

O worker:

1. recarrega a entidade dentro do contexto RLS do tenant;
2. avalia estado, geração concluída, presença de conteúdo e política de retenção;
3. remove e-mails, CPF, telefone e CEP, além de excluir endereço e coordenadas;
4. compara o hash para evitar nova versão sem mudança material;
5. grava um snapshot UTF-8 no armazenamento privado;
6. cria uma versão RAG em rascunho e solicita a indexação;
7. após indexar, torna a nova versão vigente e a anterior histórica.

Fontes inelegíveis ou expiradas desativam o documento da recuperação. A auditoria
registra somente a decisão e os identificadores, nunca o conteúdo descartado.

## Proveniência e segurança

Citações privadas passam a informar módulo, entidade de origem, finalidade, base
legal e retenção. O pipeline já existente continua tratando chunks como dados,
sanitizando instruções potencialmente maliciosas antes de formar a resposta.

## Reconciliação

Dados criados antes desta entrega podem ser enfileirados de forma idempotente:

```text
flask sync-operational-memory
flask sync-operational-memory --tenant gabinete-demo
```

Executar novamente é seguro: snapshots só avançam quando o hash minimizado muda.

## Configuração

`RAG_OPERATIONAL_MEMORY_ENABLED=true` habilita a captura automática na API e no
worker. Em testes legados ela fica desabilitada por padrão e é ativada
explicitamente nos cenários desta entrega.

`RAG_OPERATIONAL_MEMORY_MATERIALIZED_SNAPSHOTS=5` limita quantos snapshots por
fonte permanecem com conteúdo e embeddings materializados. O scheduler compacta
os snapshots excedentes, elimina arquivo, texto extraído e chunks, mas preserva
checksum e metadados imutáveis para proveniência até o fim da retenção da fonte.
Quando a retenção expira, o documento operacional e seus metadados são purgados,
restando somente o tombstone auditável.

## Validação

- criação e alteração de solicitação geram memória versionada;
- PII e localização residencial não entram nos chunks;
- versões anteriores tornam-se históricas somente após a nova indexação;
- cancelamento desativa a fonte sem copiar conteúdo para auditoria;
- registro de fontes participa das verificações PostgreSQL de RLS forçado.

## Limites conhecidos

Esta entrega é a fundação do item “informações aprendidas dos demais módulos”, não
sua conclusão:

- somente solicitações, interações e minutas legislativas estão cobertas;
- exclusões físicas não são capturadas pelo listener atual;
- retenção é reavaliada quando há alteração ou sincronização manual, sem sweep
  periódico dedicado;
- desativação impede recuperação, mas ainda não purga chunks, texto extraído,
  versões e arquivo privado;
- prompt injection é sanitizado na recuperação, sem quarentena completa antes do
  embedding;
- minutas entram quando a geração está `CONCLUIDA`; esta versão ainda não exige
  aprovação humana explícita para a projeção;
- falha definitiva da sincronização ainda não materializa estado `ERRO` na fonte;
- acesso privado usa os níveis `INTERNO` e `RESTRITO`, sem ACL granular por equipe
  ou responsável.

O plano de correção e expansão está em
`Release4.6-operational-knowledge-plan.md` e no ADR-008.
