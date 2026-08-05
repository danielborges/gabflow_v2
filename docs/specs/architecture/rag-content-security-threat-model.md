# Threat model de segurança de conteúdo do RAG

## Identificação

- **Incremento:** 5.1 — specs, threat model e dataset adversarial
- **Versão:** 1.0
- **Estado:** aprovado para orientar os incrementos 5.2 a 5.8
- **Escopo:** Base RAG privada, catálogo global, projeções operacionais, OCR,
  transcrições, feedback, recuperação, geração e futuras integrações com ferramentas
- **Referências:** RIA-047, RIA-048, RIA-069, RIA-105 a RIA-111 e RNF-032 a RNF-044

## Objetivo de segurança

Conteúdo controlado por usuários, cidadãos, documentos, integrações ou fontes
externas nunca é confiável como instrução. O sistema deve impedir que esse conteúdo:

1. altere as instruções do GabFlow ou o papel do modelo;
2. extraia prompts, segredos, dados de outro tenant ou contexto não autorizado;
3. contamine chunks, embeddings, memórias, feedback ou artefatos de aprendizado;
4. altere filtros de tenant, ACL, finalidade, vigência, retenção ou publicação;
5. provoque chamadas de ferramentas ou ações fora da intenção confirmada do usuário;
6. permaneça recuperável depois de quarentena, revogação ou decisão de bloqueio.

Prompt injection não possui prevenção perfeita baseada em texto. O controle adotado
é defesa em profundidade, com falha fechada nos pontos que antecedem indexação,
publicação, composição de contexto e execução de ações.

## Estado atual verificado

### Controles existentes

- filtro determinístico inicial com normalização de acentos;
- sanitização de sentenças suspeitas durante a recuperação;
- separação textual entre instruções do sistema e fontes não confiáveis;
- quarentena pré-armazenamento para projeções operacionais detectadas;
- moderação e quarentena de feedback textual suspeito;
- contrato fechado de afirmações e citações na geração;
- validação lexical e NLI das afirmações geradas;
- RLS forçado, contexto transacional de tenant, constraints compostas e roles de
  runtime sem `BYPASSRLS`.

### Controles adicionados até o incremento 5.4

- canonicalização defensiva com limites de entrada e de payload decodificado para
  Unicode, invisíveis, HTML, URL encoding, Base64, hexadecimal, espaçamento e typos;
- detector determinístico e classificador dedicado com modelo diferente do gerador;
- contrato estrito `label`, `score` e `categories`, sem justificativa livre nem
  persistência do payload analisado;
- dataset adversarial executado no CI contra o gateway completo, incluindo controles
  benignos, metadados, OCR, feedback, consultas e sequências de chunks;
- indisponibilidade ou resposta inválida do classificador obrigatório produz
  `INDETERMINATE/RETRY`.

### Controles adicionados no incremento 5.5

- ClamAV oficial com base persistente e atualizada por FreshClam, acessível somente
  na rede interna do Compose;
- protocolo `INSTREAM` limitado, resposta fechada e indisponibilidade fail-closed;
- validação do MIME real após o scan e antes da persistência;
- nova varredura e conferência de checksum imediatamente antes de OCR, transcrição
  ou parsing RAG;
- sidecar de parsing sem rede ou segredos, volumes de entrada somente leitura,
  filesystem raiz read-only, capabilities removidas e `no-new-privileges`;
- subprocesso descartável por documento com limites de memória, CPU, descritores,
  processos, tamanho de entrada, tamanho da saída e timeout.

### Lacunas aceitas para os próximos incrementos

- não há revarredura versionada de todo o acervo quando a política de segurança muda;
- criptografia por chave de tenant ainda não está implementada.

## Ativos protegidos

| Ativo | Impacto principal |
|---|---|
| Fronteira e identidade do tenant | confidencialidade e não interferência |
| Prompts de sistema e desenvolvedor | integridade e confidencialidade |
| Documentos, chunks e embeddings | integridade do conhecimento |
| Respostas, citações e minutas | integridade e rastreabilidade |
| Credenciais, tokens e configurações | confidencialidade |
| Políticas de ACL, vigência e retenção | autorização |
| Feedback e artefatos de aprendizado | integridade e isolamento |
| Logs e trilhas de auditoria | integridade sem replicar payload malicioso |
| Ferramentas e integrações futuras | autorização e segurança operacional |

