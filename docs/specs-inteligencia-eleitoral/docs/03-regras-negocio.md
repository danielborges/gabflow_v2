# Regras de Negócio

## Acesso e delegação

- RN-001: o módulo depende de feature flag do plano e do gabinete.
- RN-002: `PARLAMENTAR` possui acesso integral ao próprio mandato.
- RN-003: acesso de assessor exige delegação explícita, granular, temporária e revogável.
- RN-004: `ADMIN_GERAL` administra disponibilidade, mas não lê análises de gabinetes por padrão.
- RN-005: todo recurso deve carregar `tenant_id`; o backend nunca aceita o tenant apenas do payload.
- RN-006: um parlamentar não acessa dados privados de outro mandato, ainda que pertençam ao mesmo partido.

## Fontes e cálculos

- RN-010: dados eleitorais devem manter proveniência e hash da carga.
- RN-011: resultado oficial prevalece sobre qualquer captura paralela.
- RN-012: percentuais devem exibir denominador: votos válidos, comparecimento, eleitorado ou total do candidato.
- RN-013: comparações históricas devem sinalizar alteração de limites territoriais, partidos ou cargo.
- RN-014: bairros inferidos a partir de locais de votação devem ser rotulados como mapeamento derivado.
- RN-015: valores com fonte ausente ou divergente não podem alimentar insight de IA sem alerta.

## Privacidade, LGPD e ética

- RN-020: é proibido associar resultado de seção a pessoa identificada ou identificável.
- RN-021: dados de atendimento só podem aparecer no módulo de forma agregada.
- RN-022: aplicar limiar de privacidade configurável; padrão: ocultar grupos com menos de 10 ocorrências.
- RN-023: categorias sensíveis devem ser generalizadas ou excluídas das correlações.
- RN-024: não inferir ideologia, religião, saúde, raça, orientação sexual ou intenção de voto.
- RN-025: nenhuma recomendação pode condicionar atendimento público a desempenho eleitoral.
- RN-026: exportação com dados institucionais agregados exige finalidade e gera auditoria.
- RN-027: prompts e respostas com risco devem ser retidos apenas pelo período mínimo de segurança.

## IA

- RN-030: todo insight deve separar `fatos`, `cálculos`, `hipóteses` e `limitações`.
- RN-031: toda afirmação quantitativa deve citar dataset, versão e filtros.
- RN-032: a IA não pode inventar causa para correlação observada.
- RN-033: conteúdo é rascunho e deve informar que exige revisão humana.
- RN-034: versão do modelo, template e documentos recuperados devem ser auditáveis.
- RN-035: feedback negativo deve permitir ocultar o insight e abrir revisão.

## Simulações

- RN-040: cenário não altera dados oficiais.
- RN-041: toda simulação deve mostrar premissas e autor.
- RN-042: cenários compartilhados são somente leitura, salvo cópia.
- RN-043: projeções devem usar intervalo quando houver incerteza estimada.
- RN-044: é proibido apresentar simulação como pesquisa eleitoral registrada.

## Relatórios

- RN-050: relatório inclui fonte, versão, filtros, data/hora, autor e aviso metodológico.
- RN-051: links compartilhados expiram em até sete dias por padrão.
- RN-052: download e compartilhamento são auditados.
- RN-053: relatório revogado deixa de ser acessível imediatamente.

## Índice de Cobertura Territorial

Versão inicial sugerida:

`ICT = 0,30 × demanda_normalizada + 0,25 × atraso_normalizado + 0,25 × lacuna_entregas + 0,20 × baixa_presença`

Onde `baixa_presença` significa baixa presença institucional registrada em agenda/ações, e não baixa votação. Os pesos são configuráveis e a fórmula deve ficar visível.

## Matriz de permissões

| Capacidade | Parlamentar | Assessor delegado | Admin gabinete | Admin geral |
|---|---:|---:|---:|---:|
| Consultar dados públicos | Sim | Opcional | Opcional | Não por padrão |
| Ver camadas do mandato | Sim | Opcional | Opcional | Não |
| Criar comparativo | Sim | Opcional | Opcional | Não |
| Usar IA | Sim | Opcional | Opcional | Não |
| Criar cenário | Sim | Opcional | Não por padrão | Não |
| Exportar | Sim | Opcional | Não por padrão | Não |
| Delegar acesso | Sim | Não | Não | Não |
| Configurar módulo | Não | Não | Sim | Sim |
| Configurar fontes globais | Não | Não | Não | Sim |
