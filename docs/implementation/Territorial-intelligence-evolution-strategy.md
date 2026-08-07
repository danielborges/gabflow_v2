# Estratégia de evolução da Inteligência Territorial

## Status e objetivo

**Status:** estratégia aprovada para planejamento.

Este documento orienta a evolução da feature **Visão Geral > Inteligência territorial**
a partir da base entregue na Release 5. O objetivo é transformar um painel predominantemente
descritivo em um fluxo operacional que permita ao gabinete identificar um sinal, compreender
os casos que o originaram, executar uma ação e acompanhar o resultado.

Esta estratégia complementa, sem reescrever o histórico de entrega, o documento
[`Release5-territorial-intelligence.md`](Release5-territorial-intelligence.md).

## Diagnóstico da implementação atual

### Capacidades disponíveis

- filtros por período, categoria, canal, território e órgão;
- cobertura geográfica, hotspots, mapa de calor e pontos geocodificados;
- jurisdição configurável com limites e malha GeoJSON do IBGE;
- agregações PostGIS quando a extensão está disponível;
- alertas determinísticos de reincidência e crescimento anormal;
- supressão de grupos pequenos e isolamento por tenant;
- indicadores operacionais e relatório mensal com evidências por protocolo.

### Lacunas de valor para o usuário

1. Hotspots, pontos e alertas informam, mas não abrem os casos que explicam o sinal.
2. Não há ação contextual para criar tarefa, agenda, visita, roteiro ou encaminhamento.
3. Os rankings privilegiam volume absoluto e não mostram atraso, taxa de solução, tempo ou
   variação contra um período comparável.
4. Coordenadas aproximadas e verificadas não são diferenciadas, o que torna ambígua a métrica
   de cobertura geográfica.
5. O mapa não oferece seleção de território, camadas, zoom, drill-down ou navegação acessível
   equivalente fora do mapa.
6. Não existe telemetria de produto para medir adoção, investigação e conversão em ação.

### Riscos técnicos que antecedem novas análises

- o heatmap PostGIS deve aplicar exatamente o mesmo recorte dos demais indicadores;
- geocodificação aproximada não pode usar um centro fixo nem ser apresentada como coordenada
  verificada;
- protocolo e coordenada individual exigem autorização e proteção por célula geográfica, não
  apenas pelo total do território;
- o cálculo do painel não deve depender indefinidamente de carregar toda a coleção do tenant em
  memória;
- filtros inválidos devem produzir erro explícito, em vez de serem silenciosamente ignorados.

## Princípios de produto

1. **Do sinal à ação:** todo insight deve oferecer investigação e próximo passo.
2. **Confiança antes de sofisticação:** nenhuma previsão substitui qualidade e proveniência.
3. **Comparação antes de ranking:** volume isolado não caracteriza prioridade territorial.
4. **Privacidade por desenho:** o menor recorte exibido deve respeitar limiar, finalidade e perfil.
5. **Explicabilidade operacional:** período, base, regra, cobertura e limitações ficam visíveis.
6. **Mapa como uma das interfaces:** tabela e painel lateral devem oferecer funcionalidade
   equivalente para acessibilidade e trabalho intensivo.
7. **IA somente sobre agregados rastreáveis:** briefing ou recomendação deve citar métricas e
   protocolos autorizados, sem perfil individual ou propensão eleitoral.

## Decisões que a feature deve apoiar

| Perfil | Decisão principal | Saída operacional |
| --- | --- | --- |
| Chefia de gabinete | Onde redistribuir equipe ou escalar atendimento | tarefa, responsável, prazo e acompanhamento |
| Trabalhador do gabinete | Quais casos investigar ou atender em conjunto | lista filtrada de solicitações e roteiro de visita |
| Parlamentar | Quais territórios exigem presença, articulação ou fiscalização | briefing territorial e agenda |
| Administração | Onde há baixa qualidade territorial | fila de correção, fonte e confiança da coordenada |

