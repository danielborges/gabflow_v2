# Release 8.9 — Identidade eleitoral e exploração separada

## Objetivo

Separar inteligência personalizada do mandato de pesquisa eleitoral geral. Todos os
fluxos operacionais passam a usar somente participações próprias verificadas do
parlamentar titular. O catálogo global permanece acessível em **Explorar outras
eleições**.

## Regras

1. A identidade eleitoral é vinculada automaticamente pelo CPF cadastrado e pelo
   cadastro oficial de candidaturas sincronizado do TSE.
2. Cada participação corresponde a uma candidatura versionada em uma eleição.
3. Assessores delegados herdam o contexto do parlamentar titular; não possuem uma
   identidade eleitoral independente dentro do mandato.
4. `GET /electoral/elections` retorna somente eleições vinculadas.
5. `GET /electoral/elections/explore` retorna o catálogo público publicado.
6. Buscas operacionais rejeitam eleições não vinculadas; buscas exploratórias exigem
   o modo explícito `explore=true`.
7. A eleição própria mais recente é o padrão dos combos operacionais.
8. O CPF nunca é persistido na base eleitoral: somente uma impressão HMAC-SHA256
   versionada é usada na reconciliação.
9. Confirmação manual é contingência exclusiva para CPF ausente, fonte oficial
   indisponível ou divergência cadastral.
10. Nome, partido, número ou similaridade textual nunca criam vínculo automático.
11. A presença do CPF varia por ciclo e regra de divulgação do TSE. No recurso oficial
    atualmente sincronizado de 2024, o campo está suprimido; essas participações usam
    a contingência manual até existir uma fonte oficial apta à correspondência.

## Experiência

- Nova entrada lateral **Explorar outras eleições**.
- Busca por eleição, nome ou número de candidatura.
- Estado visível da verificação automática, sem revelar CPF.
- Identificação visual de vínculo **Verificado pelo CPF** ou **Confirmação manual**.
- Ação **Confirmar manualmente** somente quando a reconciliação não puder concluir.
- Vínculo automático não pode ser removido diretamente; deve-se corrigir o CPF ou
  abrir revisão de divergência.

## Segurança e auditoria

- `electoral_user_candidacies` é tenant-scoped, possui RLS forçada e chave única por
  usuário/candidatura.
- `electoral_candidate_registry_syncs` registra origem, hash e manifesto da
  sincronização oficial; `electoral_candidacy_official_identities` guarda somente a
  impressão protegida do CPF.
- Reconciliação, confirmação contingencial e remoção geram auditoria minimizada.
- CPF não aparece na API, interface, logs ou auditoria eleitoral.

## Operação

Após publicar os resultados de um ciclo, sincronizar o cadastro oficial correspondente:

```text
flask electoral-sync-candidate-registry --year 2024 --uf MG
```

O comando é idempotente por hash da fonte e versão da chave. A execução deve ser
agendada diariamente durante o calendário eleitoral e após atualização das bases
históricas. A indisponibilidade do TSE preserva o último cadastro válido e não bloqueia
login ou análises já vinculadas.
