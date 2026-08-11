# Requisitos de Analytics e Insights

- **RA-001** Volume de solicitações por período. **Implementado na Release 5.**
- **RA-002** Distribuição por categoria e subcategoria. **Implementado na Release 5 para categoria; subcategoria permanece como evolução de taxonomia.**
- **RA-003** Distribuição territorial. **Base implementada na Release 5; comparação temporal, qualidade e contrato único de filtros planejados para 5.1 e 5.2.**
- **RA-004** Canais mais utilizados. **Implementado na Release 5.**
- **RA-005** Tempo até primeira resposta. **Implementado na Release 5.**
- **RA-006** Tempo até encaminhamento. **Implementado na Release 5.**
- **RA-007** Tempo até encerramento. **Implementado na Release 5.**
- **RA-008** Taxa de resolução. **Implementado na Release 5 como métrica operacional de resoluções registradas.**
- **RA-009** Taxa de reabertura. **Implementado na Release 5 como contagem operacional de reaberturas.**
- **RA-010** Taxa de solicitações sem retorno. **Implementado parcialmente na Release 5 por retornos pendentes/vencidos e fila prioritária.**
- **RA-011** Órgãos mais acionados. **Implementado na Release 5.**
- **RA-012** Tempo de resposta por órgão. **Implementado parcialmente na Release 5 por encaminhamentos e respostas auditáveis; agregação dedicada por órgão fica pendente.**
- **RA-013** Demandas reincidentes por local. **Detecção implementada na Release 5; investigação dos casos e ciclo de vida do alerta planejados para 5.2 e 5.4.**
- **RA-014** Tendência de crescimento ou redução. **Regra de comparação de janelas implementada na Release 5; visualização comparável e explicação completa planejadas para 5.2.**
- **RA-015** Detecção de anomalias. **Regra determinística implementada na Release 5; ação, acompanhamento e avaliação do alerta planejados para 5.4.**
- **RA-016** Solicitações agrupadas por evento urbano.
- **RA-017** Demandas que originaram proposições.
- **RA-018** Proposições originadas de múltiplas demandas.
- **RA-019** Bairros com baixa presença do gabinete. **Planejado para 5.5 após estabilização de agenda, visitas e qualidade territorial.**
- **RA-020** Cobertura de visitas por território. **Planejado para 5.5, com fórmula e pesos versionados.**
- **RA-021** Temas com maior taxa de solução. **Planejado para 5.2.**
- **RA-022** Qualidade cadastral. **Qualidade territorial planejada para 5.1 e painel administrativo para 5.3.**
- **RA-023** Carga de trabalho por equipe. **Planejado para 5.2 no painel territorial.**
- **RA-024** Previsão de volume, com faixa de incerteza. **Condicionada aos gates do incremento 5.5.**
- **RA-025** Relatório de prestação de contas por intervalo de datas. **Evoluído a partir do relatório mensal da Release 5.**
- **RA-026** Percentual de solicitações atrasadas por território, categoria e órgão, com numerador e denominador explícitos. **Implementado por território no incremento 5.2.**
- **RA-027** Taxa de solução por território, categoria e órgão, distinguindo resolução, encerramento e cancelamento. **Implementado por território no incremento 5.2.**
- **RA-028** Mediana e percentis de primeira resposta e resolução por território, evitando depender somente da média. **Medianas implementadas no incremento 5.2; percentis permanecem planejados.**
- **RA-029** Variação absoluta e percentual contra período anterior equivalente, com estado explícito quando a base for insuficiente ou zero. **Implementado no incremento 5.2.**
- **RA-030** Cobertura territorial separada em território identificado, coordenada aproximada, coordenada verificada, ambígua e fora da jurisdição.
- **RA-031** Quantidade e proporção de alertas novos, investigados, convertidos em ação, resolvidos e descartados.
- **RA-032** Tempo entre detecção do alerta, primeira investigação, criação de ação e conclusão.
- **RA-033** Conversão do funil de produto `abertura > filtro > investigação > ação`, usando telemetria minimizada.
- **RA-034** Qualidade por fonte e método de geocodificação, incluindo confiança, idade, falhas e correções humanas.
- **RA-035** Latência P50, P95 e P99 das consultas territoriais por volume e combinação de filtros.
- **RA-036** Efetividade operacional após ação territorial, apresentada como evolução observada e nunca como causalidade automática.
- **RA-037** Ranking de eficiência dos funcionários do gabinete, combinando resolução, cumprimento de prazo e atividade registrada, sem incluir o Parlamentar. **Implementado.**
- **RA-038** Distribuição de atendimentos por horário e identificação da faixa de maior atividade. **Implementado.**
- **RA-039** Identificação do cidadão mais atuante e das regiões e categorias com maior volume de demandas no período, respeitando permissões e agregação mínima. **Implementado.**
- **RA-040** Quantidade de documentos legislativos relacionados às demandas e ações operacionais geradas a partir delas. **Implementado.**
- **RA-041** Classificação executiva dos achados em problemas, avisos e resultados positivos, com critério determinístico e base de cálculo visível. **Implementado.**
- **RA-042** Relatório de Insights do Mandato com leitura estratégica dos indicadores do período, sem inferência de preferência ou propensão eleitoral individual. **Implementado.**
- **RA-043** Agenda executiva semanal com volume de compromissos, presença parlamentar, distribuição por tipo, ritmo diário e alertas de conflito ou concentração. **Implementado.**

## Dimensões mínimas

- tempo;
- tenant;
- equipe;
- responsável;
- canal;
- categoria;
- subcategoria;
- status;
- prioridade;
- bairro;
- região;
- órgão;
- tipo de cidadão ou organização;
- origem;
- resultado.

## Restrições

- Não exibir segmentações com poucos indivíduos quando houver risco de identificação.
- Não criar score de propensão eleitoral.
- Não inferir apoio político individual.
- Resultados preditivos devem ser usados para planejamento, não para excluir atendimento.
- Coordenadas aproximadas não podem ser contabilizadas ou apresentadas como verificadas.
- Comparações devem informar período, base, método, tamanho da amostra e grupos suprimidos.
- Protocolo ou ponto individual somente pode ser exibido quando perfil, finalidade e limiar do menor recorte autorizarem.
- Variação após uma ação territorial não deve ser apresentada automaticamente como efeito causal da ação.
