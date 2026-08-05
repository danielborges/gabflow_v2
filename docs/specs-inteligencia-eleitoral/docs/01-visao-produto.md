# Visão do Produto

## Problema

Parlamentares consultam resultados eleitorais em fontes dispersas e têm dificuldade para transformar números por território em decisões verificáveis. Ferramentas eleitorais tradicionais analisam votos, mas geralmente não conectam o cenário eleitoral à operação cotidiana do mandato: demandas dos cidadãos, agenda territorial, ações legislativas e entregas.

## Proposta

O módulo **Inteligência Eleitoral e Territorial** centraliza dados oficiais, análises geográficas, comparativos, relatórios e IA explicável. Seu diferencial é correlacionar apenas dados agregados do resultado eleitoral com indicadores igualmente agregados da atuação do mandato.

## Usuário primário

`PARLAMENTAR`: vereador, deputado estadual, deputado federal ou senador associado a um mandato ativo no GabFlow.

## Usuários administrativos

- `ADMIN_GERAL`: habilita módulo, fontes, limites e feature flags, sem acesso automático ao conteúdo político de cada gabinete.
- `ADMIN_GABINETE`: configura permissões operacionais e fontes, mas não acessa análises reservadas ao Parlamentar sem delegação explícita.

## Resultados esperados

- Reduzir o tempo para produzir diagnóstico territorial.
- Identificar crescimento, retração, concentração e dispersão de votação.
- Priorizar presença institucional com base em lacunas de atendimento e cobertura, não em perfilamento individual.
- Demonstrar entregas do mandato por território.
- Gerar relatórios auditáveis para reuniões internas.

## Capacidades equivalentes ao mercado

- Histórico eleitoral por candidato e eleição.
- Detalhamento por município, zona, bairro, local e seção, conforme disponibilidade oficial.
- Comparação entre candidatos e eleições.
- Favoritos.
- Mapas temáticos.
- Relatórios PDF e exportações tabulares.
- Insights de IA.

## Diferenciais GabFlow

### 1. Mapa integrado do mandato

Sobreposição, em camadas agregadas, de:

- desempenho eleitoral;
- volume e tema das demandas cidadãs;
- SLA e resolutividade;
- agenda e visitas;
- ações legislativas;
- obras, entregas e compromissos públicos.

### 2. Índice de cobertura territorial

Indicador configurável que mostra onde há demanda pública relevante e baixa presença/entrega institucional. Não recomenda tratamento desigual por preferência política.

### 3. Linha do tempo eleitoral e do mandato

Compara eleições e marcos do mandato, mostrando tendências e eventos públicos relacionados, sem afirmar causalidade sem evidência.

### 4. Simulador de cenários

Permite aplicar hipóteses explícitas — comparecimento, votos válidos, transferência agregada e meta regional — com premissas visíveis. Resultado sempre rotulado como simulação, nunca previsão garantida.

### 5. Polígrafo de promessas

Conecta compromissos públicos cadastrados a ações, documentos e entregas verificáveis, produzindo percentual de progresso e evidências.

### 6. Assistente “GabIA”

Assistente analítico do GabFlow para:

- explicar variações;
- produzir briefing territorial;
- responder perguntas com RAG;
- sugerir perguntas de investigação;
- criar resumo executivo;
- apontar qualidade ou ausência de dados.

O nome é provisório e configurável.

### 7. Alertas inteligentes

- Nova carga oficial disponível.
- Mudança material em indicador.
- Território com crescimento de demanda e piora de SLA.
- Compromisso público próximo do prazo.
- Relatório agendado concluído.

## Fora do escopo

- Identificar em quem uma pessoa votou.
- Classificar cidadãos por provável preferência política.
- Direcionar serviço público com base em apoio eleitoral.
- Capturar dados privados de redes sociais sem base legal.
- Produzir propaganda eleitoral automaticamente.
- Substituir pesquisa eleitoral registrada ou resultado oficial.

## Indicadores de sucesso

- Tempo médio para gerar diagnóstico.
- Percentual de territórios com dados íntegros.
- Usuários ativos mensais do perfil Parlamentar.
- Relatórios gerados e compartilhados.
- Insights aceitos, descartados e contestados.
- Percentual de insights com fontes e explicação completas.
- Incidentes de isolamento de tenant: meta zero.
## Contexto eleitoral do parlamentar — Release 8.9

Os fluxos de Resultados, Comparações, GabIA, Simulador, Relatórios e camadas do
mandato usam exclusivamente eleições associadas ao parlamentar por reconciliação
determinística entre o CPF cadastrado e o cadastro oficial sincronizado do TSE. O CPF
não é exposto nem duplicado na base eleitoral: a comparação utiliza impressão
criptográfica versionada. O sistema nunca presume a identidade por nome, partido,
número ou similaridade textual.

O catálogo completo permanece disponível em **Explorar outras eleições**, uma área
de pesquisa pública e claramente separada. Nela o usuário pode localizar eleições e
candidaturas. A confirmação manual somente aparece como contingência quando o CPF
está ausente, a fonte oficial está indisponível ou há divergência cadastral. Consultas
exploratórias não alteram automaticamente o contexto operacional, não selecionam adversários e não criam
cenários ou análises em nome do mandato.
