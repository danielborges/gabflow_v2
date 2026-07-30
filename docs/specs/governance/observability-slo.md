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
- taxa de feedback por avaliação, motivo e estado de moderação;
- tempo entre feedback aprovado, compilação e ativação;
- regressão candidato versus baseline por artefato;
- taxa de rollback e versão ativa dos artefatos por tenant;
- repetição de avaliação negativa após ativação.
- acurácia de roteamento e de filtros nos casos curados;
- taxa de recuperação de hard negatives;
- casos curados desativados por feedback ou fonte inelegível.

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
- pico anormal de feedback por usuário, consulta, fonte ou período;
- tentativa de prompt injection em comentário ou correção;
- artefato candidato com regressão acima da tolerância;
- aprendizado ativo sem baseline, aprovação ou versão de rollback;
- divergência entre feedback revogado e artefato ainda ativo.

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

A Release 4.7 planeja:

- métricas de captura, moderação e quarentena de feedback;
- duração e falhas da compilação tenant-scoped;
- comparação de candidato com baseline;
- ativação, canário, rollback e drift por versão de artefato;
- correlação sem conteúdo entre consulta, feedback, execução e artefato.

Metas iniciais:

- p95 de consulta RAG menor ou igual a 15 segundos;
- evento RAG mais antigo pendente por no máximo 5 minutos;
- nenhuma falha definitiva sem alerta dentro da janela operacional.

Metas planejadas para conhecimento operacional:

- medir o tempo entre commit da entidade e disponibilidade da versão vigente;
- nenhuma fonte `ERRO`, `EXPIRADA` ou `EXCLUIDA` participando da recuperação;
- purge concluído dentro do prazo definido pela política de retenção;
- reconciliação sem divergências silenciosas entre origem e fonte projetada.
