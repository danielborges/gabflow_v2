# Requisitos Funcionais

Prioridade: `MUST`, `SHOULD`, `COULD`.

## Fechamento SHOULD/COULD — Release 8.11

Os requisitos RF-005, RF-026, RF-034, RF-044 e RF-072 passam a ter implementação
tenant-facing. Preferências e segmentos são privados por usuário; briefings, heatmaps,
clusters e rotas usam apenas agregados não suprimidos e referências públicas confirmadas;
relatórios recorrentes aceitam somente destinatários internos ativos. Nenhuma dessas
funcionalidades usa endereço residencial ou dado individual de cidadão.

## Épico E01 — Acesso e configuração

| ID | Pri. | Requisito | Aceite resumido |
|---|---|---|---|
| RF-001 | MUST | Exibir o módulo apenas quando habilitado para o gabinete e permitido ao usuário. | Usuário sem permissão recebe `403`; menu não aparece. |
| RF-002 | MUST | Conceder acesso integral ao perfil `PARLAMENTAR`. | Mandato ativo e tenant correspondente são validados. |
| RF-003 | MUST | Permitir delegação granular e revogável a assessor. | Parlamentar escolhe capacidades, prazo e motivo. |
| RF-004 | MUST | Registrar todos os acessos, consultas sensíveis, comparações e exportações. | Evento de auditoria contém ator, tenant, ação, data e objeto. |
| RF-005 | SHOULD | Permitir preferências de cargo, eleição, território e indicadores. | Preferências são individuais e não vazam entre gabinetes. |

## Épico E02 — Ingestão e qualidade

| ID | Pri. | Requisito | Aceite resumido |
|---|---|---|---|
| RF-010 | MUST | Importar dados eleitorais oficiais do TSE. | Toda carga registra fonte, URL, hash, versão e data. |
| RF-011 | MUST | Suportar eleições municipais e gerais desde 2012, conforme disponibilidade. | Catálogo informa cobertura e granularidade. |
| RF-012 | MUST | Validar totalizações e rejeitar carga inconsistente. | Divergência bloqueante impede publicação. |
| RF-013 | MUST | Versionar cargas sem sobrescrever histórico. | Consulta pode informar versão utilizada. |
| RF-014 | SHOULD | Normalizar partidos, federações, municípios e candidatos entre eleições. | Vínculos ambíguos ficam pendentes de revisão. |
| RF-015 | SHOULD | Exibir nota de qualidade por território. | Nota considera completude, atualidade e consistência. |

## Épico E03 — Pesquisa e análise

| ID | Pri. | Requisito | Aceite resumido |
|---|---|---|---|
| RF-020 | MUST | Pesquisar candidato por nome, número, partido, cargo e eleição. | Busca tolera acentos e homônimos são diferenciados. |
| RF-021 | MUST | Detalhar votos por recorte disponível. | Município, zona, bairro, local e seção são suportados. |
| RF-022 | MUST | Exibir votos absolutos, participação percentual e posição. | Denominador e fórmula aparecem no tooltip. |
| RF-023 | MUST | Comparar até cinco candidatos. | Mesma eleição/cargo por padrão; exceções são explicitadas. |
| RF-024 | MUST | Comparar desempenho do mesmo candidato entre eleições. | Mudanças territoriais são tratadas e sinalizadas. |
| RF-025 | SHOULD | Salvar candidatos, territórios e análises como favoritos. | Favorito é privado ao usuário, salvo compartilhamento explícito. |
| RF-026 | SHOULD | Criar segmentos territoriais manuais. | Segmento contém apenas unidades geográficas agregadas. |

## Épico E04 — Mapas e painéis

| ID | Pri. | Requisito | Aceite resumido |
|---|---|---|---|
| RF-030 | MUST | Exibir mapa coroplético de votação. | Legenda, escala, fonte e ausência de dados são visíveis. |
| RF-031 | MUST | Alternar entre quantidade, percentual, ranking e variação. | Mapa e tabela permanecem sincronizados. |
| RF-032 | SHOULD | Sobrepor camadas agregadas do mandato. | Camadas respeitam limiar mínimo de privacidade. |
| RF-033 | SHOULD | Permitir filtros por período, tema, território e status. | Filtro é refletido em URL compartilhável autorizada. |
| RF-034 | COULD | Exibir heatmap, clusters e rotas de agenda. | Rotas não expõem endereço residencial de cidadão. |

## Épico E05 — Integração com operação do mandato

| ID | Pri. | Requisito | Aceite resumido |
|---|---|---|---|
| RF-040 | SHOULD | Exibir demandas agregadas por território e categoria. | Nenhum dado pessoal aparece na camada eleitoral. |
| RF-041 | SHOULD | Calcular resolutividade e SLA por território. | Fórmula e período são configuráveis e auditáveis. |
| RF-042 | SHOULD | Relacionar ações legislativas e entregas a territórios. | Cada vínculo possui evidência e responsável. |
| RF-043 | SHOULD | Calcular Índice de Cobertura Territorial. | Pesos configuráveis e explicação obrigatória. |
| RF-044 | COULD | Gerar briefing antes de visita territorial. | Inclui demandas, entregas, agenda e dados eleitorais agregados. |

## Épico E06 — IA e RAG