## Atores e capacidades

- **Usuário malicioso do tenant:** pode enviar documentos, consultas, comentários e
  correções dentro das permissões da própria conta.
- **Fonte externa comprometida:** pode inserir instruções indiretas em PDFs, páginas,
  metadados, OCR, anexos ou respostas de APIs homologadas.
- **Cidadão ou terceiro não autenticado:** pode influenciar solicitações que depois
  sejam projetadas no RAG privado.
- **Administrador global comprometido:** pode tentar distribuir uma fonte envenenada
  a vários tenants.
- **Conteúdo legítimo ambíguo:** pode citar ataques, comandos ou palavras de risco sem
  intenção maliciosa e causar falsos positivos.
- **Falha de dependência:** scanner, classificador ou parser pode ficar indisponível,
  retornar contrato inválido ou exceder limites.

## Fronteiras de confiança

```text
[origem não confiável]
  upload | módulo | OCR | feedback | conector | consulta
                         |
                         v
[objeto temporário isolado e não publicável]
                         |
                         v
[extração limitada + normalização + security gateway]
                         |
           +-------------+-------------+
           |             |             |
         CLEAN       SUSPICIOUS     MALICIOUS/ERROR
           |             |             |
           v             v             v
   chunks/embeddings  quarentena    bloqueio/retry
           |
           v
[autorização/RLS/filtros antes do ranking]
           |
           v
[segunda inspeção + contexto estruturado não confiável]
           |
           v
[gerador sem ferramentas e sem segredos]
           |
           v
[validação de saída, afirmações, citações e política]
```

Decisões de tenant, ACL, publicação, purge e execução não podem ser produzidas ou
sobrescritas pelo LLM. Elas pertencem ao código e ao banco.

## Catálogo de ameaças

| ID | Ameaça | Vetores | Impacto | Controle-alvo |
|---|---|---|---|---|
| PI-001 | sobrescrita de instruções | “ignore”, mudança de papel, falsa mensagem de sistema | desvio do modelo | normalização, detector e classificador |
| PI-002 | extração de prompt | pedido direto ou indireto para repetir instruções | exposição de controles | classificação e validação de saída |
| PI-003 | exfiltração | URLs, Markdown, HTML, imagens ou texto codificado | vazamento de dados | modelo sem rede, saída sanitizada e allowlist |
| PI-004 | ofuscação | Base64, hex, URL encoding, zero-width, bidi, homoglyphs | evasão dos filtros | canonicalização limitada e inspeção das derivações |
| PI-005 | tipoglicemia e variações | erros, espaçamento, caixa, sinônimos e idiomas | evasão dos padrões | fuzzy matching e classificador multilíngue |
| PI-006 | ataque distribuído | instrução dividida entre páginas, chunks ou turnos | evasão local | análise por janela, documento e sessão |
| PI-007 | multimodal e metadados | OCR oculto, camada branca, nome, propriedades e comentários | injeção indireta | extração segura de todas as superfícies |
| PI-008 | envenenamento persistente | documento publicado, memória ou exemplar contaminado | repetição do ataque | bloqueio pré-embedding, quarentena e revarredura |
| PI-009 | manipulação de ferramenta | conteúdo solicita envio, alteração ou exclusão | ação não autorizada | ausência de ferramentas no leitor e policy engine externo |
| PI-010 | falso positivo | lei, treinamento ou relatório cita frase maliciosa | indisponibilidade e retrabalho | dataset benigno, score e revisão humana |
| PI-011 | falha aberta | timeout ou contrato inválido do scanner/classificador | conteúdo não avaliado entra no índice | estado indeterminado e retry fail-closed |
| PI-012 | contaminação cruzada | cache, artefato ou dado sem tenant | impacto em outro tenant | RLS, chave tenant-scoped e testes negativos |
| PI-013 | malware e parser exploit | macro, PDF, arquivo poliglota ou bomba de descompressão | execução ou indisponibilidade | antimalware, MIME real e sandbox do parser |
| PI-014 | evasão por saída | modelo reproduz instrução, segredo ou link de exfiltração | sucesso do ataque | output guard e contrato fechado |

