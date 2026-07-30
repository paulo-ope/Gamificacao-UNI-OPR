"""Regression tests for backend/app/services/ixc_importer.py."""
import pytest

from app.modules.operations import scope
from app.services import ixc_importer


def test_ixc_importer_has_no_duplicate_sector_constant():
    """Regression: 'setor tecnico de campo' costumava ser definido duas vezes - uma vez como
    IXC_TECHNICAL_SETOR_IDS aqui em ixc_importer.py, outra como PRIMARY_IXC_SECTOR_IDS em
    modules/operations/scope.py. As duas listas so batiam (["7","8","9"]) por coincidencia -
    nada garantia que editar uma atualizasse a outra. A lista duplicada nao deveria mais
    existir; ixc_importer.py deve reusar a mesma constante de scope.py por importacao."""
    assert not hasattr(ixc_importer, "IXC_TECHNICAL_SETOR_IDS")
    assert ixc_importer.PRIMARY_IXC_SECTOR_IDS is scope.PRIMARY_IXC_SECTOR_IDS, (
        "precisa ser o MESMO objeto (importado), nao uma lista redefinida aqui com os mesmos valores"
    )


def test_ixc_importer_sector_filter_reads_from_operations_scope(monkeypatch):
    """Prova comportamental de que o filtro de setor usado na chamada real ao IXC vem por
    CONSTRUCAO da constante de scope.py, nao de uma copia local - mudar o valor que
    ixc_importer.py enxerga muda o que de fato e pedido ao fetch_service_orders."""
    monkeypatch.setattr(ixc_importer, "PRIMARY_IXC_SECTOR_IDS", ("99",))

    captured: dict = {}

    class _StopAfterFetch(Exception):
        pass

    def fake_fetch_service_orders(client, **kwargs):
        captured.update(kwargs)
        raise _StopAfterFetch()

    monkeypatch.setattr(ixc_importer, "fetch_service_orders", fake_fetch_service_orders)

    with pytest.raises(_StopAfterFetch):
        ixc_importer._import_ixc_service_orders_body(db=None, client=object())

    assert captured["setor_ids"] == ["99"]