## Experiência-alvo

O fluxo principal será:

1. selecionar período e comparação;
2. identificar território, tema ou alerta com mudança relevante;
3. abrir um painel territorial com métricas, causas e solicitações subjacentes;
4. navegar para a grid de solicitações com filtros preservados;
5. criar tarefa, agenda, visita, encaminhamento ou acompanhamento;
6. revisar posteriormente o estado da ação e a evolução do indicador.

### Visão territorial mínima

Para cada território elegível, apresentar:

- total, abertas e atrasadas;
- percentual de atraso e taxa de solução;
- tempo mediano de primeira resposta e resolução;
- variação contra o período anterior equivalente;
- categorias, órgãos e responsáveis mais associados;
- qualidade do dado territorial;
- alertas ativos e ações em andamento;
- acesso às solicitações subjacentes, respeitando permissões.

## Plano de desenvolvimento

### Incremento 5.1 — Confiabilidade territorial

**Duração indicativa:** 1 sprint.

**Entregas**

- aplicar o mesmo objeto de filtros a contadores, hotspots, pontos e heatmap PostGIS;
- substituir cobertura única por território identificado, coordenada aproximada e coordenada
  verificada;
- registrar origem, método, confiança e instante da geocodificação;
- remover qualquer centro geográfico fixo e usar somente jurisdição configurada ou provedor
  governado;
- validar coordenadas dentro da jurisdição e criar estado para exceções;
- aplicar privacidade por célula e perfil antes de retornar pontos individuais;
- retornar `422` para filtros territoriais inválidos;
- adicionar telemetria sem conteúdo pessoal para abertura, filtro, investigação e ação.

**Critérios de aceite**

- o mesmo filtro produz totais coerentes em todas as representações;
- coordenada aproximada nunca aumenta o indicador de coordenadas verificadas;
- nenhum ponto fora da jurisdição é tratado silenciosamente como válido;
- usuário sem permissão recebe somente agregados elegíveis;
- testes cobrem PostGIS, fallback, filtros combinados, privacidade e múltiplas jurisdições.

### Incremento 5.2 — Exploração acionável

**Duração indicativa:** 2 sprints.

**Entregas**

- período padrão de 30 dias e comparação com os 30 dias anteriores;
- tabela territorial ordenável com volume, atraso, solução, tempos e tendência;
- mapa e tabela sincronizados por seleção;
- painel lateral com categorias, órgãos, responsáveis, alertas e amostra;
- ações **Ver solicitações** e **Ver exemplos do alerta**, levando filtros assinados ou
  validados para a grid;
- estados explícitos de amostra insuficiente, ausência de comparação e baixa qualidade;
- visões salvas por usuário sem armazenar conteúdo pessoal.

**Critérios de aceite**

- todo hotspot ou alerta permite chegar aos casos autorizados em no máximo duas ações;
- filtros e período são preservados ao navegar para Solicitações;
- a tabela oferece funcionalidade equivalente à seleção no mapa;
- a comparação informa base, janela, método e tamanho da amostra;
- eventos de produto permitem construir o funil `abertura > investigação > ação`.

### Incremento 5.3 — Cartografia e qualidade governadas

**Duração indicativa:** 2 a 3 sprints.

**Entregas**

- mapa interativo com polígonos oficiais, agrupamento de pontos e camadas configuráveis;
- geocodificador governado com cache, limite de uso, auditoria e política de retenção;
- fila administrativa de endereços não resolvidos, ambíguos ou fora da jurisdição;
- painel de qualidade por território, origem e método;
- atualização e versionamento da malha territorial;
- exportação agregada em CSV e imagem/PDF com período, filtros e metodologia.

**Critérios de aceite**

- toda coordenada possui fonte e nível de confiança consultáveis;
- correções administrativas são auditadas e recalculam agregados afetados;
- mapa, tabela e exportação usam o mesmo contrato analítico;
- nenhuma exportação inclui ponto ou protocolo sem autorização explícita.

