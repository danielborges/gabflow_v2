# Roadmap e Priorização

## Fase 0 — Fundação

- Feature flag e RBAC.
- Catálogo de eleições.
- Pipeline TSE versionado.
- Modelo PostGIS.
- Auditoria e nota de qualidade.

## Fase 1 — MVP

- Pesquisa de candidato.
- Detalhamento por território.
- Comparação de até cinco candidatos.
- Histórico entre eleições.
- Favoritos.
- Mapa coroplético.
- PDF e CSV/XLSX.
- Acesso do Parlamentar e delegação.

Critério de saída: carga validada de pelo menos duas eleições, consultas P95 abaixo de 2 s e testes de isolamento aprovados.

## Fase 2 — Inteligência GabFlow

- Camadas agregadas de demandas, SLA, agenda, ações e entregas.
- Índice de Cobertura Territorial.
- Briefing territorial.
- Alertas.
- Compromissos públicos.

## Fase 3 — IA explicável

- Análise individual e comparativa.
- Perguntas em linguagem natural.
- RAG sobre relatórios, entregas e documentos públicos.
- Feedback e revisão.
- Avaliação automatizada de citações e números.

## Fase 4 — Cenários

- Simulador com premissas.
- Metas territoriais agregadas.
- Sensibilidade e intervalos.
- Comparação de cenários.

## Fase 5 — Expansão

- Apuração paralela opcional.
- Aplicativo móvel/PWA offline para fiscais autorizados.
- Integração com pesquisas eleitorais registradas.
- Benchmark anonimizado somente com consentimento e critérios mínimos.

## Backlog de diferenciais

| Item | Valor | Esforço | Prioridade |
|---|---:|---:|---:|
| Mapa do mandato | Alto | Médio | 1 |
| Briefing territorial | Alto | Médio | 2 |
| IA com evidências | Alto | Alto | 3 |
| Índice de cobertura | Alto | Médio | 4 |
| Compromissos públicos | Médio/alto | Médio | 5 |
| Simulador | Alto | Alto | 6 |
| Alertas | Médio | Médio | 7 |
| Apuração paralela | Sazonal | Alto | 8 |

## Métricas de produto

- Ativação: primeiro comparativo concluído em até 15 minutos.
- Adoção: 60% dos parlamentares ativos usam o módulo mensalmente.
- Valor: redução de 70% no tempo de preparação de briefing.
- Confiança: menos de 1% dos insights contestados por erro quantitativo.
- Segurança: zero vazamento entre tenants.
- Qualidade: 100% das análises com fonte e versão.
