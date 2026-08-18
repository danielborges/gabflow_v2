"""Idempotent synthetic workload for the Gabinete 302 staging tenant."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from unicodedata import combining, normalize

from flask import current_app
from sqlalchemy import func, select

from app import create_app
from app.audit import add_audit
from app.auth.security import hash_password
from app.extensions import db
from app.models import (
    Citizen,
    CitizenHistory,
    CitizenOrganizationLink,
    ConsentRecord,
    ElectoralCandidacy,
    ElectoralElection,
    ElectoralSectionResult,
    ElectoralTerritorialUnit,
    ElectoralUserCandidacy,
    ExternalAgency,
    ForwardingStatus,
    InteractionDirection,
    InteractionVisibility,
    Organization,
    RequestCategory,
    RequestForwarding,
    RequestHistory,
    RequestInteraction,
    RequestPriority,
    RequestSource,
    RequestStatus,
    Role,
    ServiceRequest,
    Tenant,
    Territory,
    User,
    UserStatus,
)

SEED_TAG = "STRESS-G302-20260817"
NAMESPACE = uuid.UUID("a870a1d8-f40d-45e5-8db6-1cfdf8df9729")
REFERENCE_START = datetime(2026, 1, 1, tzinfo=UTC)
TARGET_CITIZENS = 750
TARGET_ORGANIZATIONS = 150
TARGET_REQUESTS = 1500
TARGET_OVERDUE = 375

FIRST_NAMES = (
    "Ana Beatriz",
    "Adriana",
    "Aline",
    "Amanda",
    "André",
    "Antônio",
    "Bruna",
    "Camila",
    "Carlos Eduardo",
    "Carolina",
    "Cecília",
    "Cláudia",
    "Cristiane",
    "Daniel",
    "Débora",
    "Diego",
    "Eduardo",
    "Elaine",
    "Elisa",
    "Fábio",
    "Fernanda",
    "Gabriel",
    "Gisele",
    "Guilherme",
    "Helena",
    "Igor",
    "Isabela",
    "João Pedro",
    "Jorge",
    "Juliana",
    "Larissa",
    "Leonardo",
    "Letícia",
    "Lucas",
    "Luísa",
    "Marcelo",
    "Márcia",
    "Marcos",
    "Mariana",
    "Mateus",
    "Natália",
    "Paulo Henrique",
    "Priscila",
    "Rafael",
    "Renata",
    "Ricardo",
    "Roberta",
    "Sérgio",
    "Tatiana",
    "Vanessa",
)
LAST_NAMES = (
    "Almeida Silva",
    "Alves Pereira",
    "Barbosa Souza",
    "Carvalho Lima",
    "Costa Oliveira",
    "Dias Martins",
    "Ferreira Gomes",
    "Freitas Rocha",
    "Lopes Ribeiro",
    "Machado Santos",
    "Mendes Cardoso",
    "Moreira Teixeira",
    "Nascimento Vieira",
    "Rodrigues Castro",
    "Soares Monteiro",
)
PROFESSIONS = (
    "Auxiliar administrativo",
    "Comerciante",
    "Professora",
    "Motorista",
    "Técnica de enfermagem",
    "Autônomo",
    "Estudante",
    "Aposentada",
    "Pedreiro",
    "Analista de sistemas",
    "Cuidadora",
    "Vendedora",
    "Mecânico",
    "Cozinheira",
    "Servidor público",
    "Eletricista",
    "Artesã",
    "Recepcionista",
)

# Real public street names with deliberately synthetic house numbers and approximate
# neighborhood centroids. No record represents an actual resident or establishment.
NEIGHBORHOODS = (
    ("Linhares", "Rua Diva Garcia", -21.7480, -43.3180),
    ("São Mateus", "Rua São Mateus", -21.7780, -43.3500),
    ("Centro", "Rua Halfeld", -21.7610, -43.3490),
    ("Dom Bosco", "Rua João Manata", -21.7830, -43.3670),
    ("São Pedro", "Rua José Lourenço Kelmer", -21.7750, -43.3890),
    ("Morro da Glória", "Rua Senador Salgado Filho", -21.7450, -43.3560),
    ("Passos", "Rua Morais e Castro", -21.7770, -43.3410),
    ("Bom Pastor", "Rua Barão de São Marcelino", -21.7840, -43.3440),
    ("Granbery", "Rua Antônio Dias Tostes", -21.7690, -43.3420),
    ("Cascatinha", "Rua Nair Furtado de Souza", -21.7870, -43.3700),
    ("Santa Luzia", "Rua Porto das Flores", -21.7970, -43.3430),
    ("Vitorino Braga", "Avenida Brasil", -21.7520, -43.3350),
    ("Bom Jardim", "Rua Luiz Fávero", -21.7390, -43.3250),
    ("Bairu", "Rua Américo Lobo", -21.7420, -43.3390),
    ("Santa Terezinha", "Rua Custódio Tristão", -21.7340, -43.3440),
    ("Manoel Honório", "Avenida Rio Branco", -21.7490, -43.3430),
    ("Mariano Procópio", "Rua Mariano Procópio", -21.7420, -43.3690),
    ("Teixeiras", "Avenida Deusdedith Salgado", -21.7970, -43.3620),
    ("Jardim Glória", "Rua Quintino Bocaiúva", -21.7510, -43.3610),
    ("Bandeirantes", "Rua Laurindo Nocelli", -21.7300, -43.3260),
    ("Grajaú", "Rua Doutor Leonel Jaguaribe", -21.7580, -43.3300),
    ("Benfica", "Rua Evaristo da Veiga", -21.6920, -43.4380),
    ("Nova Era", "Rua Guimarães Júnior", -21.7040, -43.4150),
    ("Progresso", "Rua Jorge Knopp", -21.7270, -43.3370),
    ("Santa Helena", "Rua Olegário Maciel", -21.7560, -43.3590),
)

REQUEST_CASES = (
    (
        "Iluminação pública",
        "Luminária apagada",
        "Moradores relatam que a luminária está apagada há vários dias, deixando o "
        "trecho escuro e inseguro no período noturno.",
        "A equipe de iluminação realizou a troca do conjunto e confirmou o "
        "funcionamento no período da noite.",
        "Secretaria Municipal de Serviços Urbanos",
    ),
    (
        "Tapa-buraco e pavimentação",
        "Buraco na via",
        "Foi identificado um buraco de grande dimensão na pista, com risco para "
        "motociclistas e prejuízo ao tráfego local.",
        "A operação tapa-buraco recompôs o pavimento e liberou a via após vistoria técnica.",
        "Secretaria Municipal de Obras",
    ),
    (
        "Saúde",
        "Consulta especializada",
        "A família solicita apoio para verificar a fila de consulta especializada já "
        "encaminhada pela unidade básica de saúde.",
        "A Secretaria de Saúde localizou o encaminhamento e informou data, unidade e "
        "orientações para o atendimento.",
        "Secretaria Municipal de Saúde",
    ),
    (
        "Coleta de lixo",
        "Coleta irregular",
        "A coleta domiciliar não ocorreu nas últimas passagens previstas e há acúmulo "
        "de resíduos próximo às residências.",
        "O roteiro da coleta foi regularizado e a equipe retirou os resíduos acumulados no local.",
        "Secretaria Municipal de Serviços Urbanos",
    ),
    (
        "Trânsito e sinalização",
        "Sinalização desgastada",
        "A faixa de pedestres está apagada e os moradores pedem reforço da sinalização "
        "para reduzir o risco de acidentes.",
        "A sinalização horizontal foi refeita e a travessia recebeu nova vistoria da "
        "equipe de mobilidade.",
        "Secretaria Municipal de Mobilidade Urbana e Transporte",
    ),
    (
        "Transporte público",
        "Horário de ônibus",
        "Usuários relatam demora excessiva e pedem verificação do cumprimento dos "
        "horários da linha que atende o bairro.",
        "A fiscalização notificou a operadora e confirmou o restabelecimento dos "
        "horários programados.",
        "Secretaria Municipal de Mobilidade Urbana e Transporte",
    ),
    (
        "Limpeza urbana",
        "Limpeza de praça",
        "A praça apresenta mato alto e resíduos nas áreas de convivência, dificultando "
        "o uso por crianças e idosos.",
        "Foi executado serviço de capina, varrição e retirada dos resíduos da área pública.",
        "Secretaria Municipal de Serviços Urbanos",
    ),
    (
        "Defesa animal",
        "Animal em situação de risco",
        "Moradores comunicam a presença de animal debilitado em área pública e "
        "solicitam avaliação e recolhimento responsável.",
        "A equipe realizou o atendimento, encaminhou o animal para avaliação e "
        "registrou a destinação adequada.",
        "Prefeitura Municipal de Juiz de Fora",
    ),
    (
        "Assistência social emergencial",
        "Família em vulnerabilidade",
        "Foi solicitada avaliação social para família com dificuldade temporária de "
        "alimentação e acesso a benefícios.",
        "A equipe de referência fez o acolhimento, atualizou o cadastro e orientou "
        "sobre os benefícios disponíveis.",
        "Secretaria Municipal de Assistência Social",
    ),
    (
        "Educação",
        "Manutenção em escola",
        "Responsáveis informam necessidade de reparo em área de circulação da escola "
        "municipal para garantir segurança dos estudantes.",
        "A manutenção corretiva foi concluída e a direção escolar confirmou a "
        "liberação segura do espaço.",
        "Secretaria Municipal de Educação",
    ),
    (
        "Saneamento básico",
        "Vazamento em via pública",
        "Há vazamento contínuo próximo ao meio-fio, com desperdício de água e formação "
        "de poça na passagem de pedestres.",
        "A equipe técnica reparou a rede, recompôs o trecho e confirmou a interrupção "
        "do vazamento.",
        "Prefeitura Municipal de Juiz de Fora",
    ),
    (
        "Acessibilidade urbana",
        "Calçada sem acessibilidade",
        "Pessoa com mobilidade reduzida relata obstáculo na calçada e ausência de "
        "rebaixamento adequado para travessia.",
        "O local foi vistoriado e a adequação de acessibilidade foi executada conforme "
        "orientação técnica.",
        "Secretaria Municipal de Planejamento Urbano",
    ),
    (
        "Habitação",
        "Orientação habitacional",
        "A cidadã solicita informações sobre atualização cadastral e critérios de "
        "atendimento dos programas municipais de habitação.",
        "A equipe conferiu o cadastro e forneceu orientações sobre documentos, "
        "critérios e acompanhamento do processo.",
        "Secretaria Municipal de Habitação",
    ),
    (
        "Segurança pública",
        "Ronda preventiva",
        "Comerciantes solicitam reforço de ronda nos horários de abertura e fechamento "
        "após ocorrências recentes na região.",
        "A demanda foi incluída no planejamento de patrulhamento e houve retorno à "
        "comunidade sobre os horários de ronda.",
        "Guarda Municipal",
    ),
    (
        "Meio ambiente",
        "Poda preventiva",
        "Galhos de árvore estão próximos da rede e encobrem parte da iluminação, "
        "exigindo avaliação e poda tecnicamente orientada.",
        "A vistoria autorizou o manejo e a poda preventiva foi realizada sem danos à arborização.",
        "Secretaria Municipal de Meio Ambiente",
    ),
)

ORGANIZATION_PREFIXES = (
    ("Associação Comunitária", "ASSOCIACAO"),
    ("Instituto Social", "INSTITUTO"),
    ("Coletivo Cultural", "COLETIVO"),
    ("Grupo de Apoio", "GRUPO_COMUNITARIO"),
    ("Clube Esportivo", "ENTIDADE_ESPORTIVA"),
    ("Rede Solidária", "REDE_SOLIDARIA"),
)


def _id(kind: str, index: int | str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{SEED_TAG}:{kind}:{index}")


def _key(value: str) -> str:
    text = " ".join(value.casefold().split())
    return "".join(char for char in normalize("NFKD", text) if not combining(char))


def _weighted_neighborhood(rng: random.Random, top_name: str):
    top = next(
        (item for item in NEIGHBORHOODS if _key(item[0]) == _key(top_name)), NEIGHBORHOODS[0]
    )
    others = [item for item in NEIGHBORHOODS if item != top]
    return top if rng.random() < 0.35 else rng.choice(others)


def _official_top_neighborhood(tenant_id: uuid.UUID) -> tuple[str, int]:
    row = db.session.execute(
        select(ElectoralTerritorialUnit.neighborhood, func.sum(ElectoralSectionResult.votes))
        .join(
            ElectoralSectionResult,
            ElectoralSectionResult.territory_id == ElectoralTerritorialUnit.id,
        )
        .join(ElectoralCandidacy, ElectoralCandidacy.id == ElectoralSectionResult.candidacy_id)
        .join(ElectoralUserCandidacy, ElectoralUserCandidacy.candidacy_id == ElectoralCandidacy.id)
        .join(ElectoralElection, ElectoralElection.id == ElectoralCandidacy.election_id)
        .where(
            ElectoralUserCandidacy.tenant_id == tenant_id,
            ElectoralElection.year == 2024,
            ElectoralTerritorialUnit.neighborhood.is_not(None),
        )
        .group_by(ElectoralTerritorialUnit.neighborhood)
        .order_by(func.sum(ElectoralSectionResult.votes).desc())
        .limit(1)
    ).first()
    return (row[0], int(row[1])) if row else (NEIGHBORHOODS[0][0], 0)


def _ensure_workers(tenant: Tenant, actor: User) -> list[User]:
    workers = [actor]
    for number in range(1, 6):
        name = f"Assessor_{number:02d}"
        email = f"assessor_{number:02d}@gabinete302.staging"
        item = db.session.get(User, _id("worker", number))
        if item is None:
            item = db.session.scalar(select(User).where(func.lower(User.email) == email))
        if item is None:
            item = User(
                id=_id("worker", number),
                tenant_id=tenant.id,
                name=name,
                email=email,
                password_hash=hash_password(secrets.token_urlsafe(48)),
                role=Role.STAFF,
                status=UserStatus.ACTIVE,
            )
            db.session.add(item)
            db.session.flush()
            add_audit(
                tenant.id,
                actor.id,
                "user.created",
                "user",
                item.id,
                after={"name": name, "email": email, "role": Role.STAFF.value, "seedTag": SEED_TAG},
            )
        else:
            item.name = name
            item.tenant_id = tenant.id
            item.role = Role.STAFF
            item.status = UserStatus.ACTIVE
        workers.append(item)
    db.session.commit()
    return workers


def _ensure_territories(tenant: Tenant) -> dict[str, Territory]:
    result = {}
    for index, (name, _street, _lat, _lon) in enumerate(NEIGHBORHOODS):
        item = db.session.scalar(
            select(Territory).where(
                Territory.tenant_id == tenant.id, func.lower(Territory.name) == name.lower()
            )
        )
        if item is None:
            item = Territory(
                id=_id("territory", index), tenant_id=tenant.id, name=name, aliases=[], active=True
            )
            db.session.add(item)
        result[_key(name)] = item
    db.session.commit()
    return result


def _address(neighborhood, index: int, territory: Territory, rng: random.Random) -> dict:
    name, street, base_lat, base_lon = neighborhood
    number = 20 + ((index * 37) % 1980)
    latitude = round(base_lat + rng.uniform(-0.0042, 0.0042), 6)
    longitude = round(base_lon + rng.uniform(-0.0042, 0.0042), 6)
    return {
        "endereco": f"{street}, {number} - {name}, Juiz de Fora - MG",
        "logradouro": street,
        "numero": str(number),
        "complemento": None,
        "cep": None,
        "bairro": name,
        "cidade": "Juiz de Fora",
        "uf": "MG",
        "latitude": latitude,
        "longitude": longitude,
        "placeId": None,
        "territorioId": str(territory.id),
        "territorio": territory.name,
        "statusResolucao": "RESOLVIDO",
        "metodoResolucao": "NOME",
    }


def _ensure_citizens(
    tenant: Tenant, workers: list[User], territories, top_name: str
) -> list[Citizen]:
    rng = random.Random(302_750)  # noqa: S311 - deterministic synthetic fixture
    citizens = []
    for index in range(TARGET_CITIZENS):
        item = db.session.get(Citizen, _id("citizen", index))
        if item is None:
            neighborhood = _weighted_neighborhood(rng, top_name)
            territory = territories[_key(neighborhood[0])]
            address = _address(neighborhood, index, territory, rng)
            given = FIRST_NAMES[index % len(FIRST_NAMES)]
            surname = LAST_NAMES[(index // len(FIRST_NAMES)) % len(LAST_NAMES)]
            creator = workers[index % len(workers)]
            created_at = REFERENCE_START + timedelta(days=index % 225, hours=index % 18)
            item = Citizen(
                id=_id("citizen", index),
                tenant_id=tenant.id,
                name=f"{given} {surname}",
                profession=PROFESSIONS[index % len(PROFESSIONS)],
                birth_date=date(1945 + (index % 59), 1 + (index % 12), 1 + (index % 27)),
                vip=index % 29 == 0,
                contacts=[
                    {"tipo": "WHATSAPP", "valor": f"329{70000000 + index:08d}"},
                    {"tipo": "EMAIL", "valor": f"cidadao.{index + 1:04d}@example.test"},
                ],
                addresses=[address],
                preferred_channel="WHATSAPP",
                contact_consent=index % 5 != 0,
                publication_consent=False,
                legal_basis="EXECUCAO_DE_POLITICAS_PUBLICAS",
                privacy_flags=["DADOS_SINTETICOS_STAGING"],
                notes=f"[{SEED_TAG}] Cadastro sintético para teste de carga.",
                created_by_id=creator.id,
                created_at=created_at,
                updated_at=created_at,
            )
            db.session.add(item)
            db.session.add(
                CitizenHistory(
                    id=_id("citizen-history", index),
                    tenant_id=tenant.id,
                    citizen_id=item.id,
                    user_id=creator.id,
                    action="CADASTRO_CRIADO",
                    changed_fields=["nome", "contatos", "enderecos"],
                    metadata_summary={"seedTag": SEED_TAG, "synthetic": True},
                    created_at=created_at,
                )
            )
            for purpose, granted in (("CONTATO", item.contact_consent), ("DIVULGACAO", False)):
                db.session.add(
                    ConsentRecord(
                        id=_id(f"consent-{purpose.lower()}", index),
                        tenant_id=tenant.id,
                        citizen_id=item.id,
                        purpose=purpose,
                        granted=granted,
                        legal_basis=item.legal_basis,
                        source="CARGA_SINTETICA_STAGING",
                        evidence=f"[{SEED_TAG}]",
                        recorded_by_id=creator.id,
                        recorded_at=created_at,
                    )
                )
        citizens.append(item)
        if (index + 1) % 150 == 0:
            db.session.commit()
    db.session.commit()
    return citizens


def _ensure_organizations(
    tenant: Tenant, actor: User, citizens: list[Citizen], territories
) -> list[Organization]:
    rng = random.Random(302_150)  # noqa: S311 - deterministic synthetic fixture
    organizations = []
    for index in range(TARGET_ORGANIZATIONS):
        item = db.session.get(Organization, _id("organization", index))
        if item is None:
            prefix, organization_type = ORGANIZATION_PREFIXES[index // len(NEIGHBORHOODS)]
            neighborhood = NEIGHBORHOODS[index % len(NEIGHBORHOODS)]
            territory = territories[_key(neighborhood[0])]
            address = _address(neighborhood, 2000 + index, territory, rng)
            item = Organization(
                id=_id("organization", index),
                tenant_id=tenant.id,
                name=f"{prefix} de {neighborhood[0]}",
                organization_type=organization_type,
                contacts=[
                    {"tipo": "TELEFONE", "valor": f"3232{400000 + index:06d}"},
                    {"tipo": "EMAIL", "valor": f"organizacao.{index + 1:03d}@example.test"},
                ],
                addresses=[address],
                territory=neighborhood[0],
                notes=f"[{SEED_TAG}] Organização sintética para teste de carga.",
                created_at=REFERENCE_START + timedelta(days=index % 180),
            )
            db.session.add(item)
        organizations.append(item)
    db.session.flush()
    # 120/150 organizations (80%) receive at least one citizen link. Every third
    # linked organization receives a second member to exercise many-to-many views.
    for index, organization in enumerate(organizations[:120]):
        member_count = 2 if index % 3 == 0 else 1
        for member in range(member_count):
            link_id = _id("organization-link", f"{index}-{member}")
            if db.session.get(CitizenOrganizationLink, link_id) is None:
                db.session.add(
                    CitizenOrganizationLink(
                        id=link_id,
                        tenant_id=tenant.id,
                        citizen_id=citizens[(index * 5 + member * 17) % len(citizens)].id,
                        organization_id=organization.id,
                        role="RESPONSAVEL" if member == 0 else "MEMBRO",
                        created_by_id=actor.id,
                        created_at=REFERENCE_START + timedelta(days=index % 180),
                    )
                )
    db.session.commit()
    return organizations


def _category_for(case, categories: list[RequestCategory]) -> RequestCategory:
    expected = _key(case[0])
    return next((item for item in categories if _key(item.name) == expected), categories[0])


def _agency_for(name: str, agencies: list[ExternalAgency]) -> ExternalAgency:
    expected = _key(name)
    return next((item for item in agencies if _key(item.name) == expected), agencies[0])


def _request_state(index: int, created_at: datetime, now: datetime, sla_hours: int):
    if index < TARGET_OVERDUE:
        status = (
            RequestStatus.TRIAGEM,
            RequestStatus.EM_ATENDIMENTO,
            RequestStatus.AGUARDANDO_ORGAO,
            RequestStatus.AGUARDANDO_CIDADAO,
        )[index % 4]
        return status, created_at + timedelta(hours=min(sla_hours, 120)), None
    if index < 675:
        status = (RequestStatus.NOVA, RequestStatus.TRIAGEM, RequestStatus.EM_ATENDIMENTO)[
            index % 3
        ]
        return status, now + timedelta(days=1 + index % 30), None
    if index < 1275:
        closed_at = min(now - timedelta(hours=1), created_at + timedelta(days=2 + index % 18))
        return RequestStatus.RESOLVIDA, created_at + timedelta(hours=sla_hours), closed_at
    if index < 1425:
        closed_at = min(now - timedelta(hours=1), created_at + timedelta(days=3 + index % 24))
        return RequestStatus.ENCERRADA, created_at + timedelta(hours=sla_hours), closed_at
    closed_at = min(now - timedelta(hours=1), created_at + timedelta(days=1 + index % 7))
    return RequestStatus.CANCELADA, created_at + timedelta(hours=sla_hours), closed_at


def _ensure_requests(tenant, workers, citizens, organizations, territories, top_name, now):
    rng = random.Random(302_1500)  # noqa: S311 - deterministic synthetic fixture
    categories = list(
        db.session.scalars(
            select(RequestCategory)
            .where(RequestCategory.tenant_id == tenant.id, RequestCategory.active.is_(True))
            .order_by(RequestCategory.name)
        )
    )
    agencies = list(
        db.session.scalars(
            select(ExternalAgency)
            .where(ExternalAgency.tenant_id == tenant.id, ExternalAgency.active.is_(True))
            .order_by(ExternalAgency.name)
        )
    )
    if not categories or not agencies:
        raise RuntimeError("categories_or_agencies_missing")
    source_values = list(RequestSource)
    created_span = max(1, int((now - REFERENCE_START).total_seconds()))
    for index in range(TARGET_REQUESTS):
        request_id = _id("request", index)
        if db.session.get(ServiceRequest, request_id) is not None:
            continue
        case = REQUEST_CASES[index % len(REQUEST_CASES)]
        category = _category_for(case, categories)
        agency = _agency_for(case[4], agencies)
        neighborhood = _weighted_neighborhood(rng, top_name)
        territory = territories[_key(neighborhood[0])]
        address = _address(neighborhood, 5000 + index, territory, rng)
        if index < TARGET_OVERDUE:
            overdue_end = now - timedelta(days=10)
            span = max(1, int((overdue_end - REFERENCE_START).total_seconds()))
            created_at = REFERENCE_START + timedelta(seconds=rng.randrange(span))
        elif index >= 675:
            closed_span = max(1, int((now - timedelta(days=5) - REFERENCE_START).total_seconds()))
            created_at = REFERENCE_START + timedelta(seconds=rng.randrange(closed_span))
        else:
            created_at = REFERENCE_START + timedelta(seconds=rng.randrange(created_span))
        status, due_at, closed_at = _request_state(index, created_at, now, category.sla_hours)
        creator = workers[index % len(workers)]
        responsible = workers[(index * 5 + 1) % len(workers)]
        citizen = citizens[(index * 47) % len(citizens)] if index % 9 != 0 else None
        organization = organizations[(index * 11) % len(organizations)] if index % 5 == 0 else None
        priority = (
            RequestPriority.BAIXA,
            RequestPriority.MEDIA,
            RequestPriority.MEDIA,
            RequestPriority.ALTA,
            RequestPriority.CRITICA,
        )[index % 5]
        item = ServiceRequest(
            id=request_id,
            tenant_id=tenant.id,
            protocol=f"ST302-2026-{index + 1:04d}",
            public_protocol=f"GFW-ST302{index + 1:08d}",
            source=source_values[index % len(source_values)],
            title=case[1],
            description=f"{case[2]} Referência: {address['endereco']}.",
            status=status,
            priority=priority,
            address=address["endereco"],
            latitude=address["latitude"],
            longitude=address["longitude"],
            geocode_source="STAGING_SYNTHETIC_GOVERNED",
            geocode_method="APPROXIMATE_NEIGHBORHOOD_CENTROID",
            geocode_confidence=0.82,
            geocode_verified=False,
            geocode_status="APPROXIMATE",
            geocoded_at=created_at,
            category=category.name,
            category_id=category.id,
            subcategory=case[1],
            theme=case[0],
            territory_id=territory.id,
            agency_id=agency.id,
            impact=("BAIXO", "MEDIO", "ALTO")[index % 3],
            urgency=("BAIXA", "MEDIA", "ALTA")[index % 3],
            citizen_id=citizen.id if citizen else None,
            organization_id=organization.id if organization else None,
            responsible_id=responsible.id,
            due_at=due_at,
            closing_reason=(
                "Demanda atendida e retorno registrado."
                if status in {RequestStatus.RESOLVIDA, RequestStatus.ENCERRADA}
                else "Registro cancelado após confirmação de duplicidade."
                if status == RequestStatus.CANCELADA
                else None
            ),
            closing_evidence=(
                case[3] if status in {RequestStatus.RESOLVIDA, RequestStatus.ENCERRADA} else None
            ),
            closed_at=closed_at,
            public_access_key_hash=hashlib.sha256(f"{SEED_TAG}:{index}".encode()).hexdigest(),
            created_by_id=creator.id,
            created_at=created_at,
            updated_at=closed_at or min(now, created_at + timedelta(days=1 + index % 10)),
        )
        db.session.add(item)
        db.session.add(
            RequestHistory(
                id=_id("request-history-created", index),
                tenant_id=tenant.id,
                request_id=item.id,
                user_id=creator.id,
                action="request.created",
                changes={
                    "protocol": {"antes": None, "depois": item.protocol},
                    "status": {"antes": None, "depois": RequestStatus.NOVA.value},
                    "seedTag": SEED_TAG,
                },
                created_at=created_at,
            )
        )
        if status in {RequestStatus.RESOLVIDA, RequestStatus.ENCERRADA}:
            forwarded_at = min(
                closed_at - timedelta(hours=8), created_at + timedelta(hours=4 + index % 18)
            )
            response_at = min(
                closed_at - timedelta(hours=2), forwarded_at + timedelta(days=1 + index % 8)
            )
            forwarding = RequestForwarding(
                id=_id("forwarding", index),
                tenant_id=tenant.id,
                request_id=item.id,
                agency_id=agency.id,
                external_protocol=f"PMJF-{2026}-{index + 31000:06d}",
                notes=(
                    "Ofício encaminhado com dados da demanda e referência territorial "
                    f"de {neighborhood[0]}."
                ),
                status=ForwardingStatus.RESPONDIDO,
                response=case[3],
                response_at=response_at,
                due_at=forwarded_at + timedelta(days=10),
                created_by_id=responsible.id,
                created_at=forwarded_at,
                updated_at=response_at,
            )
            db.session.add(forwarding)
            db.session.add_all(
                [
                    RequestInteraction(
                        id=_id("interaction-forwarded", index),
                        tenant_id=tenant.id,
                        request_id=item.id,
                        interaction_type="ENCAMINHAMENTO",
                        channel="OFICIO_ELETRONICO",
                        direction=InteractionDirection.SAIDA,
                        content=(
                            f"Demanda encaminhada para {agency.name}, protocolo "
                            f"{forwarding.external_protocol}."
                        ),
                        visibility=InteractionVisibility.INTERNA,
                        author_id=responsible.id,
                        created_at=forwarded_at,
                    ),
                    RequestInteraction(
                        id=_id("interaction-response", index),
                        tenant_id=tenant.id,
                        request_id=item.id,
                        interaction_type="RESPOSTA_ORGAO",
                        channel="ORGAO_EXTERNO",
                        direction=InteractionDirection.ENTRADA,
                        content=case[3],
                        visibility=InteractionVisibility.INTERNA,
                        author_id=responsible.id,
                        created_at=response_at,
                    ),
                    RequestInteraction(
                        id=_id("interaction-citizen", index),
                        tenant_id=tenant.id,
                        request_id=item.id,
                        interaction_type="RETORNO_AO_CIDADAO",
                        channel=item.source.value,
                        direction=InteractionDirection.SAIDA,
                        content=f"Retorno prestado ao solicitante: {case[3]}",
                        visibility=InteractionVisibility.CIDADAO,
                        author_id=responsible.id,
                        created_at=closed_at,
                    ),
                    RequestHistory(
                        id=_id("request-history-closed", index),
                        tenant_id=tenant.id,
                        request_id=item.id,
                        user_id=responsible.id,
                        action="request.resolved"
                        if status == RequestStatus.RESOLVIDA
                        else "request.closed",
                        changes={
                            "status": {
                                "antes": RequestStatus.EM_ATENDIMENTO.value,
                                "depois": status.value,
                            },
                            "seedTag": SEED_TAG,
                        },
                        created_at=closed_at,
                    ),
                ]
            )
        elif status == RequestStatus.AGUARDANDO_ORGAO:
            forwarded_at = created_at + timedelta(hours=6)
            db.session.add(
                RequestForwarding(
                    id=_id("forwarding", index),
                    tenant_id=tenant.id,
                    request_id=item.id,
                    agency_id=agency.id,
                    external_protocol=f"PMJF-{2026}-{index + 31000:06d}",
                    notes="Encaminhamento aguardando resposta técnica do órgão competente.",
                    status=ForwardingStatus.AGUARDANDO_RETORNO,
                    due_at=due_at,
                    created_by_id=responsible.id,
                    created_at=forwarded_at,
                    updated_at=forwarded_at,
                )
            )
        if (index + 1) % 100 == 0:
            db.session.commit()
    db.session.commit()


def _seed_counts(tenant_id: uuid.UUID) -> dict:
    marker = f"[{SEED_TAG}]%"
    workers = (
        db.session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.tenant_id == tenant_id, User.email.like("assessor_%@gabinete302.staging"))
        )
        or 0
    )
    citizens = (
        db.session.scalar(
            select(func.count())
            .select_from(Citizen)
            .where(Citizen.tenant_id == tenant_id, Citizen.notes.like(marker))
        )
        or 0
    )
    organizations = (
        db.session.scalar(
            select(func.count())
            .select_from(Organization)
            .where(Organization.tenant_id == tenant_id, Organization.notes.like(marker))
        )
        or 0
    )
    requests = (
        db.session.scalar(
            select(func.count())
            .select_from(ServiceRequest)
            .where(
                ServiceRequest.tenant_id == tenant_id, ServiceRequest.protocol.like("ST302-2026-%")
            )
        )
        or 0
    )
    overdue = (
        db.session.scalar(
            select(func.count())
            .select_from(ServiceRequest)
            .where(
                ServiceRequest.tenant_id == tenant_id,
                ServiceRequest.protocol.like("ST302-2026-%"),
                ServiceRequest.due_at < datetime.now(UTC),
                ServiceRequest.status.not_in(
                    [RequestStatus.RESOLVIDA, RequestStatus.ENCERRADA, RequestStatus.CANCELADA]
                ),
            )
        )
        or 0
    )
    linked_organizations = (
        db.session.scalar(
            select(func.count(func.distinct(CitizenOrganizationLink.organization_id))).where(
                CitizenOrganizationLink.tenant_id == tenant_id,
                CitizenOrganizationLink.organization_id.in_(
                    select(Organization.id).where(
                        Organization.tenant_id == tenant_id, Organization.notes.like(marker)
                    )
                ),
            )
        )
        or 0
    )
    return {
        "workers": workers,
        "citizens": citizens,
        "organizations": organizations,
        "linkedOrganizations": linked_organizations,
        "requests": requests,
        "overdueRequests": overdue,
    }


def seed(tenant_slug: str, *, now: datetime | None = None) -> dict:
    if current_app.config["APP_ENV"] != "staging":
        raise RuntimeError("This seed is restricted to APP_ENV=staging.")
    tenant = db.session.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
    if tenant is None:
        raise RuntimeError("tenant_not_found")
    actor = db.session.scalar(
        select(User).where(
            User.tenant_id == tenant.id, func.lower(User.email) == "dprata@gmail.com"
        )
    )
    if actor is None or actor.role != Role.STAFF:
        raise RuntimeError("daniel_operational_user_not_found")
    reference = (now or datetime.now(UTC)).astimezone(UTC)
    top_name, top_votes = _official_top_neighborhood(tenant.id)
    workers = _ensure_workers(tenant, actor)
    territories = _ensure_territories(tenant)
    citizens = _ensure_citizens(tenant, workers, territories, top_name)
    organizations = _ensure_organizations(tenant, actor, citizens, territories)
    _ensure_requests(tenant, workers, citizens, organizations, territories, top_name, reference)
    counts = _seed_counts(tenant.id)
    expected = {
        "workers": 5,
        "citizens": TARGET_CITIZENS,
        "organizations": TARGET_ORGANIZATIONS,
        "linkedOrganizations": 120,
        "requests": TARGET_REQUESTS,
        "overdueRequests": TARGET_OVERDUE,
    }
    if counts != expected:
        raise RuntimeError(f"seed_validation_failed:{counts}")
    add_audit(
        tenant.id,
        actor.id,
        "staging.stress_seed.completed",
        "tenant",
        tenant.id,
        after={
            "seedTag": SEED_TAG,
            "synthetic": True,
            "officialTopNeighborhood": top_name,
            "officialTopVotes": top_votes,
            **counts,
        },
    )
    db.session.commit()
    return {
        "tenant": tenant.slug,
        "seedTag": SEED_TAG,
        "officialTopNeighborhood": top_name,
        "officialTopVotes": top_votes,
        **counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-slug", default="gabinete-302")
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        print(json.dumps(seed(args.tenant_slug), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
