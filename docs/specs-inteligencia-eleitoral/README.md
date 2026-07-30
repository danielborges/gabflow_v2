# GabFlow — Módulo Inteligência Eleitoral e Territorial

Pacote de especificação orientada a desenvolvimento (Spec-Driven Development) para um módulo do GabFlow destinado ao perfil `PARLAMENTAR`.

## Objetivo

Entregar inteligência eleitoral baseada em dados públicos oficiais, com análises territoriais, comparações históricas e insights de IA, conectando esses dados — de forma agregada e juridicamente segura — às demandas, entregas e ações do mandato já geridas pelo GabFlow.

## Princípios

1. Dados eleitorais oficiais e rastreáveis.
2. Nenhuma inferência de voto individual.
3. Separação entre dado público eleitoral, dado institucional do mandato e dado pessoal do cidadão.
4. Isolamento multi-tenant por gabinete.
5. IA explicável, com fontes, metodologia e nível de confiança.
6. Funcionalidades liberadas por feature flag e permissões.
7. Exportações com marca d'água, autoria e trilha de auditoria.

## Escopo documental

| Arquivo | Conteúdo |
|---|---|
| `docs/01-visao-produto.md` | Visão, personas, proposta de valor e diferenciais |
| `docs/02-requisitos-funcionais.md` | Épicos, requisitos e critérios de aceite |
| `docs/03-regras-negocio.md` | Regras, permissões, privacidade e auditoria |
| `docs/04-modelo-dados.md` | Entidades, relacionamentos e retenção |
| `docs/05-roadmap.md` | MVP, evoluções e métricas |
| `api/openapi.yaml` | Contrato REST inicial |
| `api/asyncapi.yaml` | Eventos assíncronos |
| `features/inteligencia-eleitoral.feature` | Cenários Gherkin |
| `adr/ADR-001-fontes-eleitorais.md` | Estratégia de ingestão |
| `adr/ADR-002-segregacao-dados.md` | Segregação e privacidade |
| `adr/ADR-003-ia-explicavel.md` | Uso responsável de IA |
| `adr/ADR-004-geoespacial.md` | Estratégia geoespacial |

## Stack de referência

- Frontend: React.
- Backend: Python/FastAPI.
- Banco: PostgreSQL com PostGIS.
- Filas/cache: Redis e Celery.
- Busca vetorial/RAG: Qdrant.
- Arquivos: armazenamento compatível com S3/MinIO.
- Observabilidade: Prometheus, Grafana e logs estruturados.

## Glossário

- **Território eleitoral:** recorte agregado como município, zona, bairro, local ou seção.
- **Base eleitoral:** conjunto agregado de regiões com desempenho relevante; nunca uma lista inferida de eleitores.
- **Índice de presença:** indicador composto do desempenho territorial do parlamentar.
- **Cobertura do mandato:** relação agregada entre demandas, ações/entregas e territórios.
- **Insight:** interpretação automatizada, não uma afirmação causal.

## Definition of Done

Uma história só está concluída quando possuir: contrato de API, autorização testada, isolamento de tenant, auditoria, testes automatizados, acessibilidade, observabilidade, documentação e validação dos critérios Gherkin aplicáveis.
