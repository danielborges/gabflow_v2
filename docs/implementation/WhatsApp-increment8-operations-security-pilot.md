# Incremento 8 - Operação, segurança e piloto

## Entrega

O incremento fecha o ciclo de implantação do WhatsApp com um gate de piloto verificável por tenant. A aplicação agora reúne saúde do pipeline, SLOs, evidências, decisão de go-live e pausa segura de saída no cockpit administrativo.

## Controles implementados

- checklist interno versionado com oito gates e evidência obrigatória para aprovação;
- hash SHA-256 da referência de evidência e auditoria minimizada, sem copiar observações para o log de auditoria;
- estados `DRAFT`, `READY`, `RUNNING`, `PAUSED` e `COMPLETED` por tenant;
- início e retomada condicionados aos gates externos do Incremento 0, aos gates internos e à saúde operacional;
- pausa operacional revalidada tanto no enfileiramento quanto no dispatch; confirmação de opt-out continua permitida;
- telemetria de ACK, início de processamento, falhas, quarentena, outbox, entrega, opt-out, handoff e mídia bloqueada;
- endpoint Prometheus sem dimensões de tenant e health check protegido por token;
- logs estruturados para assinatura inválida e payload acima do limite, sem conteúdo do webhook;
- dashboard CloudWatch para fila, DLQ e estado dos alarmes, com alarmes M-de-N e `notBreaching` para dados ausentes.

## SLOs iniciais

| Indicador | Meta |
| --- | --- |
| Disponibilidade do pipeline | 99,9% |
| ACK do webhook | p95 abaixo de 500 ms |
| Início do processamento | 99% em até 30 s |
| Idade máxima observada da outbox | 300 s |
| Conflito entre tenants | zero tolerado |

Os valores são configuráveis por ambiente. Métricas Prometheus têm cardinalidade fixa; cortes por tenant são exibidos somente na API administrativa autenticada.

## Operação do piloto

1. O administrador registra uma referência rastreável para cada evidência.
2. O sistema confirma aprovações externas e saúde do período.
3. `Iniciar piloto` fica disponível somente com os três grupos em condição positiva.
4. Uma anomalia pode ser contida por `Pausar saídas`, sempre com motivo.
5. A retomada repete os gates; a conclusão mantém as saídas pausadas até a decisão de rollout.

## Privacidade e segurança

O dashboard não usa telefone, mensagem, contato, tenant ou identificador de evento como dimensão de métrica. A referência da evidência deve apontar para um repositório corporativo autorizado, sem incorporar credenciais ou dados pessoais. Segredos continuam resolvidos em runtime pelo cofre configurado e não fazem parte deste fluxo.

## Validação

Há testes para evidência obrigatória, bloqueio de início prematuro, transição do piloto, pausa, isolamento entre tenants, proteção dos endpoints operacionais, métricas de baixa cardinalidade e persistência da duração do ACK.

A primeira execução de homologação local está registrada em
[WhatsApp-pilot-homologation-2026-08-12.md](WhatsApp-pilot-homologation-2026-08-12.md). A
implantação posterior do staging AWS e os gates externos remanescentes estão em
[AWS-staging-deployment-2026-08-12.md](AWS-staging-deployment-2026-08-12.md).
