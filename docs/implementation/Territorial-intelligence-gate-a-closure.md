# Encerramento formal — Gate A da Inteligência Territorial

**Data:** 10/08/2026

**Escopo:** incremento 5.1 — Confiabilidade territorial

**Decisão:** **APROVADO E ENCERRADO**

## Critérios e evidências

| Critério do gate | Evidência | Resultado |
| --- | --- | --- |
| filtros coerentes | o mesmo recorte validado alimenta indicadores, pontos, heatmap PostGIS e fallback local | aprovado |
| proveniência geográfica | origem, método, confiança, verificação, estado e data da geocodificação são persistidos | aprovado |
| jurisdição e qualidade | centro e limites pertencem ao tenant; pontos ambíguos, externos e não resolvidos são distinguidos | aprovado |
| privacidade | limiar mínimo de três registros é aplicado por célula e pontos/exemplos dependem do perfil | aprovado |
| telemetria e baseline | funil territorial minimizado está ativo; a homologação registrou uso e P95 de 550,2 ms | aprovado |
| PostgreSQL/PostGIS | migração, coluna espacial e índice GiST foram validados em banco efêmero isolado | aprovado |
| homologação navegada | perfis `ADMIN`, `MANAGER` e `STAFF` foram exercitados no Gabinete Demonstração | aprovado |

A homologação navegada e o baseline de desempenho estão detalhados em
[`Territorial-intelligence-gate-b-homologation.md`](Territorial-intelligence-gate-b-homologation.md).
Embora registrados no Gate B, eles também satisfazem os itens de interface, autorização,
telemetria e latência que ainda estavam abertos no checklist do Gate A.

## Correção da metodologia histórica

A comparação temporal foi corrigida e versionada como `5.2.1`. Cada coorte agora é avaliada
no corte exclusivo imediatamente posterior ao último dia de sua própria janela. Assim:

- o status histórico é reconstituído pela trilha de mudanças;
- atraso considera prazo e status existentes naquele corte;
- respostas e encerramentos posteriores ao corte não alteram retroativamente a janela;
- cada solicitação contribui uma única vez para a mediana de resolução, pelo primeiro desfecho
  solucionado conhecido até o corte.

A regressão cobre uma solicitação vencida no período anterior, respondida e resolvida somente
depois: ela permanece atrasada e não solucionada no corte histórico, passando a respondida e
solucionada apenas no corte posterior.

## Validações executadas

- `ruff check app/operations/routes.py tests/test_p1_completion.py tests/test_territorial_homologation.py`: aprovado;
- `pytest tests/test_p1_completion.py tests/test_territorial_homologation.py -q`: **9 testes aprovados**;
- `pytest tests/postgres/test_postgresql_migrations.py::test_postgis_generates_request_locations_and_spatial_index -q`: **1 teste aprovado** em PostgreSQL/PostGIS efêmero.

A suíte backend global foi tentada separadamente, mas não concluiu dentro da janela de três
minutos deste ambiente local. Ela não foi usada como evidência de aprovação. O perímetro do
gate foi validado pelas suítes territoriais e espacial específicas acima e permanece coberto
pelo job PostgreSQL da integração contínua.

## Decisão e pendências fora do gate

O Gate A está encerrado sem pendência bloqueante. Continuam fora deste gate:

- benchmark e aprovação do provedor externo, pertencentes ao Gate C;
- metas definitivas de adoção, que exigem observação contínua em mais gabinetes;
- evolução de agregações em memória para SQL/materialização, condicionada ao crescimento de
  volume e ao orçamento de latência;
- automação de regressão visual, recomendada como débito técnico não bloqueante.

Esses itens não reabrem o Gate A; devem ser acompanhados nos incrementos e gates correspondentes.
