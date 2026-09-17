"""Estende a taxonomia do Atendimento IXC para o restante do catálogo de motivos

Revision ID: 20260917_0101
Revises: 20260916_0100
Create Date: 2026-09-17 00:00:00

Item 8 do plano de evolução analítica do Atendimento IXC: revisão dos mapeamentos ainda
`NAO_MAPEADO`. Diagnóstico feito em 2026-09-17 direto no banco: dos 130.569 atendimentos já
importados (71 `subject_id` distintos), 100% já tinham tema mapeado pela seed de
`20260915_0099` — nenhum atendimento REAL cai em `NAO_MAPEADO` hoje. O risco é futuro: o
catálogo `su_oss_assunto` do IXC (consultado ao vivo via `fetch_assuntos`) tem 145 motivos, e
74 deles nunca apareceram num atendimento importado e continuavam sem taxonomia - se o IXC
começar a usar um desses motivos, o atendimento cairia em `NAO_MAPEADO`/`risk_weight=0` sem
nenhum aviso.

Classificação dos 74 motivos restantes revisada e aprovada pelo usuário em 2026-09-17. Onde
fez sentido, reaproveita um tema já existente da seed anterior (`20260915_0099`); só cria tema
novo pra cluster que não tinha equivalente (`teste_interno`, `pos_venda_homologacao`,
`cobranca`, `sistemas_integracao`, `telefonia`). `effective_from` = hoje - não sobrescreve
nenhuma das 71 linhas vigentes, só adiciona motivos novos.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "20260917_0101"
down_revision = "20260916_0100"
branch_labels = None
depends_on = None


_EFFECTIVE_FROM = date(2026, 9, 17)

# (subject_id, subject_name [só documentação], category_id, category_label, theme_id,
# theme_label, risk_weight)
_MAPPINGS = [
    # Testes/internos - nunca são atendimento real, peso 0.
    ("40", "Teste", "operacoes", "Operações", "teste_interno", "Teste/interno", 0),
    ("87", "teste", "operacoes", "Operações", "teste_interno", "Teste/interno", 0),
    ("88", "Teste (Estrutura)", "operacoes", "Operações", "teste_interno", "Teste/interno", 0),
    ("89", "Teste APR", "operacoes", "Operações", "teste_interno", "Teste/interno", 0),
    # Suporte interno - mesmo tema de 80/81/90 (seed anterior).
    ("4", "Suporte Interno", "operacoes", "Operações", "suporte_interno", "Suporte Interno", 15),
    # Pesquisa/NPS - mesmo tema de 187 (seed anterior).
    ("25", "Pesquisa de Satisfação", "qualidade", "Qualidade", "pesquisa_satisfacao", "Pesquisa de satisfação", 0),
    # Pós-venda / homologação - tema novo.
    ("26", "Pós Venda", "comercial", "Comercial", "pos_venda_homologacao", "Pós-venda/homologação", 10),
    ("27", "Homologação de Ordem de Serviço", "comercial", "Comercial", "pos_venda_homologacao", "Pós-venda/homologação", 10),
    ("109", "Homologação Comercial", "comercial", "Comercial", "pos_venda_homologacao", "Pós-venda/homologação", 10),
    # Financeiro - mesmo tema de 21/22/29/58/60 (seed anterior).
    ("30", "Faturamento de Equipamento", "comercial", "Comercial", "financeiro", "Financeiro", 0),
    ("33", "Verificação de Financeiro", "comercial", "Comercial", "financeiro", "Financeiro", 0),
    ("55", "Conferência de Contrato", "comercial", "Comercial", "financeiro", "Financeiro", 0),
    ("56", "Conferência de Recebimento", "comercial", "Comercial", "financeiro", "Financeiro", 0),
    ("64", "Cancelamento de Boletos", "comercial", "Comercial", "financeiro", "Financeiro", 0),
    # Cobrança - tema novo.
    ("35", "Cobrança", "comercial", "Comercial", "cobranca", "Cobrança", 20),
    ("38", "Cobrança: Procedimentos de Rescisão Contratual", "comercial", "Comercial", "cobranca", "Cobrança", 20),
    ("39", "Cobrança: Negativação e Cancelamento", "comercial", "Comercial", "cobranca", "Cobrança", 20),
    # SPC - mesmo tema cobrança/negativação.
    ("181", "Inclusão SPC Brasil", "comercial", "Comercial", "cobranca", "Cobrança", 20),
    ("183", "Exclusão SPC Brasil", "comercial", "Comercial", "cobranca", "Cobrança", 20),
    # Indicação/Desconto - mesmo tema de 31/57 (seed anterior).
    ("32", "Gerar Desconto - Indicação", "comercial", "Comercial", "comercial_indicadores", "Comercial/indicadores", 0),
    # Auditoria/registro contrato/estoque - mesmo tema de 91/28 (seed anterior).
    ("34", "Auditoria de Contrato", "administrativo", "Administrativo", "registro_administrativo", "Registro administrativo", 0),
    ("59", "Alteração da Filial do Contrato", "administrativo", "Administrativo", "registro_administrativo", "Registro administrativo", 0),
    ("111", "Ajuste de Estoque", "administrativo", "Administrativo", "registro_administrativo", "Registro administrativo", 0),
    # Titularidade/endereço - mesmo tema de 17/18/19/41/43/54 (seed anterior).
    ("42", "Validação da Migração de Titularidade", "administrativo", "Administrativo", "endereco_titularidade", "Endereço/titularidade", 0),
    ("66", "Retorno de Alteração de Endereço Rádio", "administrativo", "Administrativo", "endereco_titularidade", "Endereço/titularidade", 0),
    ("67", "Retorno de Alteração de Endereço Fibra Urbana", "administrativo", "Administrativo", "endereco_titularidade", "Endereço/titularidade", 0),
    ("68", "Retorno de Alteração de Endereço Fibra Rural", "administrativo", "Administrativo", "endereco_titularidade", "Endereço/titularidade", 0),
    ("69", "Pendência de Alteração de Endereço Rádio", "administrativo", "Administrativo", "endereco_titularidade", "Endereço/titularidade", 0),
    ("70", "Pendência de Alteração de Endereço Fibra Urbana", "administrativo", "Administrativo", "endereco_titularidade", "Endereço/titularidade", 0),
    ("71", "Pendência de Alteração de Endereço Fibra Rural", "administrativo", "Administrativo", "endereco_titularidade", "Endereço/titularidade", 0),
    # Ativação de login - mesmo tema de 159 (Ativação de Login Presencial, seed anterior).
    ("44", "Ativação de Novo Login", "instalacao", "Instalação", "instalacao_outros", "Instalação (outros)", 0),
    ("74", "Ativação de Novo Login/Transferência de Comodato", "instalacao", "Instalação", "instalacao_outros", "Instalação (outros)", 0),
    # Cancelamento/retenção de contrato - mesmo tema de 20/23/24/36/115/185 (seed anterior).
    ("45", "Cancelamento de Contrato", "comercial", "Comercial", "contrato_plano", "Contrato/plano", 0),
    ("93", "Reativação de Contrato Inadimplente", "comercial", "Comercial", "contrato_plano", "Contrato/plano", 0),
    ("97", "Reversão de cancelamento Parcial", "comercial", "Comercial", "contrato_plano", "Contrato/plano", 0),
    ("99", "Cancelamento", "comercial", "Comercial", "contrato_plano", "Contrato/plano", 0),
    ("101", "Reversão de cancelamento Total", "comercial", "Comercial", "contrato_plano", "Contrato/plano", 0),
    ("103", "Acompanhamento - Reversão de Cancelamento Total", "comercial", "Comercial", "contrato_plano", "Contrato/plano", 0),
    ("107", "Acompanhamento - Reversão de Cancelamento Parcial", "comercial", "Comercial", "contrato_plano", "Contrato/plano", 0),
    ("179", "Escalonamento de Retenção", "comercial", "Comercial", "contrato_plano", "Contrato/plano", 0),
    # Suporte prioritário - mesmo tema/peso alto de suporte técnico fibra (seed anterior).
    ("105", "Suporte Prioritário", "operacoes", "Operações", "suporte_tecnico_fibra", "Suporte técnico (fibra)", 70),
    # Migração de tecnologia - mesmo tema de 46/65 (seed anterior).
    ("47", "Alteração da Tecnologia para Fibra", "administrativo", "Administrativo", "migracao_tecnologia", "Migração de tecnologia", 15),
    ("72", "Pendência de Alteração de Tecnologia para Fibra", "administrativo", "Administrativo", "migracao_tecnologia", "Migração de tecnologia", 15),
    ("73", "Retorno de Alteração de Tecnologia para Fibra", "administrativo", "Administrativo", "migracao_tecnologia", "Migração de tecnologia", 15),
    ("84", "Migração de Tecnologia de Fibra para Rádio", "administrativo", "Administrativo", "migracao_tecnologia", "Migração de tecnologia", 15),
    ("85", "Alteração da Tecnologia para Rádio", "administrativo", "Administrativo", "migracao_tecnologia", "Migração de tecnologia", 15),
    ("86", "Pendência de Alteração de Tecnologia para Rádio", "administrativo", "Administrativo", "migracao_tecnologia", "Migração de tecnologia", 15),
    # Viabilidade/validação de cliente - mesmo tema de 5 (Viabilidade, seed anterior).
    ("50", "Validação de Clientes/Circuito", "instalacao", "Instalação", "instalacao_outros", "Instalação (outros)", 0),
    ("189", "Retorno de Viabilidade", "instalacao", "Instalação", "instalacao_outros", "Instalação (outros)", 0),
    # Retorno/pendência de instalação, por tipo de tecnologia (mesmos temas da seed anterior).
    ("61", "Retorno de Instalação Rádio", "instalacao", "Instalação", "instalacao_radio", "Instalação (rádio)", 0),
    ("62", "Retorno de Instalação Fibra Urbana", "instalacao", "Instalação", "instalacao_fibra", "Instalação (fibra)", 0),
    ("63", "Retorno de Instalação Fibra Rural", "instalacao", "Instalação", "instalacao_fibra", "Instalação (fibra)", 0),
    ("129", "Retorno de Instalação Evento/Permuta Rádio", "instalacao", "Instalação", "instalacao_radio", "Instalação (rádio)", 0),
    ("131", "Retorno de Instalação Evento/Permuta Fibra Urbana", "instalacao", "Instalação", "instalacao_fibra", "Instalação (fibra)", 0),
    ("133", "Retorno de Instalação Evento/Permuta Fibra Rural", "instalacao", "Instalação", "instalacao_fibra", "Instalação (fibra)", 0),
    ("195", "Instalação Fibra Rural com Ativação de Câmeras", "instalacao", "Instalação", "instalacao_outros", "Instalação (outros)", 0),
    ("197", "Retorno de Instalação Fibra Urbana com Ativação de Câmeras", "instalacao", "Instalação", "instalacao_outros", "Instalação (outros)", 0),
    ("199", "Pendência de Instalação com Ativação de Câmeras", "instalacao", "Instalação", "instalacao_outros", "Instalação (outros)", 0),
    ("201", "Instalação Fibra Urbana com Ativação de Câmeras", "instalacao", "Instalação", "instalacao_outros", "Instalação (outros)", 0),
    ("203", "Instalação Rádio com Ativação de Câmeras", "instalacao", "Instalação", "instalacao_outros", "Instalação (outros)", 0),
    ("205", "Retorno de Instalação Fibra Rural com Ativação de Câmeras", "instalacao", "Instalação", "instalacao_outros", "Instalação (outros)", 0),
    ("207", "Retorno de Instalação Rádio com Ativação de Câmeras", "instalacao", "Instalação", "instalacao_outros", "Instalação (outros)", 0),
    # Tutorial/serviços digitais - mesmo tema de 37 (Suporte Streaming/Apps, seed anterior).
    ("75", "Tutorial", "operacoes", "Operações", "servicos_digitais", "Serviços digitais", 10),
    # Integração de sistema - tema novo.
    ("76", "IClass Integração", "infraestrutura", "Infraestrutura", "sistemas_integracao", "Sistemas/integração", 15),
    # Equipamento - mesmo tema de 6/7/95/127/155 (seed anterior).
    ("77", "Conferência do Equipamento", "infraestrutura", "Infraestrutura", "equipamentos", "Equipamentos", 40),
    ("78", "Revisão de Equipamentos: Operacional", "infraestrutura", "Infraestrutura", "equipamentos", "Equipamentos", 40),
    # Transmissor/CTO - mesmo tema de 51/52/53/11/12/13/125/167/191 (seed anterior).
    ("79", "Migração de Transmissor", "infraestrutura", "Infraestrutura", "cto_rede", "CTO/Rede", 55),
    ("193", "Remoção de Conector da CTO", "infraestrutura", "Infraestrutura", "cto_rede", "CTO/Rede", 55),
    # Manutenção - mesmo tema de 147/151/153/157/141 (seed anterior).
    ("83", "Manutenção/Serviços", "infraestrutura", "Infraestrutura", "manutencao_campo", "Manutenção de campo", 15),
    # Telefonia - tema novo.
    ("169", "(Checklist) Instalação com Telefonia", "comercial", "Comercial", "telefonia", "Telefonia", 0),
    ("171", "Ativação Telefonia com Portabilidade", "comercial", "Comercial", "telefonia", "Telefonia", 0),
    ("173", "Nova Ativação Telefonia", "comercial", "Comercial", "telefonia", "Telefonia", 0),
    ("175", "(Checklist) Cancelamento com Telefonia", "comercial", "Comercial", "telefonia", "Telefonia", 0),
    ("177", "(Checklist) Migração de Titularidade com Telefonia", "comercial", "Comercial", "telefonia", "Telefonia", 0),
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
