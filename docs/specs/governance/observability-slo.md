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
- `precision@k` e `recall@k` da recuperação por tenant;
- taxa de fontes desconexas;
- distribuição de consultas documentais, estruturadas e híbridas.

## Alertas

- aumento de erro;
- processamento parado;
- quebra de isolamento;
- falha de indexação;
- custo anormal;
- degradação de qualidade;
- ausência de fontes;
- aumento de respostas recusadas.
- fonte operacional desatualizada ou em erro definitivo;
- divergência detectada pela reconciliação;
- purge vencido ou incompleto;
- aumento de quarentena de conteúdo interno.

## Implementação RAG

A Release 4.5 disponibiliza:

- métricas Prometheus protegidas em `/api/v1/metrics`;
- saúde da fila e avaliação do SLO em `/api/v1/health/rag`;
- métricas tenant-scoped em `/api/v1/assistente/metricas`;
- logs JSON correlacionados;
- duração de consultas e eventos;
- idade, falhas e volume pendente do outbox RAG.

A Release 4.6 adiciona:

- dataset de perguntas reais isolado por tenant;
- execuções persistidas por `k`;
- `precision@k`, `recall@k`, groundedness e precisão de citações;
- taxa de fontes desconexas e acurácia de recusa;
- histórico em `/api/v1/assistente/avaliacoes/execucoes`.

Metas iniciais:

- p95 de consulta RAG menor ou igual a 15 segundos;
- evento RAG mais antigo pendente por no máximo 5 minutos;
- nenhuma falha definitiva sem alerta dentro da janela operacional.

Metas planejadas para conhecimento operacional:

- medir o tempo entre commit da entidade e disponibilidade da versão vigente;
- nenhuma fonte `ERRO`, `EXPIRADA` ou `EXCLUIDA` participando da recuperação;
- purge concluído dentro do prazo definido pela política de retenção;
- reconciliação sem divergências silenciosas entre origem e fonte projetada.
