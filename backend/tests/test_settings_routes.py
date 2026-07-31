"""Regression: /settings e /gamification/config sao rotas da Gamificacao, mas a tabela
`app_settings` e compartilhada com o Agendamento (chaves scheduling_*). Sem filtrar por chave,
essas rotas liam e escreviam parametros de outro modulo (achado do mapeamento da Fase 5 do plano
de administracao)."""
from app.models import AppSetting


def test_list_settings_excludes_scheduling_keys(client, db_session):
    db_session.add(AppSetting(key="scheduling_business_start", value="07:30"))
    db_session.add(AppSetting(key="point_value", value="2.50"))
    db_session.commit()

    response = client.get("/api/settings")

    assert response.status_code == 200
    keys = {item["key"] for item in response.json()}
    assert "scheduling_business_start" not in keys
    assert "point_value" in keys


def test_update_setting_rejects_a_scheduling_key(client, db_session):
    db_session.add(AppSetting(key="scheduling_business_start", value="07:30"))
    db_session.commit()

    response = client.put("/api/settings/scheduling_business_start", json={"value": "23:00"})

    assert response.status_code == 404
    unchanged = db_session.query(AppSetting).filter_by(key="scheduling_business_start").one()
    assert unchanged.value == "07:30"


def test_update_setting_accepts_a_gamification_key(client, db_session):
    response = client.put("/api/settings/point_value", json={"value": "3.00"})

    assert response.status_code == 200
    assert response.json()["value"] == "3.00"