### Incremento 5.4 — Operação territorial integrada

**Duração indicativa:** 2 sprints.

**Entregas**

- criar tarefa, agenda, visita, roteiro ou encaminhamento a partir do território/alerta;
- vincular a ação ao recorte, filtros, solicitações e regra que a originaram;
- definir responsável, prazo, estado e evidência de conclusão;
- acompanhar alertas novos, em análise, com ação, resolvidos ou descartados com justificativa;
- notificações configuráveis por território, tema, severidade e frequência;
- briefing territorial agregado antes de visitas.

**Critérios de aceite**

- ação criada preserva proveniência do insight e histórico auditável;
- o painel mostra responsável, prazo e resultado da ação;
- alertas duplicados são correlacionados, sem criar trabalho repetido;
- encerramento de uma ação exige resultado ou justificativa.

### Incremento 5.5 — Inteligência avançada

**Início condicionado aos gates dos incrementos anteriores.**

**Possíveis entregas**

- índice de presença e cobertura de visitas com fórmula versionada;
- relação entre demandas, fiscalização, agenda e produção legislativa;
- taxa de solução por tema, território e órgão;
- previsão de volume com intervalo de incerteza e baseline reproduzível;
- briefing assistido por IA, limitado a dados agregados e evidências autorizadas.

**Gates obrigatórios**

- qualidade territorial mensurável e estável;
- comparação temporal confiável;
- adoção e conversão em ação comprovadas;
- avaliação de privacidade e revisão humana;
- baseline determinístico que permita medir ganho da solução avançada.

## Backlog executável e sequência

O desenvolvimento deve começar pelo incremento 5.1. Itens posteriores não entram no mesmo PR
de confiabilidade, para permitir validação e rollback isolados.

| Ordem | Item | Resultado verificável | Dependência |
| --- | --- | --- | --- |
| 1 | `TERR-5.1-01` Contexto analítico único | contadores e consultas recebem filtros normalizados e permissões | nenhuma |
| 2 | `TERR-5.1-02` Heatmap filtrado | PostGIS e fallback retornam o mesmo recorte e contrato | 5.1-01 |
| 3 | `TERR-5.1-03` Proveniência geográfica | modelo registra origem, método, confiança, verificação e atualização | migração |
| 4 | `TERR-5.1-04` Jurisdição e revisão | coordenadas externas/ambíguas não entram como verificadas | 5.1-03 |
| 5 | `TERR-5.1-05` Política de privacidade | agregado, exemplo e ponto obedecem célula e perfil | 5.1-01 |
| 6 | `TERR-5.1-06` Cobertura revisada | interface separa território, aproximação, verificação e pendência | 5.1-03/04 |
| 7 | `TERR-5.1-07` Telemetria minimizada | funil territorial mensurável sem conteúdo pessoal | contrato de eventos |
| 8 | `TERR-5.2-01` Comparação temporal | período atual e anterior têm denominadores e método | 5.1 concluído |
| 9 | `TERR-5.2-02` Tabela e detalhe | seleção acessível mostra métricas, causas e qualidade | 5.2-01 |
| 10 | `TERR-5.2-03` Navegação para casos | grid abre com filtros preservados e autorizados | 5.2-02 |
| 11 | `TERR-5.2-04` Alertas investigáveis | exemplos, regra e estado de investigação ficam disponíveis | 5.2-03 |
| 12 | `TERR-5.3-01` Mapa interativo | mapa e tabela compartilham seleção e contrato | 5.2 concluído |
| 13 | `TERR-5.3-02` Geocodificador governado | localização real, auditável, limitada e revisável | decisão de provedor |
| 14 | `TERR-5.3-03` Exportação agregada | arquivo reproduz período, filtros, método e supressão | 5.3-01 |
| 15 | `TERR-5.4-01` Entidade de ação territorial | insight vincula ação, responsável, prazo e evidência | modelo e migração |
| 16 | `TERR-5.4-02` Integrações operacionais | tarefa, agenda, visita, roteiro e encaminhamento reutilizam serviços existentes | 5.4-01 |
| 17 | `TERR-5.4-03` Ciclo de vida do alerta | novo, análise, ação, resolvido e descartado são auditáveis | 5.4-01 |

