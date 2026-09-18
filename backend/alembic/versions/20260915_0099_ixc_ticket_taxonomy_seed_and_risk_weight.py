"""Popula a taxonomia do Atendimento IXC (tema/categoria) e adiciona `risk_weight`

Revision ID: 20260915_0099
Revises: 20260915_0098
Create Date: 2026-09-15 00:00:00

Aditiva: adiciona a coluna `risk_weight` (peso-base 0-100 do tema no indicador de risco, ICC -
pedido do usuário 2026-09-15, calibração visual inicial) e popula `support_ixc_taxonomy_mappings`
com os 67 motivos reais vistos na base em 2026-09-15, agrupados em 6 categorias / 21 temas -
proposta validada em conversa com o usuário, com a correção explícita de NÃO usar "N1/N2" (nível
de atendimento) como tema: `Atendimento Externo N2`, `Atendimento Interno N2` e `Registro de
Atendimento Operacional` entram todos em `Categoria: Operações / Tema: Suporte Interno`, com peso
baixo (a estrutura interna da empresa não deve contaminar a leitura do problema do cliente) - a
descrição do atendimento (`SupportIxcTicket.report`) é quem eleva o risco depois, via
`ixc_ticket_text_signal.py`, não o motivo genérico sozinho.

`version=1`/`effective_from=2026-09-15` pra todas as linhas (primeira vigência). Um `subject_id`
que apareça no futuro e não estiver aqui cai no fallback `NAO_MAPEADO` normalmente - esta lista
não é exaustiva pra sempre, é o retrato validado nesta data.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "20260915_0099"
down_revision = "20260915_0098"
branch_labels = None
depends_on = None


_EFFECTIVE_FROM = date(2026, 9, 15)

# (subject_id, subject_name [só documentação, não gravado], category_id, category_label,
# theme_id, theme_label, risk_weight)
_MAPPINGS = [
    ("8", "Sem Conexão Fibra Urbana", "operacoes", "Operações", "sem_conexao_fibra", "Sem conexão (fibra)", 95),
    ("9", "Sem Conexão Fibra Rural", "operacoes", "Operações", "sem_conexao_fibra", "Sem conexão (fibra)", 95),
    ("10", "Sem Conexão Rádio", "operacoes", "Operações", "sem_conexao_radio_los", "Sem conexão (rádio/LOS)", 95),
    ("119", "Sem Conexão (Link LOS)", "operacoes", "Operações", "sem_conexao_radio_los", "Sem conexão (rádio/LOS)", 95),
    ("49", "CTO Sem Sinal", "operacoes", "Operações", "sem_conexao_radio_los", "Sem conexão (rádio/LOS)", 95),
    ("1", "Suporte Externo Fibra Urbana", "operacoes", "Operações", "suporte_tecnico_fibra", "Suporte técnico (fibra)", 70),
    ("2", "Suporte Externo Fibra Rural", "operacoes", "Operações", "suporte_tecnico_fibra", "Suporte técnico (fibra)", 70),
    ("117", "Reincidência de Suporte Fibra Urbana", "operacoes", "Operações", "suporte_tecnico_fibra", "Suporte técnico (fibra)", 75),
    ("121", "Reincidência de Suporte Fibra Rural", "operacoes", "Operações", "suporte_tecnico_fibra", "Suporte técnico (fibra)", 75),
    ("3", "Suporte Externo Rádio", "operacoes", "Operações", "suporte_tecnico_radio", "Suporte técnico (rádio)", 70),
    ("123", "Reincidência de Suporte Rádio", "operacoes", "Operações", "suporte_tecnico_radio", "Suporte técnico (rádio)", 75),
    # Correção explícita do usuário (2026-09-15): NÃO usar "N1/N2" (nível de atendimento) como
    # tema - "Atendimento Externo/Interno N2" e "Registro de Atendimento Operacional" entram todos
    # em "Suporte Interno", peso baixo/neutro - a DESCRIÇÃO (`report`) eleva o risco, não o motivo.
    ("80", "Atendimento Interno N2", "operacoes", "Operações", "suporte_interno", "Suporte Interno", 15),
    ("81", "Atendimento Externo N2", "operacoes", "Operações", "suporte_interno", "Suporte Interno", 15),
    ("90", "Registro de Atendimento Operacional", "operacoes", "Operações", "suporte_interno", "Suporte Interno", 15),
    ("37", "Suporte Streaming/Apps", "operacoes", "Operações", "servicos_digitais", "Serviços digitais", 10),
    ("147", "Manutenção Preventiva", "infraestrutura", "Infraestrutura", "manutencao_campo", "Manutenção de campo", 15),
    ("157", "Manutenção Preventiva Operacional", "infraestrutura", "Infraestrutura", "manutencao_campo", "Manutenção de campo", 15),
    ("151", "Manutenção em Torre", "infraestrutura", "Infraestrutura", "manutencao_campo", "Manutenção de campo", 15),
    ("153", "Inspeção de Torre", "infraestrutura", "Infraestrutura", "manutencao_campo", "Manutenção de campo", 15),
    ("141", "Região de Manutenção", "infraestrutura", "Infraestrutura", "manutencao_campo", "Manutenção de campo", 15),
    ("149", "Rompimento", "infraestrutura", "Infraestrutura", "rompimento", "Rompimento", 100),
    ("143", "Rompimento NBS", "infraestrutura", "Infraestrutura", "rompimento", "Rompimento", 100),
    ("52", "Reparo de CTO", "infraestrutura", "Infraestrutura", "cto_rede", "CTO/Rede", 55),
    ("53", "Ampliação de CTO", "infraestrutura", "Infraestrutura", "cto_rede", "CTO/Rede", 55),
    ("51", "Construção de Rede", "infraestrutura", "Infraestrutura", "cto_rede", "CTO/Rede", 55),
    ("125", "Regulagem de Sinal", "infraestrutura", "Infraestrutura", "cto_rede", "CTO/Rede", 55),
    ("167", "Limpeza de Infraestrutura de Rede", "infraestrutura", "Infraestrutura", "cto_rede", "CTO/Rede", 55),
    ("11", "Alteração na Rede Interna Fibra Urbana", "infraestrutura", "Infraestrutura", "cto_rede", "CTO/Rede", 55),
    ("12", "Alteração na Rede Interna Fibra Rural", "infraestrutura", "Infraestrutura", "cto_rede", "CTO/Rede", 55),
    ("13", "Alteração na Rede Interna Rádio", "infraestrutura", "Infraestrutura", "cto_rede", "CTO/Rede", 55),
    ("191", "Migração de Rede Neutra", "infraestrutura", "Infraestrutura", "cto_rede", "CTO/Rede", 55),
    ("145", "Serviços NBS", "infraestrutura", "Infraestrutura", "servicos_nbs", "Serviços NBS", 15),
    ("6", "Troca de Equipamentos", "infraestrutura", "Infraestrutura", "equipamentos", "Equipamentos", 40),
    ("7", "Remoção de Equipamentos", "infraestrutura", "Infraestrutura", "equipamentos", "Equipamentos", 40),
    ("155", "Remoção de Equipamento ou Estrutura", "infraestrutura", "Infraestrutura", "equipamentos", "Equipamentos", 40),
    ("95", "Remoção de Flashman", "infraestrutura", "Infraestrutura", "equipamentos", "Equipamentos", 40),
    ("127", "Implantação/Substituição de Equipamento", "infraestrutura", "Infraestrutura", "equipamentos", "Equipamentos", 40),
    ("14", "Instalação Fibra Urbana", "instalacao", "Instalação", "instalacao_fibra", "Instalação (fibra)", 0),
    ("15", "Instalação Fibra Rural", "instalacao", "Instalação", "instalacao_fibra", "Instalação (fibra)", 0),
    ("137", "Instalação Evento/Permuta Fibra Urbana", "instalacao", "Instalação", "instalacao_fibra", "Instalação (fibra)", 0),
    ("139", "Instalação Evento/Permuta Fibra Rural", "instalacao", "Instalação", "instalacao_fibra", "Instalação (fibra)", 0),
    ("16", "Instalação Rádio", "instalacao", "Instalação", "instalacao_radio", "Instalação (rádio)", 0),
    ("135", "Instalação Evento/Permuta Rádio", "instalacao", "Instalação", "instalacao_radio", "Instalação (rádio)", 0),
    ("209", "Instalação de Câmeras de Monitoramento", "instalacao", "Instalação", "instalacao_outros", "Instalação (outros)", 0),
    ("159", "Ativação de Login Presencial", "instalacao", "Instalação", "instalacao_outros", "Instalação (outros)", 0),
    ("48", "Pendência de Instalação", "instalacao", "Instalação", "instalacao_outros", "Instalação (outros)", 0),
    ("5", "Viabilidade", "instalacao", "Instalação", "instalacao_outros", "Instalação (outros)", 0),
    ("17", "Alteração de Endereço Fibra Urbana", "administrativo", "Administrativo", "endereco_titularidade", "Endereço/titularidade", 0),
    ("18", "Alteração de Endereço Fibra Rural", "administrativo", "Administrativo", "endereco_titularidade", "Endereço/titularidade", 0),
    ("19", "Alteração de Endereço Rádio", "administrativo", "Administrativo", "endereco_titularidade", "Endereço/titularidade", 0),
    ("54", "Alteração de Endereço entre Filiais", "administrativo", "Administrativo", "endereco_titularidade", "Endereço/titularidade", 0),
    ("43", "Autorização para Migração de Titularidade", "administrativo", "Administrativo", "endereco_titularidade", "Endereço/titularidade", 0),
    ("41", "Recebimento de Migração de Titularidade", "administrativo", "Administrativo", "endereco_titularidade", "Endereço/titularidade", 0),
    ("46", "Migração de Tecnologia de Rádio para Fibra", "administrativo", "Administrativo", "migracao_tecnologia", "Migração de tecnologia", 15),
    ("65", "Pendência de Migração de Tecnologia", "administrativo", "Administrativo", "migracao_tecnologia", "Migração de tecnologia", 15),
    ("91", "Documentação de Redes/POP/Site", "administrativo", "Administrativo", "registro_administrativo", "Registro administrativo", 10),
    ("28", "Registro de Atendimento", "administrativo", "Administrativo", "registro_administrativo", "Registro administrativo", 10),
    ("24", "Alteração de Plano", "comercial", "Comercial", "contrato_plano", "Contrato/plano", 0),
    ("23", "Renovação de Contrato", "comercial", "Comercial", "contrato_plano", "Contrato/plano", 0),
    ("115", "Reativação de Contrato", "comercial", "Comercial", "contrato_plano", "Contrato/plano", 0),
    ("185", "Reativação de Suspensão Temporária - Externo", "comercial", "Comercial", "contrato_plano", "Contrato/plano", 0),
    ("36", "Suspensão Temporária", "comercial", "Comercial", "contrato_plano", "Contrato/plano", 0),
    ("20", "Solicitação de Cancelamento", "comercial", "Comercial", "contrato_plano", "Contrato/plano", 0),
    ("29", "Registro de Informação Financeira", "comercial", "Comercial", "financeiro", "Financeiro", 0),
    ("22", "Gerar Financeiro", "comercial", "Comercial", "financeiro", "Financeiro", 0),
    ("60", "OffTime - Financeiro", "comercial", "Comercial", "financeiro", "Financeiro", 0),
    ("21", "Renegociação de Boletos", "comercial", "Comercial", "financeiro", "Financeiro", 0),
    ("58", "Recuperação de Equipamento por Cobrança", "comercial", "Comercial", "financeiro", "Financeiro", 0),
    ("57", "OffTime - Comercial", "comercial", "Comercial", "comercial_indicadores", "Comercial/indicadores", 0),
    ("31", "Indicador - Promoção", "comercial", "Comercial", "comercial_indicadores", "Comercial/indicadores", 0),
    ("187", "Pesquisa NPS Comercial", "qualidade", "Qualidade", "pesquisa_satisfacao", "Pesquisa de satisfação", 0),
]


_TAXONOMY_TABLE = sa.table(
    "support_ixc_taxonomy_mappings",
    sa.column("subject_id", sa.String),
    sa.column("theme_id", sa.String),
    sa.column("theme_label", sa.String),
    sa.column("category_id", sa.String),
    sa.column("category_label", sa.String),
    sa.column("version", sa.Integer),
    sa.column("effective_from", sa.Date),
    sa.column("risk_weight", sa.Integer),
    sa.column("created_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    op.add_column(
        "support_ixc_taxonomy_mappings",
        sa.Column("risk_weight", sa.Integer(), nullable=False, server_default="0"),
    )

    now = datetime.now(timezone.utc)
    op.bulk_insert(
        _TAXONOMY_TABLE,
        [
            {
                "subject_id": subject_id,
                "theme_id": theme_id,
                "theme_label": theme_label,
                "category_id": category_id,
                "category_label": category_label,
                "version": 1,
                "effective_from": _EFFECTIVE_FROM,
                "risk_weight": risk_weight,
                "created_at": now,
            }
            for subject_id, _subject_name, category_id, category_label, theme_id, theme_label, risk_weight in _MAPPINGS
        ],
    )


def downgrade() -> None:
    subject_ids = [row[0] for row in _MAPPINGS]
    op.execute(
        _TAXONOMY_TABLE.delete().where(
            _TAXONOMY_TABLE.c.subject_id.in_(subject_ids), _TAXONOMY_TABLE.c.effective_from == _EFFECTIVE_FROM
        )
    )
    op.drop_column("support_ixc_taxonomy_mappings", "risk_weight")
