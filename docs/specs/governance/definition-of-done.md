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
- validação de saída exercitada com sinais críticos, canário, métricas e rollback;
- criptografia em repouso comprovada por teste de autenticação cruzada entre tenants;
- auditoria automatizada de RLS concluída sem tabela ou role não conforme.
- para segurança de conteúdo: threat model revisado, dataset adversarial executado,
  ataques críticos contidos, recall/falsos positivos dentro dos gates e ausência de
  chunks ou embeddings para decisões diferentes de `CLEAN`;
- falha de scanner ou classificador obrigatório validada como fail-closed, sem
  publicação ou aprovação implícita;
- canonicalização possui limites explícitos e testes para codificação, Unicode,
  espaçamento e typos, sem perder partes não transformadas do conteúdo;
- classificador usa modelo independente do gerador e rejeita qualquer campo ou
  categoria fora do contrato fechado;
- upload malicioso, MIME divergente, indisponibilidade do ClamAV e alteração de
  checksum antes do parsing são bloqueados em testes fail-closed;
- parser confirmado sem rede, segredos, escrita nos objetos, capabilities ou
  privilégios adicionais, com limites e timeout testados;
