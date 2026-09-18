from __future__ import annotations

from app.modules.support.ixc_ticket_ingestion import import_tickets_for_period
from app.modules.support.models import SupportIxcTicket, SupportIxcTicketRaw
from app.services.ixc_client import IxcClient, IxcPage


class FakeIxcClient(IxcClient):
    """Cliente IXC em memória cobrindo `su_ticket`, `cliente` e `su_oss_assunto` -
    mesmo padrão dos outros fakes do projeto (list_all real, só troca a fonte de dado)."""

    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables
        self.calls: list[dict] = []

    def _field(self, tb: str) -> str:
        return tb.split(".")[-1]

    def _apply_filters(self, records, grid_param):
        result = records
        for item in grid_param:
            field = self._field(item["TB"])
            op = item["OP"]
            value = item["P"]
            if op == ">=":
                result = [r for r in result if str(r.get(field, "")) >= str(value)]
            elif op == "<=":
                result = [r for r in result if str(r.get(field, "")) <= str(value)]
            elif op == "=":
                result = [r for r in result if str(r.get(field)) == str(value)]
            elif op == "IN":
                allowed = set(value.split(","))
                result = [r for r in result if str(r.get(field)) in allowed]
        return result

    def list(self, table, *, grid_param=None, page=1, rp=100, sortname=None, sortorder="asc"):
        self.calls.append({"table": table, "grid_param": grid_param})
        records = self.tables.get(table, [])
        filtered = self._apply_filters(records, grid_param or [])
        if sortname:
            def _sort_key(r):
                try:
                    return int(r.get("id") or 0)
                except (TypeError, ValueError):
                    return 0
            filtered = sorted(filtered, key=_sort_key, reverse=sortorder == "desc")
        total = len(filtered)
        start = (page - 1) * rp
        page_records = filtered[start : start + rp]
        return IxcPage(records=page_records, total=total, page=page)


def _ticket(ticket_id, **overrides):
    base = {
        "id": str(ticket_id),
        "protocolo": f"T{ticket_id}",
        "id_cliente": "500",
        "id_contrato": "900",
        "id_filial": "11",
        "id_assunto": "90",
        "status": "OSAB",
        "su_status": "EP",
        "id_canal_atendimento": "3",
        "id_wfl_processo": "7",
        "prioridade": "M",
        "titulo": "Registro de Atendimento Operacional",
        "menssagem": "Descrição da solicitação: sem conexão desde ontem à noite.",
        "data_criacao": "2026-09-01 08:00:00",
        "data_ultima_alteracao": "2026-09-01 08:05:00",
    }
    base.update(overrides)
    return base


def _cliente(cliente_id, **overrides):
    # `cidade` é o id_cidade (FK pra tabela `cidade`), não o nome - achado real em produção
    # (2026-09-11): sem resolver isso, a coluna city ficava cheia de código numérico.
    base = {
        "id": str(cliente_id),
        "cidade": "60",
        "bairro": "Centro",
        "tipo_localidade": "U",
        "razao": "Cliente Teste da Silva",
    }
    base.update(overrides)
    return base


def _cidade(cidade_id, nome):
    return {"id": str(cidade_id), "nome": nome}


def _assunto(assunto_id, nome):
    return {"id": str(assunto_id), "assunto": nome}


def _setor(setor_id, nome):
    return {"id": str(setor_id), "setor": nome}


def test_import_tickets_creates_records_with_enriched_city_and_subject(db_session):
    client = FakeIxcClient({
        "su_ticket": [_ticket(1)],
        "cliente": [_cliente(500)],
        "cidade": [_cidade(60, "Nova Brasilândia D'Oeste")],
        "su_oss_assunto": [_assunto(90, "Sem conexão")],
    })

    result = import_tickets_for_period(
        db_session, client, created_after="2026-09-01 00:00:00", created_before="2026-09-01 23:59:59"
    )

    assert result == {"fetched": 1, "created": 1, "updated": 0, "unchanged": 0, "rejected": 0}
    ticket = db_session.query(SupportIxcTicket).one()
    assert ticket.regional == "UNI - NOVA BRASILANDIA DOESTE"
    assert ticket.city == "Nova Brasilândia D'Oeste"
    assert ticket.neighborhood == "Centro"
    assert ticket.locality_type == "U"
    assert ticket.subject_name == "Sem conexão"
    assert ticket.protocol == "T1"
    assert ticket.customer_name == "Cliente Teste da Silva"
    assert ticket.title == "Registro de Atendimento Operacional"
    assert ticket.report == "Descrição da solicitação: sem conexão desde ontem à noite."
    raw = db_session.query(SupportIxcTicketRaw).one()
    assert raw.source_id == "1"


