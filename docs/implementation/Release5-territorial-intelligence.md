# Release 5 - Inteligencia territorial

> **Revisao de produto:** a Release 5 permanece como registro da base entregue. A avaliacao
> posterior identificou que o painel ainda e predominantemente descritivo e requer uma evolucao
> orientada a confiabilidade, investigacao e acao. O plano vigente esta em
> [`Territorial-intelligence-evolution-strategy.md`](Territorial-intelligence-evolution-strategy.md).

## Evolucao posterior dos relatorios

A funcionalidade originalmente entregue como **Relatorio mensal** foi promovida para
**Relatorios**. O registro abaixo permanece fiel ao escopo da Release 5, mas a versao
vigente aceita data inicial e data final e oferece os tipos **Operacional** e **Insights
do Mandato**. A tela atual combina indicadores e graficos com um semaforo executivo de
problemas, avisos e resultados positivos, e permite gerar PDF de apresentacao do gabinete.

O relatorio operacional passou a incluir ranking de eficiencia da equipe sem o
Parlamentar, horario de maior atendimento, cidadao mais atuante, regioes e demandas mais
recorrentes, documentos legislativos relacionados e acoes geradas no periodo. O painel
de indicadores operacionais permanece dentro da aba Operacao, sem acao redundante de
atualizacao manual, e as abas usam continuidade visual com o corpo da pagina.

Contratos vigentes da funcionalidade:

```text
GET /api/v1/painel/relatorios?inicio=YYYY-MM-DD&fim=YYYY-MM-DD&tipo=operacional
GET /api/v1/painel/relatorios/pdf?inicio=YYYY-MM-DD&fim=YYYY-MM-DD&tipo=insights_mandato
```

O intervalo e inclusivo nas duas extremidades e limitado a 731 dias. O tipo tambem aceita
`insights` como alias de `insights_mandato`.

## Escopo entregue

| Spec | Implementacao |
| --- | --- |
| RF-080 | Painel operacional com volume por status, categoria, territorio, orgao, canal e periodo, com filtros por data, categoria, canal, territorio e orgao |
| RF-081 | Metricas de tempo ate primeira resposta, primeiro encaminhamento, encerramento e resolucao |
| RF-082 | Reaberturas contabilizadas e alertas de reincidencia por categoria, territorio e celula geografica |
| RF-083 | Mapa territorial interativo em homologacao com base Geoapify, pontos geocodificados, hotspots, limites da jurisdicao, navegacao e selecao de territorio; o SVG anterior permanece apenas como contingencia |
| RF-085 | Relatorio mensal do mandato com resumo, destaques, indicadores agregados e evidencias rastreaveis por protocolo |
| RF-086 | Indicadores por orgao destinatario no painel e no relatorio mensal |
| RF-087 | Fila prioritaria com demandas atrasadas, proximas do prazo, sem responsavel, aguardando orgao e retornos pendentes |
| RA-001 a RA-004 | Distribuicoes por periodo, categoria, territorio, origem/canal e orgao |
| RA-005 a RA-009 | Tempos operacionais, taxa operacional de resolucao por registros fechados e contagem de reaberturas |
| RA-010 a RA-015 | Demandas sem retorno operacional, orgaos acionados, reincidencia local, tendencia por janela e crescimento anormal auditavel |
| RA-025 | Relatorio mensal de prestacao de contas com evidencias |
| RIA-060 a RIA-065 | Insights com metodo, periodo, base de calculo, agregacao minima, amostra insuficiente e origem auditavel dos dados |
| ADR-006 | Inteligencia geoespacial tenant-safe, com PostGIS quando disponivel e fallback local aproximado |

## Fluxo operacional

1. O usuario acessa o painel operacional e aplica filtros de periodo, categoria, canal, territorio, orgao e granularidade.
2. A API calcula indicadores, series por periodo, quebras dimensionais e metricas de atendimento apenas para o tenant autenticado.
3. Grupos pequenos sao suprimidos nas agregacoes sensiveis antes de serem enviados para a interface.
4. A aba de inteligencia territorial apresenta cobertura geografica, hotspots, pontos geocodificados e mapa de calor.
5. A acao de geocodificacao preenche coordenadas faltantes a partir de endereco, territorio, titulo e descricao, preservando auditoria.
6. Quando a base suporta PostGIS, o painel sinaliza o metodo geoespacial ativo; quando nao suporta, usa calculo local aproximado.
7. A jurisdicao territorial do tenant pode ser configurada manualmente ou importada da malha do IBGE por codigo.
8. O relatorio mensal consolida demandas recebidas, movimentadas, encaminhadas, encerradas, abertas e atrasadas no periodo.
9. O relatorio inclui destaques por categoria, territorio e orgao somente quando a agregacao minima permite.
10. Evidencias do relatorio apontam protocolos e eventos de encerramento, encaminhamento, resposta de orgao e comunicacao ao cidadao.