### Estado do incremento 5.1

Implementação iniciada em 07/08/2026, com o primeiro corte funcional cobrindo:

- contexto de filtros validado, devolvido no contrato e aplicado também ao heatmap PostGIS e ao
  fallback local;
- proveniência persistida por solicitação, com origem, método, confiança, verificação, estado e
  data da geocodificação;
- remoção do centro geográfico fixo e uso obrigatório do centro ou dos limites governados do
  tenant;
- validação de limites e geometria da jurisdição, com estados distintos para aproximação,
  verificação, ambiguidade, ausência e ponto externo;
- limiar de privacidade calculado por célula geográfica e autorização distinta para agregados,
  exemplos e pontos individuais;
- interface com métricas separadas de território identificado, coordenada aproximada,
  coordenada verificada, pendência e revisão;
- telemetria minimizada para abertura, filtro, investigação e início de ação, sem protocolo,
  coordenada ou conteúdo da solicitação.

Antes do Gate A ainda são necessárias a homologação visual no Gabinete Demonstração, a execução
dos testes PostgreSQL/PostGIS no pipeline e a coleta do baseline de uso e latência.

### Estado do incremento 5.2

Implementação iniciada em 07/08/2026, cobrindo:

- período padrão de 30 dias e comparação com a janela anterior equivalente, com amostras,
  método e estados de comparação disponíveis no contrato;
- tabela territorial ordenável com volume, atraso, solução, medianas de resposta e resolução,
  tendência e qualidade geográfica;
- seleção sincronizada entre mapa, tabela e painel lateral, com alternativa acessível por
  teclado;
- painel de investigação com categorias, órgãos, responsáveis, alertas e exemplos autorizados;
- navegação em até duas ações para a grid de Solicitações, preservando período, canal,
  categoria, território e órgão em filtros novamente validados no servidor;
- estados explícitos para ausência de comparação, amostra insuficiente e baixa qualidade;
- visões salvas limitadas e isoladas por tenant e usuário, contendo somente filtros permitidos;
- evento `INVESTIGACAO_INICIADA` integrado ao funil territorial.

### Homologação e decisão do Gate B

O Gate B foi **aprovado em 07/08/2026** após homologação navegada no Gabinete Demonstração com
os perfis `ADMIN`, `MANAGER` e `STAFF`. Foram validados comparação temporal, sincronização entre
mapa, tabela e painel, ordenação, filtros, visão salva isolada por usuário, drill-down com
contexto preservado e supressão de pontos/exemplos para `STAFF`.

A homologação encontrou e corrigiu a distribuição temporal correlacionada ao território na
massa sintética e o carregamento relacional em cascata do painel. Após a otimização, 20
consultas autenticadas apresentaram mediana de 359,3 ms e P95 de 550,2 ms, abaixo do orçamento
de 1,5 segundo. A evidência completa está em
`docs/implementation/Territorial-intelligence-gate-b-homologation.md`.

### Definition of Done por item

- requisito e cenário de aceitação vinculados;
- contrato OpenAPI atualizado quando houver mudança de API;
- migração reversível e tenant-safe quando houver persistência;
- testes unitários, de integração, privacidade e autorização proporcionais ao risco;
- estados de carregamento, vazio, erro, amostra insuficiente e baixa qualidade;
- acessibilidade por teclado e alternativa textual ao mapa;
- telemetria e auditoria sem dados proibidos;
- documentação operacional e estratégia de rollback;
- validação no Gabinete Demonstração antes da promoção.

### Marcos de decisão

