# Definition of Done

- código revisado;
- testes unitários aprovados;
- testes de integração aprovados;
- teste de contrato aprovado;
- cenário de aceite automatizado quando aplicável;
- documentação atualizada;
- migrations versionadas;
- logs e métricas adicionados;
- controles de autorização testados;
- auditoria validada;
- acessibilidade verificada;
- risco LGPD revisado;
- para IA: dataset de avaliação executado, métricas registradas e fallback validado.
- para RAG privado: teste de RLS sem filtro explícito, escrita cruzada, pool de conexões e worker aprovado;
- para RAG global: política de distribuição, jurisdição, vigência, proveniência e revogação validadas;
- para recuperação hierárquica: avaliação separada e conjunta dos escopos, citações e recusa conclusiva;
- para memória operacional: criação, atualização, cancelamento, exclusão,
  anonimização e expiração propagadas e testadas;
- para projetores: allowlist, elegibilidade, PII, ACL, idempotência, evento fora de
  ordem, erro definitivo e reconciliação validados;
- para purge: ausência comprovada de chunks, embeddings, texto extraído, versões
  derivadas e objeto privado, preservando auditoria sem conteúdo;
- para retrieval: dataset por tenant com `precision@k`, `recall@k`, groundedness,
  citações desconexas, recusa e ausência de diversidade forçada abaixo do limiar;
- para feedback: revisões imutáveis, taxonomia, julgamento de fontes, quarentena,
  substituição e revogação tenant-scoped testados;
- para curadoria: promoção idempotente, FK tenant-scoped, expected sources, hard
  negatives, rota/filtros/recusa e desativação por inelegibilidade testados;
- para aprendizado: artefato reproduzível, candidato contra baseline, limites de
  influência, ativação atômica, canário e rollback validados;
- para segurança do aprendizado: comentário malicioso não alcança prompt, índice,
  logs, eventos ou artefato e nenhum sinal cruza tenant;
- para conectores: allowlist, SSRF, cofre de segredos, limites, quarentena e snapshot versionado testados;
- credenciais de runtime confirmadas como `NOSUPERUSER` e `NOBYPASSRLS`.
