# GabFlow — Spec-Driven Development

O **GabFlow** é uma plataforma de gestão de gabinetes parlamentares municipais, com foco em atendimento ao cidadão, gestão de demandas, produção legislativa, relacionamento institucional, agenda, fiscalização, comunicação e inteligência de mandato.

Este repositório contém a documentação de especificação utilizada para evoluir o produto de forma orientada a contratos, regras de negócio, cenários verificáveis e decisões arquiteturais.

## Objetivos

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
│   └── ADR-006-geospatial-analytics.md
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
- Mapas de calor.
- Tendências.
- Demandas reincidentes.
- Alertas de anomalia.
- Planejamento de visitas e ações.

## Convenções

- Requisitos funcionais: `RF-XXX`
- Requisitos não funcionais: `RNF-XXX`
- Regras de negócio: `RN-XXX`
- Requisitos de IA: `RIA-XXX`
- Requisitos analíticos: `RA-XXX`
- Eventos: nomes no passado, por exemplo `SolicitacaoCriada`
- Todos os timestamps em UTC e exibidos no fuso configurado pelo tenant.
