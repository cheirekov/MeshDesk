from fastapi.testclient import TestClient

from meshdesk.app import create_app


class StaticManager:
    def disconnect(self) -> None:
        pass


def test_role_advisor_is_present_and_read_only() -> None:
    app = create_app(manager=StaticManager())

    with TestClient(app) as client:
        page = client.get("/")
        script = client.get("/app.js")

    assert page.status_code == 200
    assert script.status_code == 200
    assert 'id="guidancePanel"' in page.text
    assert 'id="roleAdvisorCards"' in page.text
    assert "ИНФОРМАТИВНО · НЕ ПРИЛАГА ПРОМЕНИ" in page.text
    assert "CLIENT_BASE" in script.text
    assert "ROUTER_LATE" in script.text
    assert "renderRoleAdvisor()" in script.text


def test_configuration_has_contextual_guidance() -> None:
    app = create_app(manager=StaticManager())

    with TestClient(app) as client:
        script = client.get("/app.js")

    assert script.status_code == 200
    assert "configSectionGuidance" in script.text
    assert 'id="configGuidance"' in script.text
    assert "renderConfigGuidance(section)" in script.text
