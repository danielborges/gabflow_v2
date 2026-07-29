# ADR-008 — Conhecimento operacional por projeções governadas

## Status

Aceito

## Contexto

O GabFlow precisa usar informações produzidas nos módulos do gabinete para apoiar
atendimento, planejamento e produção legislativa. Copiar tabelas inteiras para o
RAG aumenta ruído, risco de exposição de dados pessoais e inconsistência entre o
estado transacional e o conhecimento recuperável. Busca vetorial também não é
adequada para contagens, indicadores ou perguntas que exigem exatidão relacional.

A Release 4.4 entregou a primeira projeção de memória operacional para solicitações,
interações e minutas legislativas. A expansão para os demais módulos exige um
contrato uniforme de elegibilidade, segurança, versionamento e descarte.

## Decisão

Adotar uma arquitetura híbrida:

- **memória operacional documental:** snapshots canônicos, minimizados e
  versionados no RAG Privado para recuperação semântica e citações;
- **consulta estruturada:** read models e consultas tenant-scoped para contagens,
  estados, prazos, agrupamentos e indicadores;
- **roteamento de intenção:** o assistente escolhe recuperação documental, consulta
  estruturada ou composição das duas, registrando o método usado.

Cada tipo de entidade elegível deve possuir um projetor registrado. O projetor:

1. recarrega o estado canônico dentro do contexto transacional do tenant;
2. valida estado de aprovação, finalidade, base legal, retenção, sigilo e ACL;
3. seleciona campos por allowlist e minimiza PII;
4. detecta conteúdo malicioso e define aprovação, sanitização ou quarentena;
5. produz conteúdo canônico e metadados de proveniência;
6. calcula hash e cria nova versão somente quando houver mudança material;
7. torna a nova versão vigente apenas após indexação bem-sucedida;
8. despublica ou elimina o conhecimento quando a origem for cancelada, excluída,
   anonimizada ou expirada.

O registry implementado mantém uma definição imutável por tipo de entidade com
módulo, versão semântica, proprietário, ações suportadas, allowlist de campos,
finalidade, base legal padrão, ACL, tipo de retenção e políticas de quarentena e
purge. Tipos não registrados são rejeitados antes de entrar no outbox. A versão do
projetor que produziu a fonte é persistida para proveniência e auditoria.

O caminho primário é evento de domínio gravado no outbox na mesma transação da
alteração. O evento transporta apenas identificadores, revisão e ação, sem copiar
conteúdo sensível. Varreduras agendadas são usadas somente para backfill,
reconciliação, expiração e detecção de divergências.

O contrato V2 implementado diferencia `CREATE`, `UPDATE`, `CANCEL`, `DELETE`,
`ANONYMIZE`, `RETENTION_EXPIRED` e `RECONCILE`. A fonte operacional guarda a maior
revisão processada para impedir que entrega duplicada ou fora de ordem sobrescreva
uma projeção mais nova.

Cadastros brutos de cidadãos, consentimentos, solicitações de privacidade,
credenciais, configurações, notificações, auditoria e saídas de IA não revisadas não
podem ser indexados como conhecimento operacional.

## Ciclo de vida

- `ATIVA`: fonte elegível e versão vigente indexada;
- `PENDENTE`: alteração aceita aguardando projeção ou indexação;
- `QUARENTENA`: conteúdo requer revisão de segurança;
- `INELEGIVEL`: origem não satisfaz finalidade, aprovação, base legal ou sigilo;
- `EXPIRADA`: prazo de retenção encerrado;
- `ERRO`: sincronização esgotou retentativas e requer intervenção;
- `EXCLUIDA`: origem eliminada e conteúdo derivado purgado.

Despublicação deve ser imediata. Purge remove chunks, embeddings, texto extraído,
versões derivadas e objeto de armazenamento, preservando somente auditoria sem
conteúdo e os identificadores mínimos exigidos.

Na implementação, `PENDENTE` somente passa a `ATIVA` após a indexação concluir.
Atualizações pendentes, em quarentena ou com erro não substituem a versão vigente
anterior. Ações destrutivas desativam o documento no commit de emissão do evento e
o worker conclui um purge idempotente, deixando `EXCLUIDA` como tombstone sem
conteúdo. O scheduler emite expiração por tenant e o administrador pode inspecionar
e reprocessar fontes não excluídas.

## Consequências

### Positivas

- conhecimento privado atualizado sem treinar o modelo;
- proveniência até o módulo e entidade de origem;
- menor risco de PII, prompt injection e conteúdo não aprovado;
- respostas quantitativas reproduzíveis por consulta estruturada;
- backfill e reprocessamento idempotentes;
- expansão incremental por módulo.

### Custos

- cada módulo precisa manter projetor e testes de contrato;
- exclusão, retenção e ACL exigem propagação para os artefatos derivados;
- o assistente precisa rotear intenção e combinar resultados heterogêneos;
- qualidade de recuperação deve ser medida antes de ampliar o volume indexado.

## Alternativas rejeitadas

- **Indexar todas as tabelas:** não representa semântica de aprovação, amplia PII e
  produz conhecimento ruidoso.
- **CDC como caminho principal:** captura deltas de linha, não a regra de negócio ou
  o aggregate canônico; permanece opção futura para integração entre serviços.
- **Varredura periódica como ingestão principal:** aumenta latência, custo e
  dificuldade de identificar exclusões.
- **Usar RAG para indicadores:** similaridade semântica não garante contagem,
  agrupamento ou estado transacional exato.