def test_import_tickets_is_idempotent(db_session):
    client = FakeIxcClient({
        "su_ticket": [_ticket(1)],
        "cliente": [_cliente(500)],
        "cidade": [_cidade(60, "Nova Brasilândia D'Oeste")],
        "su_oss_assunto": [_assunto(90, "Sem conexão")],
    })

    import_tickets_for_period(db_session, client, created_after="2026-09-01", created_before="2026-09-02")
    result = import_tickets_for_period(db_session, client, created_after="2026-09-01", created_before="2026-09-02")

    assert result["created"] == 0
    assert result["unchanged"] == 1
    assert db_session.query(SupportIxcTicket).count() == 1


def test_import_tickets_updates_when_status_changes(db_session):
    client = FakeIxcClient({
        "su_ticket": [_ticket(1, status="OSAB")],
        "cliente": [_cliente(500)],
        "cidade": [_cidade(60, "Nova Brasilândia D'Oeste")],
        "su_oss_assunto": [_assunto(90, "Sem conexão")],
    })
    import_tickets_for_period(db_session, client, created_after="2026-09-01", created_before="2026-09-02")

    client.tables["su_ticket"][0]["status"] = "F"
    result = import_tickets_for_period(db_session, client, created_after="2026-09-01", created_before="2026-09-02")

    assert result["updated"] == 1
    ticket = db_session.query(SupportIxcTicket).one()
    assert ticket.status == "F"


def test_import_tickets_filters_by_filial(db_session):
    client = FakeIxcClient({
        "su_ticket": [_ticket(1, id_filial="11"), _ticket(2, id_filial="18")],
        "cliente": [_cliente(500)],
        "cidade": [_cidade(60, "Nova Brasilândia D'Oeste")],
        "su_oss_assunto": [_assunto(90, "Sem conexão")],
    })

    result = import_tickets_for_period(
        db_session, client, created_after="2026-09-01", created_before="2026-09-02", filial_ids=["11"]
    )

    assert result["fetched"] == 1
    ticket = db_session.query(SupportIxcTicket).one()
    assert ticket.source_id == "1"


def test_import_tickets_rejects_record_without_id(db_session):
    client = FakeIxcClient({
        "su_ticket": [_ticket(1), {**_ticket(2), "id": ""}],
        "cliente": [_cliente(500)],
        "cidade": [_cidade(60, "Nova Brasilândia D'Oeste")],
        "su_oss_assunto": [_assunto(90, "Sem conexão")],
    })

    result = import_tickets_for_period(db_session, client, created_after="2026-09-01", created_before="2026-09-02")

    assert result["created"] == 1
    assert result["rejected"] == 1


def _contrato(contract_id, cliente_id, id_filial="11", status="A", cidade="60", bairro="Centro", ultima_atualizacao="2026-09-01 00:00:00"):
    return {
        "id": str(contract_id),
        "id_cliente": str(cliente_id),
        "id_filial": id_filial,
        "cidade": cidade,
        "bairro": bairro,
        "status": status,
        "ultima_atualizacao": ultima_atualizacao,
    }


def test_import_tickets_falls_back_to_contract_regional_when_ticket_filial_is_invalid(db_session):
    """Pedido explícito do usuário (2026-09-11): atendimento sem filial válida no próprio
    su_ticket deve herdar a regional do CONTRATO do cliente, não ficar "NAO IDENTIFICADO" à toa."""
    client = FakeIxcClient({
        "su_ticket": [_ticket(1, id_filial="0")],  # "0" é código inválido (INVALID_REGIONAL_CODES)
        "cliente": [_cliente(500)],
        "cliente_contrato": [_contrato(900, 500, id_filial="18")],  # 18 = SAO FRANCISCO DO GUAPORE
        "cidade": [_cidade(60, "Nova Brasilândia D'Oeste")],
        "su_oss_assunto": [_assunto(90, "Sem conexão")],
    })

    import_tickets_for_period(db_session, client, created_after="2026-09-01", created_before="2026-09-02")

    ticket = db_session.query(SupportIxcTicket).one()
    assert ticket.regional == "UNI - SAO FRANCISCO DO GUAPORE"


def test_import_tickets_keeps_not_identified_when_contract_filial_is_also_invalid(db_session):
    client = FakeIxcClient({
        "su_ticket": [_ticket(1, id_filial="0")],
        "cliente": [_cliente(500)],
        "cliente_contrato": [_contrato(900, 500, id_filial="1")],  # também inválido
        "cidade": [_cidade(60, "Nova Brasilândia D'Oeste")],
        "su_oss_assunto": [_assunto(90, "Sem conexão")],
    })

    import_tickets_for_period(db_session, client, created_after="2026-09-01", created_before="2026-09-02")

    ticket = db_session.query(SupportIxcTicket).one()
    assert ticket.regional == "NAO IDENTIFICADO"


