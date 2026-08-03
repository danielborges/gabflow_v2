# Release 7.6 — Gate final do MVP de Inteligência Eleitoral

Data da execução: 2026-08-03
Ambiente: GabFlow local em Docker, PostgreSQL, API e worker de produção
Gabinete-piloto: Gabinete Demonstração
Parlamentar: Maurício Henrique Pinto de Oliveira Delgado

## Decisão

| Dimensão | Resultado | Decisão |
|---|---|---|
| Jornada autenticada | Pesquisa, análise, mapa, histórico, comparação, exportação e download concluídos | Aprovada |
| Desempenho | Maior P95: 114,06 ms; orçamento: 2.000 ms | Aprovado no ambiente-piloto |
| Acessibilidade técnica | Estrutura sem falhas detectadas; contraste corrigido e revalidado | Aprovada tecnicamente |
| Segurança e privacidade implementadas | Isolamento, criptografia, retenção, autorização e auditoria verificados | Aprovadas tecnicamente |
| Parecer jurídico e RIPD | Minuta concluída; assinaturas do controlador, encarregado e jurídico ausentes | Pendente de aprovação formal |

**Resultado global:** `APROVADO TECNICAMENTE / BLOQUEADO PARA PRODUÇÃO` até que as
assinaturas e decisões indicadas no RIPD sejam registradas. A ativação continua opt-in no
gabinete-piloto e não deve ser ampliada para outros tenants antes dessa aprovação.

## Jornada autenticada executada

1. Autenticação como usuário `representative` do Gabinete Demonstração.
2. Confirmação de que o menu Inteligência Eleitoral está disponível ao parlamentar.
3. Pesquisa de Maurício Delgado na eleição municipal de 2024/MG.
4. Consulta do resultado de Juiz de Fora: 5.453 votos, 2,07%, 10ª posição e denominador 263.159.
5. Exibição da fonte TSE, versão do dataset e metodologia.
6. Exibição do mapa com geometria oficial IBGE e sincronização com a tabela.
7. Histórico 2020/2024, incluindo mudança partidária e alerta de equivalência territorial pendente.
8. Comparação de Maurício Delgado e Vitinho no mesmo território e denominador.
9. Geração assíncrona de CSV de comparação pelo outbox e worker.
10. Download com JWT, capacidade `exportar` e token assinado temporário.

Evidência do artefato do gate:

- job: `216574d8-f6fc-41b0-99e7-911498fef2bc`;
- relatório: `61ecd5ea-11c8-4cdf-8b78-f9ae694c13f2`;
- SHA-256: `474d141994c6d238b294b5417a71dcdd17de0c3b60b86e4fdc39c3361755b232`;
- estado: `COMPLETED`;
- downloads auditados: 1.

Nenhuma delegação foi criada durante o gate.

## Medição de desempenho

Metodologia:

- requisições através do Nginx em `http://localhost:8081`;
- sessão parlamentar real com cookies JWT e CSRF;
- três requisições de aquecimento por endpoint;
- 40 amostras sequenciais por endpoint;
- medição de tempo de parede incluindo autorização, RLS, consulta e auditoria;
- percentil calculado pelo método nearest-rank.

| Operação | P50 | P95 | P99 | Máximo |
|---|---:|---:|---:|---:|
| Pesquisa de candidatura | 101,16 ms | 114,06 ms | 126,13 ms | 126,13 ms |
| Resultado territorial | 35,46 ms | 49,85 ms | 55,43 ms | 55,43 ms |
| Mapa oficial | 81,69 ms | 105,71 ms | 337,53 ms | 337,53 ms |
| Comparação | 44,87 ms | 65,81 ms | 328,61 ms | 328,61 ms |
| Lista privada de relatórios | 16,43 ms | 39,26 ms | 40,34 ms | 40,34 ms |

O critério P95 menor que 2 segundos foi atendido em todas as operações. Esta medição
qualifica o piloto funcional; ela não substitui ensaio de capacidade concorrente no ambiente
de produção.

## Revisão de acessibilidade

Foram verificados na tela eleitoral autenticada:

- idioma `pt-BR`, um `main` e uma navegação principal;
- hierarquia de títulos sem saltos;
- 52 controles visíveis com nome acessível;
- nenhuma imagem visível sem texto alternativo;
- nenhum `id` duplicado;
- tabelas com `caption` e células de cabeçalho;
- mapa exposto como imagem nomeada e territórios como botões acessíveis;
- nenhum link visível sem destino.

A primeira inspeção encontrou contraste de 3,62:1 nos botões ativos e 3,37:1 no marcador do
módulo. O token `--blue-600` foi alterado de `#1688ef` para `#0b6fc2`, alcançando 5,16:1
sobre branco. A reinspeção de 58 elementos textuais ativos encontrou zero ocorrência abaixo
dos limites WCAG AA de 4,5:1 ou 3:1 para texto grande.

## Condições para liberação

1. Controlador identifica formalmente a hipótese legal por finalidade e assina o RIPD.
2. Encarregado registra parecer, canal de atendimento e periodicidade de revisão.
3. Jurídico confirma o enquadramento do gabinete, o papel controlador/operador e os usos
   eleitorais permitidos.
4. Política de privacidade e registro das operações de tratamento incluem o módulo.
5. Runbook de incidente, revogação e rollback recebe responsáveis nominais.
6. É realizado teste de carga concorrente no ambiente que antecede produção.
7. O módulo permanece sem integração com dados pessoais de cidadãos até o Incremento 5
   concluir limiar, supressão, finalidade e nova revisão do RIPD.
