# Release 8.0 — IA explicável e cenários

Data de estabilização: 2026-08-04.

## Escopo entregue

- insight individual ou comparativo enfileirado pelo outbox;
- resultado estruturado em fatos, cálculos, hipóteses e limitações;
- citação obrigatória de fonte, hash, versão do dataset e filtros;
- versão do mecanismo e template persistida em cada execução;
- feedback aceito, descartado ou contestado, com ocultação para revisão;
- cenário territorial com baseline oficial preservado e premissas explícitas;
- fórmulas, autoria, metodologia e disclaimer persistidos;
- RLS forçado por tenant nas três novas tabelas;
- áreas de trabalho `IA explicável` e `Cenários`, protegidas por feature flags e
  capacidades próprias.

## Decisões de segurança

A primeira versão não usa um LLM. O mecanismo `electoral-explainable-v1` transforma
somente agregações oficiais em afirmações e cálculos reproduzíveis. Não infere voto
individual, ideologia, intenção de voto ou causalidade. Essa escolha cria o contrato de
evidência e contestação antes da futura geração em linguagem natural com RAG.

Os cenários não alteram tabelas oficiais. Cada resultado se identifica como simulação
hipotética, não pesquisa registrada ou previsão.

## Backlog explícito

- perguntas livres fundamentadas em documentos autorizados;
- recusa adversarial e auditoria minimizada de prompts bloqueados;
- compartilhamento somente leitura e cópia de cenário;
- comparação e sensibilidade multivariada entre cenários;
- intervalos de incerteza calibrados;
- revisão humana com fila administrativa dedicada.

## Homologação

- testes de backend cobrem fila, evidência, fórmulas, feedback e imutabilidade oficial;
- lint, testes e build do frontend permanecem verdes;
- migration PostgreSQL/PostGIS cobre tabelas, índices, grants e RLS forçado.
