# Requisitos de IA, LLM e RAG

## Triagem

- **RIA-001** Classificar categoria e subcategoria.
- **RIA-002** Sugerir prioridade, impacto e urgência.
- **RIA-003** Extrair entidades: endereço, bairro, órgão, data, serviço, pessoas e protocolo.
- **RIA-004** Sugerir órgão ou secretaria competente.
- **RIA-005** Identificar texto potencialmente ofensivo sem bloquear o relato.
- **RIA-006** Detectar risco, emergência ou ameaça e acionar fluxo humano.
- **RIA-007** Produzir resumo de texto, áudio ou conversa.
- **RIA-008** Detectar duplicidade por similaridade semântica, proximidade geográfica e temporal.
- **RIA-009** Transcrever áudio preservando o arquivo original.
- **RIA-010** Realizar OCR com indicação de confiança.

## Assistência ao atendimento

- **RIA-020** Sugerir resposta ao cidadão com linguagem configurável.
- **RIA-021** Resumir histórico antes do atendimento.
- **RIA-022** Sugerir perguntas faltantes.
- **RIA-023** Identificar documentos necessários.
- **RIA-024** Propor próximos passos.
- **RIA-025** Nunca enviar resposta sem ação explícita do usuário, salvo automações previamente aprovadas.

## Produção legislativa

- **RIA-030** Gerar minuta com base em fatos selecionados.
- **RIA-031** Recuperar proposições semelhantes.
- **RIA-032** Identificar fundamentação normativa por recuperação tenant-safe, com citações versionadas e confirmação humana antes da aplicação.
- **RIA-033** Sugerir estrutura e justificativa.
- **RIA-034** Marcar trechos não fundamentados.
- **RIA-035** Impedir protocolo automático.

## RAG

- **RIA-040** Indexar documentos com metadados, vigência, órgão, tipo e versão. **Implementado na Release 4.**
- **RIA-041** Aplicar filtros por tenant e nível de acesso antes da recuperação. **Implementado na base documental e no endpoint de consulta.**
- **RIA-042** Retornar citações por documento, página ou seção. **Implementado no endpoint `/assistente/consultas`.**
- **RIA-043** Exibir data da fonte. **Implementado na gestão da base documental.**
- **RIA-044** Diferenciar conteúdo vigente, revogado, histórico e rascunho. **Implementado na Release 4.**
- **RIA-045** Recusar resposta conclusiva quando a recuperação for insuficiente. **Implementado com limiar mínimo de evidência.**
- **RIA-046** Registrar consulta, documentos recuperados e resposta. **Implementado com registro persistente e auditoria por hash.**
- **RIA-047** Avaliar risco de prompt injection nos documentos. **Implementado com sinalização por fonte recuperada.**
- **RIA-048** Não executar instruções encontradas dentro das fontes. **Implementado com política explícita e sanitização de trechos suspeitos.**
- **RIA-049** Permitir avaliação positiva, negativa e correção pelo usuário. **Implementado no endpoint de avaliação de consultas RAG.**

## Insights

- **RIA-060** Explicar método, período e base de cálculo.
- **RIA-061** Sinalizar correlação sem afirmar causalidade.
- **RIA-062** Apresentar intervalo de confiança ou qualidade do dado.
- **RIA-063** Evitar inferência de preferência político-eleitoral individual.
- **RIA-064** Alertar sobre amostra insuficiente.
- **RIA-065** Possibilitar auditoria da origem dos dados.

## Avaliação

Métricas mínimas:
- precisão e recall de classificação;
- taxa de aceitação de sugestões;
- groundedness das respostas;
- precisão das citações;
- taxa de alucinação;
- tempo de resposta;
- custo por execução;
- taxa de intervenção humana;
- desempenho por categoria e canal;
- testes de viés e privacidade.
