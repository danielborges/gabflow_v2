"""political parties catalog

Revision ID: f7d2a1c4b6e8
Revises: f6c1d2e3a4b5
Create Date: 2026-07-21 18:20:00
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "f7d2a1c4b6e8"
down_revision = "f6c1d2e3a4b5"
branch_labels = None
depends_on = None

SOURCE_BASE = "https://www.tse.jus.br/partidos/partidos-registrados-no-tse"

PARTIES = [
    ("MDB", "MOVIMENTO DEMOCRÁTICO BRASILEIRO", 15, "30.6.1981", "LUIZ FELIPE BALEIA TENUTO ROSSI", "movimento-democratico-brasileiro"),
    ("PDT", "PARTIDO DEMOCRÁTICO TRABALHISTA", 12, "10.11.1981", "CARLOS ROBERTO LUPI", "partido-democratico-trabalhista"),
    ("PT", "PARTIDO DOS TRABALHADORES", 13, "11.2.1982", "EDSON ANTONIO EDINHO DA SILVA", "partido-dos-trabalhadores"),
    ("PCdoB", "PARTIDO COMUNISTA DO BRASIL", 65, "23.6.1988", "NÁDIA CAMPEÃO", "partido-comunista-do-brasil"),
    ("PSB", "PARTIDO SOCIALISTA BRASILEIRO", 40, "1.7.1988", "JOÃO HENRIQUE DE ANDRADE LIMA CAMPOS", "partido-socialista-brasileiro"),
    ("PSDB", "PARTIDO DA SOCIAL DEMOCRACIA BRASILEIRA", 45, "24.8.1989", "AÉCIO NEVES DA CUNHA", "partido-da-social-democracia-brasileira"),
    ("AGIR", "AGIR", 36, "22.2.1990", "DANIEL S. TOURINHO", "agir"),
    ("MOBILIZA", "MOBILIZAÇÃO NACIONAL", 33, "25.10.1990", "ANTONIO CARLOS BOSCO MASSAROLLO", "mobilizacao-nacional"),
    ("CIDADANIA", "CIDADANIA", 23, "19.3.1992", "ALEX SPINELLI MANENTE", "cidadania"),
    ("PV", "PARTIDO VERDE", 43, "30.9.1993", "JOSÉ LUIZ DE FRANÇA PENNA", "partido-verde"),
    ("AVANTE", "AVANTE", 70, "11.10.1994", "LUIS HENRIQUE DE OLIVEIRA RESENDE", "avante"),
    ("PP", "PROGRESSISTAS", 11, "16.11.1995", "CIRO NOGUEIRA LIMA FILHO", "progressistas"),
    ("PSTU", "PARTIDO SOCIALISTA DOS TRABALHADORES UNIFICADO", 16, "19.12.1995", "JOSÉ MARIA DE ALMEIDA", "partido-socialista-dos-trabalhadores-unificado"),
    ("PCB", "PARTIDO COMUNISTA BRASILEIRO", 21, "9.5.1996", "EDMILSON SILVA COSTA", "partido-comunista-brasileiro"),
    ("PRTB", "PARTIDO RENOVADOR TRABALHISTA BRASILEIRO", 28, "18.2.1997", "LEONARDO ALVES DE ARAÚJO", "partido-renovador-trabalhista-brasileiro"),
    ("DC", "DEMOCRACIA CRISTÃ", 27, "5.8.1997", "JOÃO CALDAS DA SILVA", "democracia-crista"),
    ("PCO", "PARTIDO DA CAUSA OPERÁRIA", 29, "30.9.1997", "RUI COSTA PIMENTA", "partido-da-causa-operaria"),
    ("PODE", "PODEMOS", 20, "2.10.1997", "RENATA HELLMEISTER DE ABREU", "podemos"),
    ("REPUBLICANOS", "REPUBLICANOS", 10, "25.8.2005", "MARCOS ANTONIO PEREIRA", "republicanos"),
    ("PSOL", "PARTIDO SOCIALISMO E LIBERDADE", 50, "15.9.2005", "PAULA BERMUDES MORAES CORADI", "partido-socialismo-e-liberdade"),
    ("PL", "PARTIDO LIBERAL", 22, "19.12.2006", "VALDEMAR COSTA NETO", "partido-liberal"),
    ("PSD", "PARTIDO SOCIAL DEMOCRÁTICO", 55, "27.9.2011", "GILBERTO KASSAB", "partido-social-democratico"),
    ("SOLIDARIEDADE", "SOLIDARIEDADE", 77, "24.9.2013", "PAULO PEREIRA DA SILVA", "solidariedade"),
    ("NOVO", "PARTIDO NOVO", 30, "15.9.2015", "EDUARDO RODRIGO FERNANDES RIBEIRO", "partido-novo"),
    ("REDE", "REDE SUSTENTABILIDADE", 18, "22.9.2015", "PAULO ROBERTO LAMAC JUNIOR", "rede-sustentabilidade"),
    ("DEMOCRATA", "DEMOCRATA", 35, "29.9.2015", "SUÊD HAIDAR NOGUEIRA", "democrata"),
    ("UP", "UNIDADE POPULAR", 80, "10.12.2019", "LEONARDO PERICLES VIEIRA ROQUE", "unidade-popular"),
    ("UNIÃO", "UNIÃO BRASIL", 44, "8.2.2022", "ANTÔNIO EDUARDO GONÇALVES DE RUEDA", "uniao-brasil"),
    ("PRD", "PARTIDO RENOVAÇÃO DEMOCRÁTICA", 25, "9.11.2023", "MARCUS VINÍCIUS DE VASCONCELOS FERREIRA", "partido-renovacao-democratica"),
    ("MISSÃO", "PARTIDO MISSÃO", 14, "4.11.2025", "RENAN ANTONIO FERREIRA DOS SANTOS", "partido-missao"),
]


def upgrade():
    op.create_table(
        "political_parties",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("acronym", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("ballot_number", sa.Integer(), nullable=False),
        sa.Column("registration_date", sa.String(length=20), nullable=True),
        sa.Column("national_president", sa.String(length=180), nullable=True),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("acronym"),
        sa.UniqueConstraint("ballot_number"),
    )
    op.create_index("ix_political_parties_acronym", "political_parties", ["acronym"])
    op.create_index("ix_political_parties_active", "political_parties", ["active"])

    rows = [
        {
            "id": uuid.uuid4(),
            "acronym": acronym,
            "name": name,
            "ballot_number": number,
            "registration_date": registration_date,
            "national_president": president,
            "logo_url": None,
            "source_url": f"{SOURCE_BASE}/{slug}",
        }
        for acronym, name, number, registration_date, president, slug in PARTIES
    ]
    op.bulk_insert(sa.table(
        "political_parties",
        sa.column("acronym", sa.String),
        sa.column("id", sa.Uuid),
        sa.column("name", sa.String),
        sa.column("ballot_number", sa.Integer),
        sa.column("registration_date", sa.String),
        sa.column("national_president", sa.String),
        sa.column("logo_url", sa.Text),
        sa.column("source_url", sa.Text),
    ), rows)


def downgrade():
    op.drop_index("ix_political_parties_active", table_name="political_parties")
    op.drop_index("ix_political_parties_acronym", table_name="political_parties")
    op.drop_table("political_parties")