## Invariantes de segurança

1. Nenhuma versão sem decisão `CLEAN` pode gerar chunks ou embeddings.
2. `SUSPICIOUS`, `MALICIOUS` e `INDETERMINATE` nunca são publicáveis nem recuperáveis.
3. Indisponibilidade de scanner obrigatório não equivale a aprovação.
4. Sanitização não muda um conteúdo de alto risco para confiável automaticamente.
5. A decisão registra política, sinais, modelo, versão e hash, sem copiar o payload
   malicioso para logs ou eventos.
6. Reclassificação para risco despublica imediatamente e elimina artefatos derivados.
7. Conteúdo recuperado continua não confiável mesmo depois de aprovado para indexação.
8. O contexto do modelo contém somente fontes já autorizadas e IDs opacos.
9. O modelo que lê fontes não recebe credenciais, rede ou permissão de escrita.
10. Toda ação de alto impacto exige autorização determinística e confirmação humana.
11. Nenhuma decisão de segurança ou artefato pode atravessar tenant.
12. O arquivo bruto preservado para revisão fica em namespace isolado e sujeito à
    retenção; criptografia não substitui RLS ou autorização.

## Contrato de decisão implementado

O gateway produz um resultado fechado:

```json
{
  "status": "CLEAN | SUSPICIOUS | MALICIOUS | INDETERMINATE",
  "action": "ALLOW | QUARANTINE | BLOCK | RETRY",
  "score": 0.0,
  "categories": ["INSTRUCTION_OVERRIDE"],
  "signals": ["UNICODE_ZERO_WIDTH"],
  "policyVersion": "rag-content-security-v2",
  "detectorVersion": "canonical-deterministic-v2",
  "classifier": {"provider": "http", "model": "...", "version": "...", "label": "MALICIOUS", "score": 0.98, "categories": ["INSTRUCTION_OVERRIDE"]}
}
```

Campos livres do classificador são rejeitados; somente label, score e categorias
allowlisted e os metadados versionados podem dirigir ou documentar a decisão.

## Dataset adversarial

O contrato do dataset está em
`docs/specs/datasets/prompt-injection-adversarial.schema.json`, e a primeira versão
em `docs/specs/datasets/prompt-injection-adversarial-v1.json`.

Regras de governança:

- casos são imutáveis dentro da mesma versão;
- mudanças de rótulo ou conteúdo criam nova versão;
- casos possuem origem sintética ou autorização explícita e nunca contêm segredos;
- ataques e controles benignos devem ser mantidos em todas as línguas suportadas;
- o conjunto de desenvolvimento e o conjunto holdout não compartilham paráfrases;
- casos de produção são minimizados, anonimizados e promovidos por revisão humana;
- o dataset não é fonte factual, não entra no RAG e não pode ser citado pelo assistente.

## Critérios de aceite do programa de segurança

- 100% dos ataques críticos conhecidos do dataset de regressão bloqueados ou
  colocados em quarentena;
- recall mínimo de 98% no holdout adversarial;
- falso positivo máximo de 2% nos controles benignos;
- zero chunks ou embeddings produzidos para decisões diferentes de `CLEAN`;
- zero recuperação de versões em quarentena;
- zero vazamento entre tenants nos testes PostgreSQL;
- falha de scanner ou classificador obrigatório resulta em `INDETERMINATE`;
- todo resultado é reproduzível por versão da política e checksum do conteúdo;
- revarredura despublica e purga derivados antes de concluir a decisão de risco;
- validação de saída impede prompt leakage, segredos e destinos externos não
  autorizados.

Esses critérios são gates de release, não alegação de que prompt injection possa ser
eliminada por completo. Novas técnicas alimentam continuamente o dataset e o processo
de red team.

## Evolução do runtime

Os incrementos 5.2 a 5.6 implementam gateway, estado persistente, enforcement,
canonicalização, classificador, antimalware, parsing isolado e revarredura com purge
dos derivados. Validação de saída e criptografia por tenant permanecem nos
incrementos 5.7 e 5.8.
