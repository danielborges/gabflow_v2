# Matriz responsiva

Esta suíte é a especificação executável da issue #17. Ela combina contratos de layout com comparação visual em Chromium.

## Execução

```bash
pnpm run test:e2e
pnpm run test:e2e:update
```

O segundo comando atualiza as imagens de referência e deve ser usado apenas depois de revisão visual intencional.

## Cobertura

- Viewports: 320x568, 375x667, 430x932, 768x1024, 1024x768, 1280x720, 1440x900 e 1920x1080.
- Perfis: administrador, gerente, assessor e parlamentar.
- Áreas: páginas públicas, atendimento, cidadãos, IA, agenda, fiscalização, canais, administração, privacidade, Documentos e todas as subáreas de Inteligência Eleitoral.
- Estado: API interceptada, usuários e dados fixos por perfil, data congelada e navegação aguardando estabilidade da rede.
- Evidências: 96 imagens de referência, screenshot e trace em falhas e relatório HTML publicado como artefato do CI por 14 dias.

## Critérios de aceite

- páginas públicas não podem criar rolagem horizontal no documento;
- controles visíveis não podem ficar fora do viewport, exceto quando contidos em uma região de rolagem horizontal explícita, como tabelas;
- menu móvel, navegação e modal de formulário precisam permanecer visíveis e utilizáveis;
- formulários, tabelas, mapas e painéis são exercitados pelas rotas que os contêm em todos os viewports aplicáveis;
- uma imagem crítica reprova se mais de 1% dos pixels diferir da referência;
- qualquer teste de contrato ou comparação visual reprovado é regressão bloqueante no CI.

O PR #15 é registrado somente como cobertura parcial anterior das telas de Cidadãos e Organizações; ele não substitui esta matriz ampla.
