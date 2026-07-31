# Release 5.5 — ClamAV e parsing isolado

## Resultado

Uploads de anexos, documentos RAG privados e versões do catálogo global agora
passam por ClamAV antes da gravação. O cliente usa o protocolo `INSTREAM`, limita
bytes e tempo e aceita apenas `OK` ou `FOUND`. Qualquer indisponibilidade, resposta
inválida ou limite excedido falha de forma fechada.

Depois do scan, o GabFlow verifica a assinatura real do MIME para PDF, PNG, JPEG,
DOCX, texto, MP3, MP4, OGG, WAV e WebM. Provider, versão do engine, versão das
assinaturas, instante e decisão ficam persistidos sem copiar o conteúdo analisado.

## Defesa antes do parsing

Imediatamente antes de OCR, transcrição ou ingestão RAG, o arquivo é relido, seu
checksum é comparado ao original e uma nova varredura é executada. Divergência ou
malware despublica a versão, remove derivados e impede o parser.

## Sidecar isolado

TXT, DOCX, PDF e imagens são processados em um sidecar acessado por socket Unix. O
container usa `network_mode: none`, não recebe secrets, monta os objetos como
read-only, remove capabilities e habilita `no-new-privileges`. Cada solicitação
roda em subprocesso descartável com limites de CPU, memória, descritores, processos,
arquivo, saída e timeout.

O contrato retorna somente status, texto, páginas, confiança, contagem e versão do
parser. Campos extras e respostas acima do limite são rejeitados.

## Referências operacionais

A integração segue o protocolo `INSTREAM` e as recomendações da imagem oficial do
ClamAV: https://docs.clamav.net/manual/Usage/ClamdProtocol.html e
https://docs.clamav.net/manual/Installing/Docker.html.
