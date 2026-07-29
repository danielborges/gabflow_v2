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
- para conectores: allowlist, SSRF, cofre de segredos, limites, quarentena e snapshot versionado testados;
- credenciais de runtime confirmadas como `NOSUPERUSER` e `NOBYPASSRLS`.
