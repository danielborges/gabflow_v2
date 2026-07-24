# Observabilidade e SLO

## Indicadores técnicos

- disponibilidade;
- latência;
- taxa de erro;
- filas pendentes;
- tempo de processamento;
- falhas de integração;
- consumo de tokens;
- custo de IA;
- taxa de timeout;
- taxa de fallback.

## Indicadores de qualidade de IA

- acurácia da classificação;
- precisão das citações;
- groundedness;
- taxa de alucinação;
- taxa de aceitação;
- taxa de edição;
- taxa de rejeição;
- distribuição por categoria;
- incidentes de privacidade.

## Alertas

- aumento de erro;
- processamento parado;
- quebra de isolamento;
- falha de indexação;
- custo anormal;
- degradação de qualidade;
- ausência de fontes;
- aumento de respostas recusadas.

## Implementação RAG

A Release 4.5 disponibiliza:

- métricas Prometheus protegidas em `/api/v1/metrics`;
- saúde da fila e avaliação do SLO em `/api/v1/health/rag`;
- métricas tenant-scoped em `/api/v1/assistente/metricas`;
- logs JSON correlacionados;
- duração de consultas e eventos;
- idade, falhas e volume pendente do outbox RAG.

Metas iniciais:

- p95 de consulta RAG menor ou igual a 15 segundos;
- evento RAG mais antigo pendente por no máximo 5 minutos;
- nenhuma falha definitiva sem alerta dentro da janela operacional.
