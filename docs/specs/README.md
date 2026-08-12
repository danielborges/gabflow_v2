# GabFlow — Spec-Driven Development

O **GabFlow** é uma plataforma de gestão de gabinetes parlamentares municipais, com foco em atendimento ao cidadão, gestão de demandas, produção legislativa, relacionamento institucional, agenda, fiscalização, comunicação e inteligência de mandato.

Este repositório contém a documentação de especificação utilizada para evoluir o produto de forma orientada a contratos, regras de negócio, cenários verificáveis e decisões arquiteturais.

## Objetivos

O domínio WhatsApp possui especificação complementar em
[`../specs-whatsapp`](../specs-whatsapp/README.md), incluindo onboarding Meta, recebimento
confiável, inbox 2.0, privacidade, Flows, mídia/IA, saída/templates e operação do piloto.

- Centralizar solicitações recebidas por diferentes canais.
- Acompanhar todo o ciclo de vida do atendimento.
- Identificar demandas recorrentes e problemas territoriais.
- Apoiar a produção de indicações, requerimentos, ofícios e pedidos de informação.
- Disponibilizar um assistente de IA baseado em RAG.
- Automatizar classificação, resumo, transcrição e geração de documentos.
- Produzir indicadores operacionais, legislativos e territoriais.
- Garantir rastreabilidade, segurança, LGPD e revisão humana.

## Princípios do produto

1. Toda demanda deve ser rastreável.
2. Nenhuma resposta gerada por IA deve ocultar sua origem.
3. Documentos legislativos gerados por IA exigem validação humana.
4. Dados pessoais devem ser minimizados e protegidos.
5. Indicadores não podem ser utilizados como mecanismo automático de discriminação política.
6. Toda inferência deve apresentar evidências, período e grau de confiança.
7. Regras municipais devem ser configuráveis por Câmara ou gabinete.
8. Conhecimento global e conhecimento privado devem possuir fronteiras explícitas.
9. Nenhum dado privado de tenant pode melhorar outro tenant sem autorização e governança.
10. Toda citação RAG deve informar escopo, versão e proveniência.
11. Dados dos módulos entram no RAG somente por projeções governadas; fatos
    quantitativos permanecem em consultas estruturadas tenant-scoped.
12. Feedback humano é dado não confiável até validação e somente influencia o
    próprio tenant por artefatos versionados, avaliados e reversíveis.
13. Todo conteúdo externo ou textual permanece não confiável como instrução mesmo
    depois de autorizado para indexação; segurança de conteúdo exige defesa em
    profundidade e falha fechada.

## Estrutura do repositório

```text
gabflow-spec-driven/
├── README.md
├── product/
│   ├── vision.md
│   ├── personas.md
│   ├── glossary.md
│   └── roadmap.md
├── requirements/
│   ├── functional-requirements.md
│   ├── non-functional-requirements.md
│   ├── business-rules.md
│   ├── ai-requirements.md
│   └── analytics-requirements.md
├── architecture/
│   ├── system-context.md
│   ├── containers.md
│   ├── data-model.md
│   ├── rag-architecture.md
│   └── security-privacy.md
├── api/
│   ├── openapi.yaml
│   └── asyncapi.yaml
├── features/
│   ├── solicitacoes.feature
│   ├── classificacao-ia.feature
│   ├── assistencia-atendimento-ia.feature
│   ├── documentos-legislativos.feature
│   ├── assistente-rag.feature
│   ├── insights.feature
│   └── lgpd.feature
├── adr/
│   ├── ADR-001-modular-monolith-first.md
│   ├── ADR-002-event-driven-integration.md
│   ├── ADR-003-rag-with-citations.md
│   ├── ADR-004-human-in-the-loop.md
│   ├── ADR-005-multi-tenant.md
│   ├── ADR-006-geospatial-analytics.md
│   ├── ADR-007-hierarchical-rag.md
│   ├── ADR-008-operational-knowledge-projections.md
│   ├── ADR-009-controlled-feedback-learning.md
│   ├── ADR-010-assisted-whatsapp-email-identity.md
│   ├── ADR-011-governed-geospatial-provider.md
│   └── ADR-012-aws-production-platform.md
├── governance/
│   ├── definition-of-ready.md
│   ├── definition-of-done.md
│   ├── ai-governance.md
│   └── observability-slo.md
└── examples/
    ├── sample-request.json
    ├── sample-ai-classification.json
    └── sample-rag-answer.json
```

