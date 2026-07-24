# Arquitetura — Contêineres

## Aplicação Web

- gestão de atendimento;
- dashboards;
- administração;
- revisão de IA;
- produção legislativa.

## API Backend

Responsável por:
- autenticação e autorização;
- regras de negócio;
- APIs;
- auditoria;
- orquestração.

## Worker Assíncrono

Responsável por:
- transcrição;
- OCR;
- classificação;
- geocodificação;
- notificações;
- indexação;
- geração de relatórios.

## Serviço de IA

Camada de abstração para:
- provedores de LLM;
- prompts versionados;
- políticas;
- mascaramento;
- avaliação;
- fallback.

## Serviço RAG

Responsável por:
- ingestão global e privada;
- parsing;
- chunking;
- embeddings;
- distribuição e versionamento do catálogo global;
- recuperação federada global + privada;
- filtros de tenant, jurisdição, vigência e finalidade;
- normalização e reranking;
- citações;
- controle de acesso;
- avaliação e melhoria tenant-scoped.

## Banco Transacional

Sugestão:
- PostgreSQL;
- PostGIS para geodados;
- schemas distintos para RAG global e privado;
- row-level security forçado no domínio privado;
- roles separadas para migration, API, worker e backup;
- pgvector para busca vetorial quando adotado.

## Armazenamento de Objetos

- anexos;
- áudios;
- documentos;
- versões;
- relatórios.

## Índice de Busca

- busca textual;
- filtros;
- agregações;
- busca híbrida.

## Barramento de Eventos

- desacoplamento;
- integração;
- processamento assíncrono;
- auditoria operacional.
