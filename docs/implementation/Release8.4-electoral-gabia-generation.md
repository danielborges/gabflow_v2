# Release 8.4 — GabIA Eleitoral fundamentada

Data de implementação: 2026-08-04.

## Lacuna encerrada

As Releases 8.0 e 8.1 criaram o contrato explicável, as recusas e a integração documental,
mas a análise eleitoral principal ainda era produzida apenas por regras determinísticas.
A Release 8.4 introduz geração real por modelo na jornada eleitoral sem entregar ao modelo
a responsabilidade pelos cálculos oficiais.

## Escopo entregue

- provedor `OLLAMA` específico para a GabIA Eleitoral, configurável por ambiente;
- saída obrigatoriamente estruturada em afirmações citadas, perguntas de investigação e
  limitações;
- contexto restrito ao snapshot eleitoral oficial e aos documentos RAG autorizados;
- JSON Schema com IDs de citação permitidos, limites de tamanho e temperatura zero;
- validação posterior de citações, valores quantitativos e linguagem causal;
- modelo, provedor e versão do prompt persistidos em cada insight;
- fallback determinístico seguro e explicitamente identificado quando o modelo falha;
- disponibilidade operacional exposta em `iaEleitoral` e exibida na interface;
- área renomeada para `GabIA Eleitoral`, com hipóteses visíveis e identificação da
  origem generativa do resultado.

## Limites de responsabilidade

O LLM não calcula votos, percentuais, ranking ou denominadores. Esses valores continuam
derivados do dataset publicado pelo mecanismo determinístico. O modelo pode redigir apenas
afirmações que citem evidências fornecidas e hipóteses na forma de perguntas. Toda saída
permanece como rascunho sujeito a revisão parlamentar.

## Configuração operacional

As chaves `ELECTORAL_AI_*` controlam ativação, provedor, modelo, prompt, timeout, limites de
contexto/saída e fallback. O Docker Compose reutiliza o modelo `qwen2.5:3b` já provisionado
pelo serviço Ollama do GabFlow.

## Homologação executada

- 24 testes eleitorais focados aprovados, incluindo contrato do provedor, fonte desconhecida,
  formato de hipóteses, fallback e integração completa via outbox;
- 67 testes de frontend aprovados, incluindo os estados generativo e determinístico;
- Ruff, ESLint, build de produção, OpenAPI YAML e Docker Compose validados;
- suíte global de backend sem regressão atribuível à release; o teste RAG intermitente de
  desempate falhou na execução conjunta e passou na repetição isolada;
- nenhuma migration nova foi necessária, pois os metadados de execução usam o snapshot e os
  campos de modelo já existentes no domínio de insights.