## Fluxo Spec-Driven

1. Definir ou alterar a especificação.
2. Revisar regras de negócio e impacto em LGPD.
3. Atualizar contratos OpenAPI e AsyncAPI.
4. Criar ou atualizar cenários Gherkin.
5. Registrar decisões arquiteturais relevantes.
6. Gerar mocks, SDKs e testes de contrato.
7. Implementar.
8. Validar critérios de aceite.
9. Monitorar indicadores e revisar o comportamento da IA.

## Escopo inicial recomendado

### Fase 1 — Fundação operacional
- Cadastro de cidadãos, organizações, territórios e canais.
- Registro, triagem, encaminhamento e acompanhamento de solicitações.
- Histórico, anexos, comentários, SLA e notificações.
- Painel operacional.

Especificação evolutiva do diretório: `features/cadastro-cidadaos-organizacoes-v2.feature`.

### Fase 2 — Inteligência e automação
- Classificação automática.
- Transcrição e resumo de áudio.
- Detecção de duplicidade.
- Sugestão de encaminhamento.
- Geração assistida de respostas e documentos.

### Fase 3 — RAG legislativo e institucional
- Indexação de legislação, regimento, atos, processos e respostas.
- Assistente com citações.
- Busca semântica.
- Identificação de precedentes.

### Fase 4 — Inteligência territorial e estratégica
- Base de mapas de calor, tendências, recorrências e alertas entregue na Release 5.
- Confiabilidade territorial e proveniência das coordenadas antes de novas inferências.
- Exploração com comparação temporal e acesso aos casos subjacentes.
- Conversão de hotspots e alertas em tarefas, agenda, visitas e encaminhamentos rastreáveis.
- Cartografia governada, qualidade cadastral e inteligência avançada condicionadas a gates.

Estratégia vigente: [`Territorial-intelligence-evolution-strategy.md`](../implementation/Territorial-intelligence-evolution-strategy.md).

## Convenções

- Requisitos funcionais: `RF-XXX`
- Requisitos não funcionais: `RNF-XXX`
- Regras de negócio: `RN-XXX`
- Requisitos de IA: `RIA-XXX`
- Requisitos analíticos: `RA-XXX`
- Eventos: nomes no passado, por exemplo `SolicitacaoCriada`
- Todos os timestamps em UTC e exibidos no fuso configurado pelo tenant.

## Datasets de especificação

Datasets em `datasets/` são contratos versionados de avaliação e não fontes do RAG.
O dataset adversarial de prompt injection possui JSON Schema próprio, casos
`REGRESSION` e `HOLDOUT`, ataques sintéticos e controles benignos. Seu conteúdo não
pode ser indexado, recuperado pelo assistente ou promovido para catálogo factual.

O incremento 5.2 materializa esse contrato em um gateway único e persiste seu
estado nas versões privadas/globais, fontes operacionais e feedback. A API expõe
somente metadados de decisão e checksum, nunca o payload analisado.

O incremento 5.4 torna o dataset um gate executável do gateway e adiciona
canonicalização defensiva limitada e classificador dedicado, independente do modelo
gerador. O contrato do classificador aceita somente `label`, `score` e categorias
allowlisted; erro, timeout ou contrato inválido falham de forma fechada.

O incremento 5.5 substitui o smoke test EICAR isolado por ClamAV operacional,
valida o MIME real, revalida checksum e malware antes do parsing e move TXT, DOCX,
PDF e imagens para um sidecar sem rede, segredos ou escrita nos objetos.

O incremento 5.6 reavalia o acervo privado, global e os anexos em execuções
assíncronas e retomáveis. Alvos pendentes ficam inelegíveis no retrieval e uma
reclassificação elimina chunks, embeddings, OCR, transcrição e memória operacional
derivada antes de registrar a conclusão auditável.
