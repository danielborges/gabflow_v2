# ADR-003 — IA explicável com evidências

Status: Aceito

## Contexto

Insights políticos sem evidências podem induzir decisões erradas, inventar causalidade ou reforçar vieses.

## Decisão

Usar geração aumentada por recuperação com dados estruturados e documentos autorizados. Toda saída separa fatos, cálculos, hipóteses e limitações, cita versões e registra modelo/template. Prompts de inferência política individual são bloqueados.

## Consequências

- A resposta é mais auditável, porém menos livre.
- Exige pipeline de avaliação quantitativa e citações.
- O usuário pode contestar e solicitar revisão.
- Mudanças de modelo não alteram silenciosamente análises antigas.
