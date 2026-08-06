# Release 7.8 - Compromissos públicos e mapa operacional

## Escopo

Este corte do Incremento 5 acrescenta compromissos públicos territoriais com responsável,
prazo, progresso, estado manual, estado efetivo derivado e evidências públicas. A interface
sincroniza a lista de compromissos com a camada cartográfica operacional.

## Histórico e evidências

- somente o parlamentar pode criar ou alterar compromissos e adicionar evidências;
- usuários delegados com `ver_camadas_mandato` mantêm acesso somente leitura;
- estados manuais: planejado, em andamento, concluído e cancelado;
- prazo vencido é derivado e marcado por `status_source=derived_deadline`;
- conclusão fixa progresso em 100% e registra a data;
- evidências exigem título, data e URL pública HTTP(S);
- criação, atualização e evidência geram eventos append-only;
- operações também são registradas no log geral de auditoria.

## Cartografia operacional

A API retorna o limite oficial da jurisdição carregado pelo fluxo IBGE e pontos somente para
compromissos cujo local foi explicitamente confirmado como público. Coordenadas incompletas,
inválidas ou sem confirmação são rejeitadas.

Os territórios internos do gabinete ainda não possuem polígonos oficiais próprios. Por isso:

- nenhum polígono territorial artificial é criado;
- compromissos sem ponto público continuam consultáveis na tabela;
- a resposta informa quantos compromissos não foram mapeados;
- o mapa eleitoral e o mapa operacional permanecem camadas separadas;
- votos continuam fora do ICT e da priorização de compromissos.

## Persistência e segurança

As tabelas `electoral_public_commitments`, `electoral_commitment_evidence` e
`electoral_commitment_history` usam chaves compostas de tenant, RLS forçada e concessões
restritas às roles de runtime. O vínculo territorial também usa `tenant_id + territory_id`.

## Carga sintética de homologação

O gabinete-piloto pode receber uma carga idempotente de seis compromissos inequivocamente
marcados com o prefixo `[DEMO]`:

```powershell
docker compose exec -T api flask --app wsgi:app `
  seed-electoral-commitments-demo --tenant gabinete-demo
```

A carga cobre estados planejado, em andamento, concluído, cancelado e vencido derivado,
além de evidências, histórico, responsáveis distintos, pontos públicos e um compromisso ativo
sem coordenadas. As URLs sob `example.org` e todo o conteúdo da carga são sintéticos e não
devem ser apresentados como ações reais do parlamentar.

## Próximo passo

Homologar o fluxo com a carga sintética, cadastrar compromissos reais autorizados e, quando houver
fonte oficial para subdivisões operacionais, importar uma malha versionada antes de oferecer
coropléticos por bairro ou região interna.