| ID | Pri. | Requisito | Aceite resumido |
|---|---|---|---|
| RF-050 | SHOULD | Gerar análise individual de candidato. | Texto cita eleição, fonte, versão e números usados. |
| RF-051 | SHOULD | Gerar comparativo entre candidatos. | Separa fatos, cálculos e hipóteses. |
| RF-052 | SHOULD | Responder perguntas em linguagem natural. | Resposta sem evidência suficiente declara limitação. |
| RF-053 | MUST | Bloquear inferência de voto ou ideologia de pessoa identificável. | Prompt inseguro é recusado e auditado. |
| RF-054 | MUST | Permitir avaliação e contestação de insight. | Feedback registra motivo e versão do modelo. |
| RF-055 | SHOULD | Produzir briefing e resumo executivo editáveis. | Conteúdo é rascunho e exige revisão humana. |

## Épico E07 — Cenários e metas

| ID | Pri. | Requisito | Aceite resumido |
|---|---|---|---|
| RF-060 | SHOULD | Criar cenário com premissas explícitas. | Data, autor, premissas e versão ficam armazenados. |
| RF-061 | SHOULD | Simular metas agregadas por território. | Resultado é rotulado como simulação. |
| RF-062 | SHOULD | Comparar cenário com resultado histórico. | Diferenças e fórmulas são exportáveis. |
| RF-063 | COULD | Aplicar análise de sensibilidade. | Exibe intervalo, não apenas valor pontual. |

## Épico E08 — Relatórios e exportações

| ID | Pri. | Requisito | Aceite resumido |
|---|---|---|---|
| RF-070 | MUST | Gerar relatório PDF de candidato, comparação ou território. | Contém fontes, filtros, data e marca d'água. |
| RF-071 | MUST | Exportar tabela em CSV/XLSX. | Exportação reproduz filtros e versão dos dados. |
| RF-072 | SHOULD | Agendar relatório recorrente. | Apenas destinatários internos autorizados. |
| RF-073 | SHOULD | Compartilhar relatório dentro do tenant. | Link expira e respeita revogação. |

## Épico E09 — Alertas e compromissos

| ID | Pri. | Requisito | Aceite resumido |
|---|---|---|---|
| RF-080 | SHOULD | Configurar alertas de qualidade, carga e indicadores. | Usuário escolhe canal e frequência. |
| RF-081 | SHOULD | Cadastrar compromissos públicos com prazo e evidências. | Histórico de alteração é imutável. |
| RF-082 | SHOULD | Exibir progresso por compromisso e território. | Status manual e evidências são distinguíveis de inferências. |

## Requisitos não funcionais

| ID | Requisito |
|---|---|
| RNF-001 | P95 de consulta agregada inferior a 2 s com cache aquecido. |
| RNF-002 | Geração de relatório assíncrona para operações acima de 10 s. |
| RNF-003 | Disponibilidade mensal alvo de 99,5% no plano inicial. |
| RNF-004 | WCAG 2.2 nível AA nas jornadas principais. |
| RNF-005 | Criptografia TLS em trânsito e criptografia de campos sensíveis em repouso. |
| RNF-006 | Teste automatizado de isolamento de tenant em toda rota protegida. |
| RNF-007 | RPO de 24 h e RTO de 8 h no plano inicial; configurável por plano. |
| RNF-008 | Logs sem CPF, endereço, telefone, conteúdo de demanda ou prompt pessoal bruto. |
| RNF-009 | APIs versionadas em `/api/v1`. |
| RNF-010 | Processamento aderente à LGPD e às regras eleitorais vigentes. |
## Épico E10 — Identidade eleitoral e exploração

| ID | Pri. | Requisito | Aceite resumido |
|---|---|---|---|
| RF-090 | MUST | Vincular automaticamente o parlamentar às candidaturas cujo CPF oficial corresponda deterministicamente ao CPF cadastrado. | Apenas impressão HMAC versionada é persistida na base eleitoral; CPF não aparece em API, log ou auditoria. |
| RF-091 | MUST | Restringir os combos operacionais de eleição às participações confirmadas do parlamentar titular. | Resultados, Comparações, GabIA, Simulador e Relatórios recebem a mesma lista centralizada. |
| RF-092 | MUST | Selecionar inicialmente a participação confirmada mais recente. | URL inválida ou eleição não vinculada não amplia o escopo. |
| RF-093 | MUST | Oferecer “Explorar outras eleições” como área separada de pesquisa pública. | O catálogo completo não altera o contexto operacional sem vínculo verificado ou contingencial. |
| RF-094 | MUST | Permitir confirmação manual somente quando o CPF estiver ausente, a fonte oficial indisponível ou houver divergência cadastral. | A contingência é exclusiva do titular, auditada e distinguível do vínculo automático. |
| RF-095 | MUST | Compartilhar o contexto do titular com assessores delegados. | O assessor não cria identidade eleitoral independente no mandato. |
| RF-096 | MUST | Sincronizar idempotentemente o cadastro oficial de candidaturas do TSE e reconciliar vínculos após atualização. | Falha do TSE preserva o último estado válido e não bloqueia login ou análises. |
| RF-097 | MUST | Impedir remoção direta de vínculo automático. | Correção de CPF ou revisão de divergência substitui exclusão manual e evita recriação silenciosa. |
