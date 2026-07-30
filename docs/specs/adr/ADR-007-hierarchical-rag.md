# ADR-007 — RAG hierárquico global e privado

## Status

Aceito

## Contexto

O GabFlow precisa combinar conhecimento comum, curado pela plataforma, com
informações internas e exclusivas de cada gabinete. Copiar todo o catálogo global
para cada tenant aumentaria custo, divergência de versões e risco operacional.
Manter tudo em uma única coleção dificultaria demonstrar isolamento e impedir
promoção acidental de dados privados.

## Decisão

Adotar recuperação federada com dois domínios de persistência:

- `rag_global`: catálogo versionado, publicado e distribuído por política;
- `rag_private`: conhecimento exclusivo, protegido por tenant.

O contexto de um gabinete é a união, no momento da consulta, das fontes globais
autorizadas e das fontes privadas acessíveis. Conteúdo global é referenciado, não
copiado por padrão.

Coleções globais suportam distribuição obrigatória, padrão, opcional, direcionada,
restrita por jurisdição ou privada da plataforma. Tenants podem acompanhar a versão
mais recente, fixar uma versão ou criar fork privado explícito.

Dados privados nunca são promovidos para o catálogo global automaticamente. Uma
promoção exige autorização do tenant, anonimização, revisão humana e criação de nova
fonte global auditável.

A incorporação de informações produzidas nos módulos segue projeções governadas e
recuperação híbrida conforme o ADR-008; não significa copiar tabelas nem treinar o
modelo com dados privados.

## Fronteiras de autorização

- usuários de tenant possuem somente leitura sobre conteúdo global publicado e
  elegível;
- somente `GLOBAL_KNOWLEDGE_ADMIN` publica no catálogo global;
- `GLOBAL_KNOWLEDGE_ADMIN` e `PLATFORM_ADMIN` não recebem acesso implícito aos dados
  privados;
- acesso de suporte é temporário, escopado e auditado;
- RLS e constraints compostas protegem o domínio privado;
- API e worker não usam superusuário nem `BYPASSRLS`.

## Consequências

### Positivas

- atualização centralizada das fontes comuns;
- isolamento demonstrável dos dados internos;
- citações e reproduções por versão exata;
- menor duplicação de documentos e embeddings;
- possibilidade de políticas por jurisdição e plano;
- evolução para implantação dedicada sem mudar o contrato.

### Custos

- recuperação e reranking precisam normalizar dois conjuntos;
- concessões e versões globais exigem governança;
- testes devem cobrir vazamento, pool de conexões e workers;
- forks privados exigem rastreabilidade de origem e divergência.

## Alternativas rejeitadas

- **Copiar todo o catálogo global por tenant:** alto custo e versões divergentes.
- **Uma única coleção sem distinção de escopo:** aumenta o risco de vazamento e
  promoção acidental.
- **Uma infraestrutura completa por tenant como padrão:** custo operacional
  desproporcional; permanece opção enterprise.
