# ruff: noqa: E501
"""Idempotent legislative workload for the Gabinete 302 staging tenant."""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from flask import current_app
from sqlalchemy import func, select

from app import create_app
from app.audit import add_audit
from app.extensions import db
from app.models import (
    LegislativeDocumentType,
    LegislativeDraft,
    LegislativeDraftRequest,
    LegislativeDraftStatus,
    LegislativeDraftVersion,
    LegislativeGenerationStatus,
    LegislativeTramitation,
    LegislativeTramitationStatus,
    NormativeSource,
    RequestHistory,
    Role,
    ServiceRequest,
    Tenant,
    Territory,
    User,
    UserStatus,
)

SEED_TAG = "LEGISLATIVE-G302-20260818"
NAMESPACE = uuid.UUID("37782396-6dcc-40c2-a295-f31ea0a99760")
TARGET_DOCUMENTS = 120
TARGET_LINKED_DOCUMENTS = 84
TARGET_CONCLUDED_PROPOSITIONS = 72
TARGET_NORMATIVE_SOURCES = 14
REFERENCE_TIME = datetime(2026, 1, 8, 14, 0, tzinfo=UTC)


def _id(kind: str, index: int | str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{SEED_TAG}:{kind}:{index}")


NORMATIVE_CATALOG = (
    {
        "key": "cf-interesse-local",
        "source_type": "CONSTITUICAO",
        "title": "Constituição da República Federativa do Brasil de 1988",
        "reference": "art. 30, incisos I, II e V",
        "excerpt": (
            "Compete aos Municípios legislar sobre assuntos de interesse local, suplementar "
            "a legislação federal e estadual e organizar os serviços públicos locais."
        ),
        "jurisdiction": "Federal",
        "url": "https://www.planalto.gov.br/ccivil_03/constituicao/constituicaocompilado.htm",
        "valid_from": date(1988, 10, 5),
    },
    {
        "key": "cf-meio-ambiente",
        "source_type": "CONSTITUICAO",
        "title": "Constituição da República Federativa do Brasil de 1988",
        "reference": "art. 225",
        "excerpt": (
            "Todos têm direito ao meio ambiente ecologicamente equilibrado, impondo-se ao "
            "Poder Público e à coletividade o dever de defendê-lo e preservá-lo."
        ),
        "jurisdiction": "Federal",
        "url": "https://www.planalto.gov.br/ccivil_03/constituicao/constituicaocompilado.htm",
        "valid_from": date(1988, 10, 5),
    },
    {
        "key": "lei-organica-jf",
        "source_type": "LEI_ORGANICA",
        "title": "Lei Orgânica do Município de Juiz de Fora",
        "reference": "texto compilado e atualizado em 2026",
        "excerpt": (
            "Norma fundamental de organização do Município de Juiz de Fora, de seus Poderes, "
            "competências, serviços públicos e processo legislativo municipal."
        ),
        "jurisdiction": "Juiz de Fora/MG",
        "url": "https://www.camarajf.mg.gov.br/www/lei-organica-municipal",
        "valid_from": date(1990, 4, 5),
    },
    {
        "key": "estatuto-cidade",
        "source_type": "LEI_FEDERAL",
        "title": "Estatuto da Cidade",
        "reference": "Lei Federal nº 10.257/2001, arts. 1º e 2º",
        "excerpt": (
            "Estabelece normas de ordem pública e interesse social para o uso da propriedade "
            "urbana em benefício coletivo, com segurança, bem-estar e equilíbrio ambiental."
        ),
        "jurisdiction": "Federal",
        "url": "https://www.planalto.gov.br/ccivil_03/leis/leis_2001/l10257.htm",
        "valid_from": date(2001, 10, 10),
    },
    {
        "key": "acesso-informacao",
        "source_type": "LEI_FEDERAL",
        "title": "Lei de Acesso à Informação",
        "reference": "Lei Federal nº 12.527/2011, arts. 1º, 5º e 6º",
        "excerpt": (
            "Os Municípios devem garantir acesso à informação por procedimentos objetivos, "
            "ágeis, transparentes, claros e em linguagem de fácil compreensão."
        ),
        "jurisdiction": "Federal",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2011/lei/l12527.htm",
        "valid_from": date(2012, 5, 16),
    },
    {
        "key": "inclusao-deficiencia",
        "source_type": "LEI_FEDERAL",
        "title": "Lei Brasileira de Inclusão da Pessoa com Deficiência",
        "reference": "Lei Federal nº 13.146/2015, arts. 1º, 3º e 53",
        "excerpt": (
            "Assegura o exercício de direitos em igualdade de condições e define "
            "acessibilidade como direito que possibilita vida independente e participação social."
        ),
        "jurisdiction": "Federal",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2015/lei/l13146.htm",
        "valid_from": date(2016, 1, 2),
    },
    {
        "key": "residuos-solidos",
        "source_type": "LEI_FEDERAL",
        "title": "Política Nacional de Resíduos Sólidos",
        "reference": "Lei Federal nº 12.305/2010, arts. 1º, 6º e 7º",
        "excerpt": (
            "Institui princípios, objetivos e instrumentos para gestão integrada e gerenciamento "
            "de resíduos sólidos, com responsabilidade do poder público e dos geradores."
        ),
        "jurisdiction": "Federal",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2010/lei/l12305.htm",
        "valid_from": date(2010, 8, 3),
    },
    {
        "key": "saneamento-basico",
        "source_type": "LEI_FEDERAL",
        "title": "Diretrizes Nacionais para o Saneamento Básico",
        "reference": "Lei Federal nº 11.445/2007, arts. 2º, 3º e 9º",
        "excerpt": (
            "Os serviços de saneamento devem observar universalização, integralidade, segurança, "
            "qualidade, controle social e articulação com as políticas de desenvolvimento urbano."
        ),
        "jurisdiction": "Federal",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2007-2010/2007/lei/l11445compilado.htm",
        "valid_from": date(2007, 2, 22),
    },
    {
        "key": "mobilidade-urbana",
        "source_type": "LEI_FEDERAL",
        "title": "Política Nacional de Mobilidade Urbana",
        "reference": "Lei Federal nº 12.587/2012, arts. 1º, 2º e 5º",
        "excerpt": (
            "A política de mobilidade busca acesso universal à cidade, integração dos modos de "
            "transporte, acessibilidade e gestão democrática do sistema municipal."
        ),
        "jurisdiction": "Federal",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2011-2014/2012/lei/l12587.htm",
        "valid_from": date(2012, 4, 13),
    },
    {
        "key": "sus",
        "source_type": "LEI_FEDERAL",
        "title": "Lei Orgânica da Saúde",
        "reference": "Lei Federal nº 8.080/1990, arts. 2º, 7º e 18",
        "excerpt": (
            "A saúde é direito fundamental e as ações e serviços do SUS devem observar "
            "universalidade, integralidade, igualdade e descentralização político-administrativa."
        ),
        "jurisdiction": "Federal",
        "url": "https://www.planalto.gov.br/ccivil_03/leis/l8080.htm",
        "valid_from": date(1990, 9, 20),
    },
    {
        "key": "educacao",
        "source_type": "LEI_FEDERAL",
        "title": "Lei de Diretrizes e Bases da Educação Nacional",
        "reference": "Lei Federal nº 9.394/1996, arts. 1º, 3º e 11",
        "excerpt": (
            "A educação escolar vincula-se à prática social e deve observar igualdade de acesso, "
            "liberdade de aprender, pluralismo, gestão democrática e padrão de qualidade."
        ),
        "jurisdiction": "Federal",
        "url": "https://www.planalto.gov.br/ccivil_03/leis/l9394compilado.htm",
        "valid_from": date(1996, 12, 23),
    },
    {
        "key": "pessoa-idosa",
        "source_type": "LEI_FEDERAL",
        "title": "Estatuto da Pessoa Idosa",
        "reference": "Lei Federal nº 10.741/2003, arts. 2º, 3º e 9º",
        "excerpt": (
            "O poder público deve assegurar à pessoa idosa, com prioridade, direitos à vida, "
            "saúde, alimentação, educação, cultura, cidadania, dignidade e convivência comunitária."
        ),
        "jurisdiction": "Federal",
        "url": "https://www.planalto.gov.br/ccivil_03/leis/2003/l10.741compilado.htm",
        "valid_from": date(2004, 1, 1),
    },
    {
        "key": "eca",
        "source_type": "LEI_FEDERAL",
        "title": "Estatuto da Criança e do Adolescente",
        "reference": "Lei Federal nº 8.069/1990, arts. 3º, 4º e 53",
        "excerpt": (
            "Crianças e adolescentes gozam de proteção integral e prioridade na efetivação dos "
            "direitos à vida, saúde, alimentação, educação, cultura, dignidade e convivência."
        ),
        "jurisdiction": "Federal",
        "url": "https://www.planalto.gov.br/ccivil_03/leis/l8069compilado.htm",
        "valid_from": date(1990, 10, 12),
    },
    {
        "key": "lgpd",
        "source_type": "LEI_FEDERAL",
        "title": "Lei Geral de Proteção de Dados Pessoais",
        "reference": "Lei Federal nº 13.709/2018, arts. 6º, 7º e 23",
        "excerpt": (
            "O tratamento de dados pelo poder público deve atender finalidade pública, interesse "
            "público e execução de competências legais, observando necessidade e transparência."
        ),
        "jurisdiction": "Federal",
        "url": "https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm",
        "valid_from": date(2020, 9, 18),
    },
)


SUBJECTS = {
    "iluminação pública": {
        "headline": "Programa de iluminação segura em vias e praças de {territory}",
        "action": "mapear pontos escuros e priorizar a manutenção preventiva da iluminação pública",
        "destination": "Secretaria Municipal de Serviços Urbanos",
        "committee": "Comissão de Urbanismo",
        "sources": ("cf-interesse-local", "lei-organica-jf", "estatuto-cidade"),
        "types": ("INDICACAO", "REQUERIMENTO", "PEDIDO_INFORMACAO"),
    },
    "tapa-buraco e pavimentação": {
        "headline": "Plano de manutenção viária e transparência de obras em {territory}",
        "action": "estabelecer cronograma público de vistorias, reparos e recomposição do pavimento",
        "destination": "Secretaria Municipal de Obras",
        "committee": "Comissão de Urbanismo",
        "sources": ("cf-interesse-local", "lei-organica-jf", "estatuto-cidade"),
        "types": ("INDICACAO", "REQUERIMENTO", "PEDIDO_INFORMACAO"),
    },
    "saúde": {
        "headline": "Transparência da fila e do acesso à atenção especializada em {territory}",
        "action": "aperfeiçoar o acompanhamento das filas, dos encaminhamentos e dos retornos do SUS municipal",
        "destination": "Secretaria Municipal de Saúde",
        "committee": "Comissão de Saúde Pública",
        "sources": ("cf-interesse-local", "lei-organica-jf", "sus", "acesso-informacao"),
        "types": ("REQUERIMENTO", "PEDIDO_INFORMACAO", "INDICACAO", "PROJETO_LEI"),
    },
    "coleta de lixo": {
        "headline": "Regularidade e monitoramento da coleta domiciliar em {territory}",
        "action": "publicar rotas, horários e indicadores de regularidade da coleta de resíduos",
        "destination": "Secretaria Municipal de Serviços Urbanos",
        "committee": "Comissão de Meio Ambiente",
        "sources": ("cf-interesse-local", "lei-organica-jf", "residuos-solidos"),
        "types": ("INDICACAO", "REQUERIMENTO", "PEDIDO_INFORMACAO", "PROJETO_LEI"),
    },
    "trânsito e sinalização": {
        "headline": "Travessias seguras e sinalização acessível em {territory}",
        "action": "priorizar faixas de pedestres, rotas acessíveis e sinalização em áreas de maior circulação",
        "destination": "Secretaria Municipal de Mobilidade Urbana e Transporte",
        "committee": "Comissão de Urbanismo",
        "sources": ("cf-interesse-local", "mobilidade-urbana", "inclusao-deficiencia"),
        "types": ("INDICACAO", "REQUERIMENTO", "PROJETO_LEI"),
    },
    "transporte público": {
        "headline": "Confiabilidade das linhas de transporte coletivo em {territory}",
        "action": "monitorar cumprimento de horários, lotação, acessibilidade e informação ao usuário",
        "destination": "Secretaria Municipal de Mobilidade Urbana e Transporte",
        "committee": "Comissão de Transporte e Trânsito",
        "sources": ("cf-interesse-local", "lei-organica-jf", "mobilidade-urbana", "inclusao-deficiencia"),
        "types": ("REQUERIMENTO", "PEDIDO_INFORMACAO", "INDICACAO"),
    },
    "limpeza urbana": {
        "headline": "Cuidado continuado de praças e áreas públicas de {territory}",
        "action": "instituir calendário integrado de capina, varrição, manutenção e fiscalização das áreas públicas",
        "destination": "Secretaria Municipal de Serviços Urbanos",
        "committee": "Comissão de Meio Ambiente",
        "sources": ("cf-interesse-local", "estatuto-cidade", "residuos-solidos"),
        "types": ("INDICACAO", "OFICIO", "PROJETO_LEI"),
    },
    "defesa animal": {
        "headline": "Rede municipal de proteção e atendimento animal em {territory}",
        "action": "organizar fluxo de acolhimento, atendimento veterinário e destinação responsável de animais",
        "destination": "Secretaria Municipal de Meio Ambiente",
        "committee": "Comissão de Defesa dos Animais",
        "sources": ("cf-interesse-local", "cf-meio-ambiente", "lei-organica-jf"),
        "types": ("INDICACAO", "REQUERIMENTO", "PROJETO_LEI"),
    },
    "assistência social emergencial": {
        "headline": "Atendimento integrado a famílias em vulnerabilidade de {territory}",
        "action": "fortalecer a busca ativa, o acolhimento e o encaminhamento intersetorial das famílias",
        "destination": "Secretaria Municipal de Assistência Social",
        "committee": "Comissão de Direitos Humanos",
        "sources": ("cf-interesse-local", "lei-organica-jf", "eca", "pessoa-idosa"),
        "types": ("INDICACAO", "REQUERIMENTO", "OFICIO", "PROJETO_LEI"),
    },
    "educação": {
        "headline": "Manutenção preventiva e ambiente escolar seguro em {territory}",
        "action": "adotar plano de manutenção preventiva, acessibilidade e participação da comunidade escolar",
        "destination": "Secretaria Municipal de Educação",
        "committee": "Comissão de Educação e Cultura",
        "sources": ("cf-interesse-local", "educacao", "eca", "inclusao-deficiencia"),
        "types": ("INDICACAO", "REQUERIMENTO", "PEDIDO_INFORMACAO", "PROJETO_LEI"),
    },
    "saneamento básico": {
        "headline": "Prevenção de vazamentos e perdas de água em {territory}",
        "action": "adotar metas, indicadores e comunicação ativa para reparos de vazamentos e redes de saneamento",
        "destination": "Companhia de Saneamento Municipal",
        "committee": "Comissão de Serviços Públicos",
        "sources": ("cf-interesse-local", "lei-organica-jf", "saneamento-basico"),
        "types": ("REQUERIMENTO", "PEDIDO_INFORMACAO", "INDICACAO", "PROJETO_LEI"),
    },
    "acessibilidade urbana": {
        "headline": "Rotas acessíveis e eliminação de barreiras em {territory}",
        "action": "mapear barreiras, adaptar travessias e garantir continuidade das rotas acessíveis",
        "destination": "Secretaria Municipal de Planejamento Urbano",
        "committee": "Comissão de Defesa dos Direitos da Pessoa com Deficiência",
        "sources": ("cf-interesse-local", "estatuto-cidade", "inclusao-deficiencia"),
        "types": ("INDICACAO", "REQUERIMENTO", "PROJETO_LEI"),
    },
    "habitação": {
        "headline": "Transparência e atendimento habitacional em {territory}",
        "action": "garantir informação clara sobre cadastros, critérios, prioridades e acompanhamento habitacional",
        "destination": "Secretaria Municipal de Habitação",
        "committee": "Comissão de Urbanismo",
        "sources": ("cf-interesse-local", "estatuto-cidade", "acesso-informacao", "lgpd"),
        "types": ("REQUERIMENTO", "PEDIDO_INFORMACAO", "PROJETO_LEI"),
    },
    "segurança pública": {
        "headline": "Prevenção comunitária e ocupação segura dos espaços de {territory}",
        "action": "integrar iluminação, desenho urbano, dados territoriais e ações preventivas da guarda municipal",
        "destination": "Guarda Municipal",
        "committee": "Comissão de Segurança Pública",
        "sources": ("cf-interesse-local", "lei-organica-jf", "estatuto-cidade", "lgpd"),
        "types": ("INDICACAO", "REQUERIMENTO", "PEDIDO_INFORMACAO"),
    },
    "meio ambiente": {
        "headline": "Manejo responsável da arborização urbana em {territory}",
        "action": "planejar vistorias, podas preventivas, reposição arbórea e comunicação com a comunidade",
        "destination": "Secretaria Municipal de Meio Ambiente",
        "committee": "Comissão de Meio Ambiente",
        "sources": ("cf-interesse-local", "cf-meio-ambiente", "estatuto-cidade"),
        "types": ("INDICACAO", "REQUERIMENTO", "PROJETO_LEI", "MOCAO"),
    },
}


def _ensure_normative_sources(tenant: Tenant, actor: User) -> dict[str, NormativeSource]:
    result = {}
    for index, definition in enumerate(NORMATIVE_CATALOG):
        source_id = _id("normative-source", index)
        item = db.session.get(NormativeSource, source_id)
        if item is None:
            item = db.session.scalar(
                select(NormativeSource).where(
                    NormativeSource.tenant_id == tenant.id,
                    NormativeSource.external_id == f"STAGING-G302-NORMATIVE:{definition['key']}",
                )
            )
        checksum = hashlib.sha256(definition["excerpt"].encode("utf-8")).hexdigest()
        if item is None:
            item = NormativeSource(
                id=source_id,
                tenant_id=tenant.id,
                created_by_id=actor.id,
                origin="MANUAL",
                reviewed_by_id=actor.id,
                reviewed_at=datetime.now(UTC),
            )
            db.session.add(item)
        item.source_type = definition["source_type"]
        item.title = definition["title"]
        item.reference = definition["reference"]
        item.excerpt = definition["excerpt"]
        item.jurisdiction = definition["jurisdiction"]
        item.source_url = definition["url"]
        item.official_source_url = definition["url"]
        item.version = "Texto oficial consultado em 2026-08-18"
        item.checksum = checksum
        item.valid_from = definition["valid_from"]
        item.valid_until = None
        item.rag_collection = "legislacao"
        item.active = True
        item.provider = "CATALOGO_OFICIAL_STAGING"
        item.external_id = f"STAGING-G302-NORMATIVE:{definition['key']}"
        result[definition["key"]] = item
    db.session.flush()
    return result


def _request_groups(tenant_id: uuid.UUID) -> tuple[list[ServiceRequest], dict[str, list[ServiceRequest]]]:
    requests = list(
        db.session.scalars(
            select(ServiceRequest)
            .where(
                ServiceRequest.tenant_id == tenant_id,
                ServiceRequest.protocol.like("ST302-2026-%"),
            )
            .order_by(ServiceRequest.protocol)
        )
    )
    if len(requests) < TARGET_LINKED_DOCUMENTS:
        raise RuntimeError("insufficient_seed_requests")
    grouped: dict[str, list[ServiceRequest]] = defaultdict(list)
    for item in requests:
        grouped[(item.theme or "").casefold()].append(item)
    return requests, grouped


def _citation(source: NormativeSource) -> dict:
    return {
        "sourceId": str(source.id),
        "titulo": source.title,
        "referencia": source.reference,
        "trecho": source.excerpt,
        "url": source.source_url,
        "versaoFonte": source.version,
        "checksum": source.checksum,
        "validadaPeloUsuario": True,
        "recuperadaVia": "BASE_NORMATIVA_HIBRIDA",
    }


def _territory_name(request: ServiceRequest | None, territories: dict[uuid.UUID, str], index: int) -> str:
    if request and request.territory_id in territories:
        return territories[request.territory_id]
    values = sorted(territories.values())
    return values[index % len(values)] if values else "Juiz de Fora"


def _document_type(subject: dict, index: int) -> LegislativeDocumentType:
    values = subject["types"]
    return LegislativeDocumentType(values[index % len(values)])


def _render_document(
    document_type: LegislativeDocumentType,
    title: str,
    subject: dict,
    territory: str,
    request: ServiceRequest | None,
    citations: list[dict],
) -> tuple[str, str]:
    factual_context = (
        (request.description or request.title)[:700]
        if request
        else f"Diagnóstico territorial e escutas comunitárias realizadas em {territory}."
    )
    references = "; ".join(f"{item['titulo']} ({item['referencia']})" for item in citations)
    justification = (
        f"A iniciativa responde a evidências do cotidiano de {territory}. {factual_context} "
        f"A medida observa a competência municipal e foi fundamentada em {references}. "
        "A execução deverá preservar planejamento, transparência, acessibilidade, controle "
        "social e avaliação de resultados."
    )
    action = subject["action"]
    destination = subject["destination"]
    if document_type == LegislativeDocumentType.PROJETO_LEI:
        content = f"""PROJETO DE LEI

Ementa: {title}.

A Câmara Municipal de Juiz de Fora aprova:

Art. 1º Ficam instituídas diretrizes municipais para {action}, com atuação integrada dos órgãos competentes e participação social.

Art. 2º São objetivos desta Lei:
I - organizar diagnóstico territorial e critérios públicos de prioridade;
II - assegurar acessibilidade, transparência e atendimento não discriminatório;
III - divulgar cronograma, responsáveis e indicadores de resultado;
IV - permitir acompanhamento pela população e pelos órgãos de controle.

Art. 3º O Poder Executivo poderá integrar dados e serviços já existentes, observadas a finalidade pública, a necessidade e a proteção de dados pessoais.

Art. 4º A implementação observará as disponibilidades orçamentárias e o planejamento municipal, sem criação automática de despesa obrigatória.

Art. 5º Esta Lei entra em vigor na data de sua publicação.
"""
    elif document_type == LegislativeDocumentType.PEDIDO_INFORMACAO:
        content = f"""PEDIDO DE INFORMAÇÃO

Requer ao Poder Executivo Municipal informações sobre {title.casefold()}.

Solicita-se ao órgão responsável que informe:
1. qual diagnóstico atualizado existe para {territory};
2. quais critérios de prioridade, cronogramas e responsáveis são adotados;
3. quais recursos e contratos estão vinculados às ações;
4. quais indicadores de execução e qualidade são monitorados;
5. como a população acompanha solicitações e resultados.

Requer-se resposta em formato acessível e com dados agregados, observada a legislação de transparência e proteção de dados.
"""
    elif document_type == LegislativeDocumentType.REQUERIMENTO:
        content = f"""REQUERIMENTO

Requeiro à Mesa, na forma regimental, o envio de expediente ao Poder Executivo e a {destination}, solicitando providências para {action} em {territory}.

Requer-se diagnóstico, cronograma de atendimento, indicação da unidade responsável e devolutiva pública sobre as medidas adotadas.
"""
    elif document_type == LegislativeDocumentType.OFICIO:
        content = f"""OFÍCIO

À {destination}
Assunto: {title}

Senhor(a) Secretário(a),

O Gabinete 302 encaminha demanda territorial e solicita avaliação técnica para {action} em {territory}. Pede-se vistoria, registro do encaminhamento e resposta com prazo estimado, unidade responsável e providências executadas.

Atenciosamente,
Gabinete 302
"""
    elif document_type == LegislativeDocumentType.MOCAO:
        content = f"""MOÇÃO

A Câmara Municipal manifesta apoio às iniciativas comunitárias de {territory} relacionadas a {action}.

A mobilização social, o cuidado com o território e a cooperação com os serviços públicos merecem reconhecimento e continuidade, com respeito às competências institucionais.
"""
    else:
        content = f"""INDICAÇÃO

Indico ao Poder Executivo Municipal, na forma regimental, que avalie e adote providências para {action} em {territory}.

Sugere-se vistoria técnica, definição de prioridades, cronograma público, acessibilidade e devolutiva à comunidade sobre a execução.
"""
    return content.strip(), justification


def _final_status(document_type: LegislativeDocumentType, index: int) -> LegislativeTramitationStatus:
    if document_type == LegislativeDocumentType.PROJETO_LEI:
        return (
            LegislativeTramitationStatus.SANCIONADA,
            LegislativeTramitationStatus.APROVADA,
            LegislativeTramitationStatus.VETADA,
            LegislativeTramitationStatus.ARQUIVADA,
        )[index % 4]
    if document_type == LegislativeDocumentType.MOCAO:
        return (
            LegislativeTramitationStatus.APROVADA,
            LegislativeTramitationStatus.REJEITADA,
        )[index % 2]
    return (
        LegislativeTramitationStatus.APROVADA,
        LegislativeTramitationStatus.ARQUIVADA,
        LegislativeTramitationStatus.RETIRADA,
    )[index % 3]


def _add_version(
    draft: LegislativeDraft,
    number: int,
    actor: User,
    content: str,
    reason: str,
    created_at: datetime,
) -> None:
    version_id = _id("draft-version", f"{draft.id}:{number}")
    if db.session.get(LegislativeDraftVersion, version_id) is None:
        db.session.add(
            LegislativeDraftVersion(
                id=version_id,
                tenant_id=draft.tenant_id,
                draft_id=draft.id,
                version_number=number,
                title=draft.title,
                content=content,
                justification=draft.justification,
                legal_basis=draft.legal_basis,
                unsupported_passages=[],
                change_reason=reason,
                created_by_id=actor.id,
                created_at=created_at,
            )
        )


def _add_tramitation(
    draft: LegislativeDraft,
    sequence: int,
    status: LegislativeTramitationStatus,
    stage: str,
    actor: User,
    occurred_at: datetime,
    destination: str | None,
    notes: str,
) -> None:
    tramitation_id = _id("tramitation", f"{draft.id}:{sequence}")
    if db.session.get(LegislativeTramitation, tramitation_id) is None:
        db.session.add(
            LegislativeTramitation(
                id=tramitation_id,
                tenant_id=draft.tenant_id,
                draft_id=draft.id,
                status=status,
                stage=stage,
                destination=destination,
                external_reference=draft.protocol_number,
                notes=notes,
                occurred_at=occurred_at,
                created_by_id=actor.id,
            )
        )


def _ensure_document(
    index: int,
    tenant: Tenant,
    authors: list[User],
    approver: User,
    requests: list[ServiceRequest],
    grouped_requests: dict[str, list[ServiceRequest]],
    territories: dict[uuid.UUID, str],
    sources: dict[str, NormativeSource],
) -> LegislativeDraft:
    draft_id = _id("legislative-draft", index)
    existing = db.session.get(LegislativeDraft, draft_id)
    if existing is not None:
        return existing
    linked = index < TARGET_LINKED_DOCUMENTS
    primary = requests[(index * 17) % len(requests)] if linked else None
    theme = (primary.theme or "").casefold() if primary else list(SUBJECTS)[index % len(SUBJECTS)]
    subject = SUBJECTS.get(theme, SUBJECTS[list(SUBJECTS)[index % len(SUBJECTS)]])
    territory = _territory_name(primary, territories, index)
    document_type = _document_type(subject, index)
    title = subject["headline"].format(territory=territory)
    title = f"{title} - ciclo {1 + index // len(SUBJECTS)}"
    selected_sources = [sources[key] for key in subject["sources"]]
    citations = [_citation(item) for item in selected_sources]
    content, justification = _render_document(
        document_type, title, subject, territory, primary, citations
    )
    created_at = REFERENCE_TIME + timedelta(days=index * 1.6, hours=index % 7)
    author = authors[index % len(authors)]
    concluded = index >= TARGET_DOCUMENTS - TARGET_CONCLUDED_PROPOSITIONS
    status = LegislativeDraftStatus.APROVADA if concluded else (
        LegislativeDraftStatus.EM_REVISAO if index % 4 == 0 else LegislativeDraftStatus.RASCUNHO
    )
    protocol_number = f"CMJF-ST302-2026-{index + 1:04d}" if concluded else None
    protocolled_at = created_at + timedelta(days=8) if concluded else None
    current_tramitation_status = _final_status(document_type, index) if concluded else None
    request_links: list[ServiceRequest] = []
    if primary:
        candidates = grouped_requests.get((primary.theme or "").casefold(), [primary])
        primary_position = candidates.index(primary)
        request_links = [primary]
        for offset in range(1, 1 + index % 3):
            related = candidates[(primary_position + offset * 5) % len(candidates)]
            if related.id not in {item.id for item in request_links}:
                request_links.append(related)
    request_ids = [str(item.id) for item in request_links]
    draft = LegislativeDraft(
        id=draft_id,
        tenant_id=tenant.id,
        document_type=document_type,
        status=status,
        generation_status=LegislativeGenerationStatus.CONCLUIDA,
        title=title,
        content=content,
        justification=justification,
        legal_basis=citations,
        sources=citations,
        unsupported_passages=[],
        similar_proposals=[],
        generation_metadata={
            "seedTag": SEED_TAG,
            "synthetic": True,
            "datasetPurpose": "SIMULACAO_COTIDIANO_GABINETE",
            "provedor": "DETERMINISTIC_STAGING_SEED",
            "modelo": "governed-fixture-v1",
            "confianca": 0.96,
            "revisaoHumanaObrigatoria": True,
            "revisaoHumanaSimulada": True,
            "protocoloAutomatico": False,
            "solicitacaoPrincipalId": request_ids[0] if request_ids else None,
            "solicitacoesIds": request_ids,
            "normativeSourceIds": [str(item.id) for item in selected_sources],
            "territorio": territory,
        },
        current_version=2 if concluded else 1,
        protocol_number=protocol_number,
        protocolled_at=protocolled_at,
        current_tramitation_status=current_tramitation_status,
        created_by_id=author.id,
        reviewed_by_id=approver.id if status != LegislativeDraftStatus.RASCUNHO else None,
        approved_by_id=approver.id if concluded else None,
        reviewed_at=created_at + timedelta(days=3) if status != LegislativeDraftStatus.RASCUNHO else None,
        approved_at=created_at + timedelta(days=7) if concluded else None,
        created_at=created_at,
        updated_at=(protocolled_at + timedelta(days=20)) if concluded else created_at + timedelta(days=3),
    )
    db.session.add(draft)
    db.session.flush()
    initial_content = content.replace("cronograma público", "cronograma de execução", 1)
    _add_version(
        draft,
        1,
        author,
        initial_content,
        "Versão inicial elaborada a partir da escuta territorial",
        created_at,
    )
    if concluded:
        _add_version(
            draft,
            2,
            approver,
            content,
            "Revisão final, conferência normativa e aprovação do gabinete",
            created_at + timedelta(days=7),
        )
    for link_index, request_item in enumerate(request_links):
        link_id = _id("draft-request", f"{index}:{link_index}")
        db.session.add(
            LegislativeDraftRequest(
                id=link_id,
                tenant_id=tenant.id,
                draft_id=draft.id,
                request_id=request_item.id,
                created_at=created_at,
            )
        )
        db.session.add(
            RequestHistory(
                id=_id("request-history-legislative", f"{index}:{link_index}"),
                tenant_id=tenant.id,
                request_id=request_item.id,
                user_id=author.id,
                action="request.legislative_document.seeded",
                changes={
                    "minutaId": str(draft.id),
                    "titulo": draft.title,
                    "principal": link_index == 0,
                    "seedTag": SEED_TAG,
                    "synthetic": True,
                },
                created_at=created_at,
            )
        )
    if concluded:
        final_status = current_tramitation_status
        _add_tramitation(
            draft,
            1,
            LegislativeTramitationStatus.PROTOCOLADA,
            "Protocolo legislativo",
            approver,
            protocolled_at,
            "Secretaria Legislativa",
            "Proposição protocolada após revisão formal e conferência normativa.",
        )
        _add_tramitation(
            draft,
            2,
            LegislativeTramitationStatus.DISTRIBUIDA,
            "Distribuição",
            approver,
            protocolled_at + timedelta(days=2),
            subject["committee"],
            "Matéria distribuída para análise da comissão temática competente.",
        )
        _add_tramitation(
            draft,
            3,
            LegislativeTramitationStatus.EM_COMISSAO,
            "Análise em comissão",
            approver,
            protocolled_at + timedelta(days=8),
            subject["committee"],
            "Parecer e documentação de apoio incluídos no acompanhamento da matéria.",
        )
        _add_tramitation(
            draft,
            4,
            final_status,
            "Conclusão da tramitação",
            approver,
            protocolled_at + timedelta(days=20),
            "Plenário da Câmara Municipal",
            f"Tramitação encerrada com resultado {final_status.value}.",
        )
    add_audit(
        tenant.id,
        author.id,
        "legislative_draft.staging_seeded",
        "legislative_draft",
        draft.id,
        after={
            "seedTag": SEED_TAG,
            "synthetic": True,
            "documentType": document_type.value,
            "status": status.value,
            "tramitationStatus": current_tramitation_status.value
            if current_tramitation_status
            else None,
            "requestIds": request_ids,
            "normativeSourceIds": [str(item.id) for item in selected_sources],
        },
    )
    return draft


def _counts(tenant_id: uuid.UUID) -> dict:
    draft_ids = [_id("legislative-draft", index) for index in range(TARGET_DOCUMENTS)]
    source_ids = [_id("normative-source", index) for index in range(TARGET_NORMATIVE_SOURCES)]
    documents = list(
        db.session.scalars(
            select(LegislativeDraft).where(
                LegislativeDraft.tenant_id == tenant_id, LegislativeDraft.id.in_(draft_ids)
            )
        )
    )
    linked = (
        db.session.scalar(
            select(func.count(func.distinct(LegislativeDraftRequest.draft_id))).where(
                LegislativeDraftRequest.tenant_id == tenant_id,
                LegislativeDraftRequest.draft_id.in_(draft_ids),
            )
        )
        or 0
    )
    versions = (
        db.session.scalar(
            select(func.count()).select_from(LegislativeDraftVersion).where(
                LegislativeDraftVersion.tenant_id == tenant_id,
                LegislativeDraftVersion.draft_id.in_(draft_ids),
            )
        )
        or 0
    )
    tramitations = (
        db.session.scalar(
            select(func.count()).select_from(LegislativeTramitation).where(
                LegislativeTramitation.tenant_id == tenant_id,
                LegislativeTramitation.draft_id.in_(draft_ids),
            )
        )
        or 0
    )
    normative_sources = (
        db.session.scalar(
            select(func.count()).select_from(NormativeSource).where(
                NormativeSource.tenant_id == tenant_id, NormativeSource.id.in_(source_ids)
            )
        )
        or 0
    )
    return {
        "documents": len(documents),
        "draftsInProgress": sum(item.status != LegislativeDraftStatus.APROVADA for item in documents),
        "concludedPropositions": sum(
            item.status == LegislativeDraftStatus.APROVADA
            and item.current_tramitation_status is not None
            for item in documents
        ),
        "linkedDocuments": linked,
        "versions": versions,
        "tramitations": tramitations,
        "normativeSources": normative_sources,
        "documentsWithNormativeBasis": sum(bool(item.legal_basis) for item in documents),
    }


def seed(tenant_slug: str = "gabinete-302") -> dict:
    if current_app.config["APP_ENV"] != "staging":
        raise RuntimeError("This seed is restricted to APP_ENV=staging.")
    tenant = db.session.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
    if tenant is None:
        raise RuntimeError("tenant_not_found")
    actor = db.session.scalar(
        select(User).where(
            User.tenant_id == tenant.id,
            func.lower(User.email) == "dprata@gmail.com",
            User.status == UserStatus.ACTIVE,
        )
    )
    if actor is None:
        raise RuntimeError("daniel_operational_user_not_found")
    users = list(
        db.session.scalars(
            select(User)
            .where(User.tenant_id == tenant.id, User.status == UserStatus.ACTIVE)
            .order_by(User.created_at, User.id)
        )
    )
    authors = [item for item in users if item.role in {Role.STAFF, Role.MANAGER, Role.ADMIN}]
    if not authors:
        authors = [actor]
    approver = next(
        (
            item
            for item in users
            if item.role in {Role.REPRESENTATIVE, Role.ADMIN, Role.MANAGER}
        ),
        actor,
    )
    sources = _ensure_normative_sources(tenant, actor)
    requests, grouped_requests = _request_groups(tenant.id)
    territories = {
        territory_id: name
        for territory_id, name in db.session.execute(
            select(Territory.id, Territory.name).where(Territory.tenant_id == tenant.id)
        )
    }
    for index in range(TARGET_DOCUMENTS):
        _ensure_document(
            index,
            tenant,
            authors,
            approver,
            requests,
            grouped_requests,
            territories,
            sources,
        )
        if (index + 1) % 20 == 0:
            db.session.commit()
    counts = _counts(tenant.id)
    expected = {
        "documents": TARGET_DOCUMENTS,
        "draftsInProgress": TARGET_DOCUMENTS - TARGET_CONCLUDED_PROPOSITIONS,
        "concludedPropositions": TARGET_CONCLUDED_PROPOSITIONS,
        "linkedDocuments": TARGET_LINKED_DOCUMENTS,
        "versions": TARGET_DOCUMENTS + TARGET_CONCLUDED_PROPOSITIONS,
        "tramitations": TARGET_CONCLUDED_PROPOSITIONS * 4,
        "normativeSources": TARGET_NORMATIVE_SOURCES,
        "documentsWithNormativeBasis": TARGET_DOCUMENTS,
    }
    if counts != expected:
        raise RuntimeError(f"legislative_seed_validation_failed:{counts}")
    add_audit(
        tenant.id,
        actor.id,
        "staging.legislative_seed.completed",
        "tenant",
        tenant.id,
        after={"seedTag": SEED_TAG, "synthetic": True, **counts},
    )
    db.session.commit()
    return {"tenant": tenant.slug, "seedTag": SEED_TAG, **counts}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-slug", default="gabinete-302")
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        print(json.dumps(seed(args.tenant_slug), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