- **Gate A — fim de 5.1:** filtros coerentes, proveniência disponível, privacidade aprovada e
  baseline de uso coletando dados.
- **Gate B — fim de 5.2:** usuários conseguem chegar do sinal aos casos e a conversão em
  investigação pode ser medida.
- **Gate C — fim de 5.3:** qualidade cartográfica e exportação atendem requisitos operacionais e
  de proteção de dados.
- **Gate D — fim de 5.4:** ações territoriais têm responsável, prazo, evidência e resultado.
- **Gate E — entrada em 5.5:** somente após Gates A–D e revisão explícita de privacidade,
  metodologia e ganho de produto.

## Arquitetura e contratos

### Contrato analítico único

O backend deve produzir um `TerritorialQueryContext` interno com tenant, período, comparação,
categoria, canal, território, órgão, status, prioridade, responsável e permissões. Todas as
consultas e agregações territoriais devem consumir esse contexto.

Cada resposta territorial deve expor:

- `periodo` e `comparacao`;
- `filtrosAplicados`;
- `metodo` e `versaoMetodo`;
- `qualidadeDados`;
- `privacidade` e grupos suprimidos;
- `geradoEm`;
- token de navegação para o detalhamento, quando autorizado.

### Leitura escalável

- mover filtros e agregações para consultas SQL tenant-safe;
- evitar carregar todas as solicitações e relacionamentos na memória;
- considerar tabelas agregadas ou views materializadas somente após medir volume e latência;
- definir orçamento inicial de P95 de 1,5 segundo para consulta territorial comum;
- invalidar ou atualizar agregados de modo idempotente quando solicitação, território ou
  coordenada mudar.

### Privacidade e autorização

- separar permissão para visualizar agregados, exemplos e pontos individuais;
- calcular limiar no menor recorte retornado;
- não persistir termos de busca, protocolos ou coordenadas na telemetria de produto;
- registrar auditoria para exportação, correção geográfica e criação de ação;
- proibir inferência de preferência ou propensão eleitoral individual.

## Estratégia de testes

- testes unitários das métricas, comparação e regras de qualidade;
- testes de contrato garantindo que todos os componentes respeitam os mesmos filtros;
- testes PostgreSQL/PostGIS com múltiplos tenants e jurisdições;
- testes de privacidade por território, célula, perfil e exportação;
- testes frontend de drill-down, preservação de filtros e equivalência mapa/tabela;
- testes de integração `alerta > solicitação > ação > acompanhamento`;
- testes de carga com volumes progressivos e orçamento P95;
- regressão visual e acessibilidade por teclado para mapa, tabela e painel lateral.

## Rollout

1. disponibilizar 5.1 em feature flag para o gabinete de demonstração;
2. comparar métricas antigas e novas e revisar divergências conhecidas;
3. liberar 5.2 para um pequeno grupo de gabinetes, com entrevistas orientadas a tarefas;
4. promover por tenant somente após cumprir qualidade, privacidade, latência e adoção;
5. manter rollback para o painel anterior enquanto o contrato novo estiver em estabilização.

## Métricas de sucesso

As metas definitivas devem ser calibradas após a instrumentação do incremento 5.1. Metas
iniciais para validação:

- pelo menos 90% das solicitações com território resolvido;
- menos de 2% das coordenadas verificadas fora da jurisdição;
- pelo menos 25% das sessões territoriais convertidas em investigação ou ação;
- pelo menos 60% dos alertas relevantes tratados em até sete dias;
- redução de 50% no tempo para preparar briefing territorial;
- P95 menor que 1,5 segundo no recorte operacional homologado;
- zero exposição de grupo abaixo do limiar ou de ponto sem autorização.

## Fora de escopo imediato

- previsão de voto ou propensão política individual;
- recomendação automática sem revisão humana;
- priorização de atendimento baseada em afinidade eleitoral;
- causalidade inferida somente por correlação territorial;
- IA generativa antes da estabilização dos contratos, métricas e qualidade territorial.
