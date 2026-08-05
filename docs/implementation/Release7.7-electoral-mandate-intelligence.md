# Release 7.7 - Inteligência integrada do mandato

## Escopo entregue

O primeiro corte do Incremento 5 conecta resultados eleitorais públicos ao desempenho
agregado do mandato sem criar vínculo entre voto e pessoa. O painel materializa snapshots
privados por período, com demandas, resolução, SLA, agenda realizada, fiscalização,
ações legislativas vinculadas e entregas com evidência.

## Privacidade e uso responsável

- limiar por gabinete, padrão 10;
- supressão integral das métricas operacionais em grupos abaixo do limiar;
- categorias pequenas omitidas ou reunidas somente quando o próprio agregado alcança o limiar;
- categorias sensíveis generalizadas como `Temas protegidos (agregado)`;
- nenhum protocolo, cidadão, endereço, descrição ou responsável integra a resposta;
- votos aparecem somente no contexto jurisdicional e nunca no cálculo do ICT;
- alertas tratam SLA e ausência de atividade, jamais baixa votação.

## Índice de Cobertura Territorial

O `ICT-1.0` pondera resolução (30%), SLA (25%), agenda (15%), fiscalização (15%) e
entregas com evidência (15%). Quando não existe demanda avaliável por SLA, o componente
é retirado e os demais pesos são renormalizados. Metas, pesos, categorias protegidas e
explicação são versionados; somente o parlamentar pode ativar uma nova versão.

Cada snapshot persiste período, corte temporal, versão do perfil, limiar, hash SHA-256 da
configuração, contexto eleitoral e payload agregado. Assim, uma leitura posterior não é
alterada por mudanças nos registros operacionais.

## Segurança e acesso

- capacidade exigida: `ver_camadas_mandato`;
- feature flag opt-in: `camadasMandato`;
- isolamento por `tenant_id` e mandato ativo;
- RLS forçada para perfis e snapshots no PostgreSQL;
- criação de perfil e snapshot registrada no log de auditoria;
- a interface identifica células suprimidas e não oferece drill-down individual.

## Próximo corte do incremento

Adicionar compromissos públicos territoriais com responsável, prazo, evidência e estado,
além da camada geográfica operacional. A associação com zonas eleitorais só poderá ocorrer
por crosswalk oficial/revisado; na ausência dele, os dois mapas permanecem separados.