def test_import_tickets_falls_back_to_contract_city_and_neighborhood_when_client_lacks_them(db_session):
    client = FakeIxcClient({
        "su_ticket": [_ticket(1)],
        "cliente": [_cliente(500, bairro="", cidade="")],  # cliente sem bairro/cidade cadastrado
        "cliente_contrato": [_contrato(900, 500, cidade="61", bairro="Setor 2")],
        "cidade": [_cidade(60, "Nova Brasilândia D'Oeste"), _cidade(61, "Rolim de Moura")],
        "su_oss_assunto": [_assunto(90, "Sem conexão")],
    })

    import_tickets_for_period(db_session, client, created_after="2026-09-01", created_before="2026-09-02")

    ticket = db_session.query(SupportIxcTicket).one()
    assert ticket.city == "Rolim de Moura"
    assert ticket.neighborhood == "Setor 2"


def test_import_tickets_picks_active_contract_over_inactive_when_customer_has_several(db_session):
    client = FakeIxcClient({
        "su_ticket": [_ticket(1, id_filial="0")],
        "cliente": [_cliente(500)],
        "cliente_contrato": [
            _contrato(900, 500, id_filial="9", status="D"),  # cancelado - JARU
            _contrato(901, 500, id_filial="18", status="A"),  # ativo - SAO FRANCISCO
        ],
        "cidade": [_cidade(60, "Nova Brasilândia D'Oeste")],
        "su_oss_assunto": [_assunto(90, "Sem conexão")],
    })

    import_tickets_for_period(db_session, client, created_after="2026-09-01", created_before="2026-09-02")

    ticket = db_session.query(SupportIxcTicket).one()
    assert ticket.regional == "UNI - SAO FRANCISCO DO GUAPORE"


def test_import_tickets_does_not_look_up_contracts_when_ticket_already_has_everything(db_session):
    """Nunca deve consultar `cliente_contrato` quando o ticket já tem filial válida e o cliente já
    tem cidade/bairro - evita chamada extra à API do IXC por ticket que não precisa."""
    client = FakeIxcClient({
        "su_ticket": [_ticket(1)],  # id_filial="11" (válido), cliente completo
        "cliente": [_cliente(500)],
        "cliente_contrato": [_contrato(900, 500, id_filial="18")],
        "cidade": [_cidade(60, "Nova Brasilândia D'Oeste")],
        "su_oss_assunto": [_assunto(90, "Sem conexão")],
    })

    import_tickets_for_period(db_session, client, created_after="2026-09-01", created_before="2026-09-02")

    assert not any(call["table"] == "cliente_contrato" for call in client.calls)


def test_import_tickets_normalizes_neighborhood_casing(db_session):
    """Achado real em produção (2026-09-12): bairro é texto livre sem padrão - "CENTRO"/"Centro"/
    "centro" apareciam como linhas separadas no drill-down. Normaliza pra uma forma só."""
    client = FakeIxcClient({
        "su_ticket": [_ticket(1)],
        "cliente": [_cliente(500, bairro="ZONA   RURAL")],
        "cidade": [_cidade(60, "Nova Brasilândia D'Oeste")],
        "su_oss_assunto": [_assunto(90, "Sem conexão")],
    })

    import_tickets_for_period(db_session, client, created_after="2026-09-01", created_before="2026-09-02")

    ticket = db_session.query(SupportIxcTicket).one()
    assert ticket.neighborhood == "Zona Rural"


def test_import_tickets_resolves_sector_name(db_session):
    """`su_ticket.id_ticket_setor` resolve contra `empresa_setor` - mesma tabela que a O.S. já
    usa. Achado real 2026-09-12: id=2 -> "Pós Venda", id=3 -> "Retenção" (confirmado ao vivo)."""
    client = FakeIxcClient({
        "su_ticket": [_ticket(1, id_ticket_setor="3")],
        "cliente": [_cliente(500)],
        "cidade": [_cidade(60, "Nova Brasilândia D'Oeste")],
        "su_oss_assunto": [_assunto(90, "Sem conexão")],
        "empresa_setor": [_setor(2, "Pós Venda"), _setor(3, "Retenção")],
    })

    import_tickets_for_period(db_session, client, created_after="2026-09-01", created_before="2026-09-02")

    ticket = db_session.query(SupportIxcTicket).one()
    assert ticket.sector_id == "3"
    assert ticket.sector_name == "Retenção"


def test_import_tickets_does_not_look_up_sectors_without_any_sector_id(db_session):
    client = FakeIxcClient({
        "su_ticket": [_ticket(1)],  # sem id_ticket_setor
        "cliente": [_cliente(500)],
        "cidade": [_cidade(60, "Nova Brasilândia D'Oeste")],
        "su_oss_assunto": [_assunto(90, "Sem conexão")],
    })

    import_tickets_for_period(db_session, client, created_after="2026-09-01", created_before="2026-09-02")

    assert not any(call["table"] == "empresa_setor" for call in client.calls)
