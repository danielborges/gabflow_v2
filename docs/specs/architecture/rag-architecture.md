# Arquitetura RAG

## Fundação normativa já implementada

A Produção Legislativa utiliza o adaptador `FoundationRetriever` como primeira integração RAG-ready. Nesta fase, o catálogo relacional fornece fontes versionadas e vigentes, e o Ollama calcula embeddings localmente com fallback lexical. A resposta já preserva coleção, modelo, scores, IDs, referências, versões e checksums. A aplicação de uma citação continua condicionada à revisão humana e cria uma nova versão auditável da minuta.

O índice vetorial e a ingestão documental genérica permanecem evoluções futuras de RIA-040 a RIA-049. A troca do backend de recuperação deve preservar o contrato, a filtragem por tenant, a validação de vigência e a proibição de executar instruções encontradas nas fontes.

## Fontes

- Lei Orgânica.
- Regimento Interno.
- Legislação municipal.
- Decretos e atos.
- Plano Diretor.
- Código de Obras.
- Código de Posturas.
- Proposições.
- Atas.
- Respostas de secretarias.
- Contratos e processos autorizados.
- Base interna de procedimentos.
- Histórico de solicitações, conforme permissão.

## Pipeline de ingestão

1. Receber arquivo ou URL autorizada.
2. Validar tipo, tamanho e malware.
3. Extrair texto.
4. Identificar idioma e estrutura.
5. Aplicar OCR quando necessário.
6. Extrair metadados.
7. Classificar nível de acesso.
8. Gerar chunks com sobreposição.
9. Criar embeddings.
10. Indexar texto, vetores e filtros.
11. Executar testes de qualidade.
12. Publicar versão.

## Pipeline de consulta

1. Autenticar usuário.
2. Resolver tenant e permissões.
3. Classificar intenção.
4. Reescrever consulta quando necessário.
5. Aplicar filtros de acesso e vigência.
6. Recuperar por busca híbrida.
7. Reranquear.
8. Montar contexto.
9. Gerar resposta.
10. Verificar citações e groundedness.
11. Exibir resposta, fontes e incerteza.
12. Registrar feedback.

## Segurança

- Conteúdo recuperado é dado, não instrução.
- Instruções contidas em documentos devem ser ignoradas.
- Dados pessoais devem ser mascarados quando não necessários.
- Consultas devem respeitar isolamento por tenant.
- Documentos sigilosos exigem autorização explícita.
- Citações devem apontar para a versão exata.
