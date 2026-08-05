# Release 7.5 - Exportações auditáveis e delegação controlada

## Escopo

O Incremento 4 fecha o MVP operacional da Inteligência Eleitoral com geração
assíncrona de PDF, CSV e XLSX, armazenamento criptografado, downloads assinados,
retenção, revogação imediata e delegações temporárias por capacidade.

## Fluxo de exportação

1. O ator com a capacidade `exportar` informa conteúdo, formato e finalidade.
2. A API valida candidatura/comparação e persiste um `electoral_report_job`.
3. O mesmo commit inclui `electoral.report.requested` no outbox.
4. O worker recompõe a análise somente a partir do dataset publicado e gera o arquivo.
5. O artefato é cifrado com AES-256-GCM e recebe hash SHA-256 e prazo de retenção.
6. O download exige JWT, capacidade `exportar` e token assinado temporário.
7. Compartilhamento, download, retry, conclusão, expiração e revogação são auditados.

O PDF contém marca d'água, autoria, data/hora UTC, finalidade, filtros, fonte,
versão e aviso metodológico. CSV e XLSX reproduzem o mesmo recorte e preservam
valores numéricos de votos, percentuais, ranking e denominador.

## Delegação

- somente o Parlamentar titular possui `delegar_acesso`;
- o destinatário deve ser usuário ativo do mesmo tenant;
- capacidades, motivo e janela de 1 a 90 dias são obrigatórios;
- `delegar_acesso` nunca pode ser redelegada;
- `exportar` precisa ser concedida explicitamente;
- a revogação passa a valer na próxima requisição;
- a navegação para não parlamentares só aparece após a API confirmar delegação com
  `consultar_dados_publicos`.

As flags `exportacoes` e `delegacao` permanecem opt-in por gabinete.

## Retenção e segurança

- retenção padrão: 30 dias;
- validade padrão do link: 5 minutos, limitada em configuração a no máximo 7 dias;
- o scheduler remove o objeto criptografado e preserva metadados de auditoria;
- recursos privados usam RLS forçada por `tenant_id`;
- o tenant é sempre derivado do JWT e nunca aceito do payload.

Estados do job:

`QUEUED -> PROCESSING -> COMPLETED | FAILED -> QUEUED (retry) | REVOKED`

Um relatório revogado ou expirado retorna `404` mesmo que um token previamente
emitido ainda esteja criptograficamente válido.