## Controles de governanca e privacidade

- todas as consultas sao filtradas pelo tenant autenticado;
- a jurisdicao territorial e auditada em alteracoes manuais e importacoes do IBGE;
- a geocodificacao registra historico por solicitacao e auditoria consolidada;
- nenhum indicador tenta inferir apoio politico, preferencia eleitoral ou propensao individual;
- recortes com menos de tres solicitacoes sao suprimidos em agregacoes sensiveis;
- alertas de reincidencia e crescimento anormal sao regras deterministicas, com janela e criterio expostos;
- crescimento anormal e apresentado como sinal operacional, nao como causalidade;
- o relatorio mensal preserva evidencias por protocolo para revisao humana;
- o mapa territorial pode usar limites oficiais da jurisdicao sem expor dados pessoais alem dos dados operacionais ja autorizados.

## Interfaces entregues

- filtros do painel operacional por periodo, categoria, canal, territorio, orgao e granularidade;
- aba de operacao com metricas, fila prioritaria, retornos e alertas de demanda;
- aba de inteligencia territorial com cobertura, jurisdicao, hotspots, mapa de calor e pontos geocodificados;
- acao de geocodificar demandas pendentes;
- aba de relatorio mensal com selecao de mes/ano, resumo, destaques, indicadores e evidencias;
- administracao da jurisdicao territorial do tenant, incluindo tipo de casa, municipio, UF, codigo IBGE, centro, limites e GeoJSON;
- importacao de malha territorial do IBGE para camaras municipais e assembleias legislativas.

## Limites desta entrega

- o heatmap PostGIS atual nao compartilha integralmente o mesmo contexto de filtros das demais
  agregacoes; a unificacao e criterio de aceite do incremento 5.1;
- a metrica de cobertura atual indica presenca de coordenadas, mas ainda nao diferencia origem,
  aproximacao, verificacao, confianca e validade dentro da jurisdicao;
- o fallback local gera coordenadas aproximadas e nao deve ser usado como fonte cartografica
  verificada nem como solucao definitiva para outros municipios ou estados;
- hotspots, pontos e alertas ainda nao oferecem drill-down consistente para as solicitacoes nem
  criacao de tarefa, agenda, visita, roteiro ou encaminhamento;
- a privacidade territorial precisa ser refinada para o menor recorte retornado e para permissoes
  distintas de agregado, exemplo e ponto individual;
- o mapa interativo depende de uma chave publica de tiles restrita por dominio e permanece
  bloqueado em producao; exportacao cartografica e seletores de camadas permanecem planejados;
- o painel nao possui telemetria de produto suficiente para medir adocao, investigacao e
  conversao em acao;
- RF-084 esta parcialmente coberto por filtros; exportacao de dashboard ainda depende de uma entrega especifica.
- RA-016 depende de um modelo explicito de agrupamento por evento urbano, alem da reincidencia por local ja entregue.
- RA-017 e RA-018 dependem da consolidacao analitica entre solicitacoes e producao legislativa.
- RA-019 e RA-020 dependem da implementacao completa de agenda, visitas e cobertura territorial de campo.
- RA-021, RA-022 e RA-023 ainda exigem metricas dedicadas de taxa de solucao por tema, qualidade cadastral e carga por equipe.
- RA-024 nao foi implementado; previsao de volume com faixa de incerteza deve entrar como incremento posterior.
- A geocodificacao local e aproximada e deve ser substituida ou calibrada por provedor geocodificador governado quando houver requisito de precisao cartografica.

## Direcao aprovada para evolucao

1. **5.1 Confiabilidade territorial:** filtros, proveniencia, qualidade, jurisdicao, privacidade e
   telemetria.
2. **5.2 Exploracao acionavel:** comparacao temporal, tabela, painel territorial e navegacao para
   os casos subjacentes.
3. **5.3 Cartografia e qualidade governadas:** mapa interativo, geocodificador, fila de revisao e
   exportacao agregada.
4. **5.4 Operacao integrada:** tarefas, agenda, visitas, roteiros, encaminhamentos e ciclo de vida
   do alerta.
5. **5.5 Inteligencia avancada:** cobertura, atuacao do mandato e previsao com incerteza somente
   apos os gates de qualidade, privacidade e adocao.

## Validacao

- testes backend cobrem dashboard operacional, relatorio mensal, geocodificacao e privacidade por agregacao;
- a evolucao para relatorios por periodo possui cobertura backend para payload executivo,
  exclusao do Parlamentar no ranking e resposta PDF, e cobertura frontend para os dois
  tipos de relatorio e seus indicadores;
- testes frontend cobrem a visualizacao dos indicadores, abas territoriais, mapa, relatorio mensal e acao de geocodificacao;
- testes PostgreSQL cobrem migracoes territoriais, campos de jurisdicao e ativacao de PostGIS.
