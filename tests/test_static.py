from fastapi.testclient import TestClient

from meshdesk.app import create_app


class StaticManager:
    def disconnect(self) -> None:
        pass


def test_role_advisor_is_contextual_and_read_only() -> None:
    app = create_app(manager=StaticManager())

    with TestClient(app) as client:
        page = client.get("/")
        script = client.get("/app.js")

    assert page.status_code == 200
    assert script.status_code == 200
    assert 'id="guidancePanel"' not in page.text
    assert 'id="roleAdvisorModal"' in page.text
    assert 'id="roleAdvisorCards"' in page.text
    assert "ИНФОРМАТИВНО · НЕ ПРИЛАГА ПРОМЕНИ" in page.text
    assert "CLIENT_BASE" in script.text
    assert "ROUTER_LATE" in script.text
    assert "renderRoleAdvisor()" in script.text
    assert 'id="openRoleAdvisor"' in script.text
    assert "organizeWorkspace()" in script.text


def test_saved_connection_profiles_are_available_in_connection_panel() -> None:
    app = create_app(manager=StaticManager())

    with TestClient(app) as client:
        page = client.get("/")
        script = client.get("/app.js")

    assert 'id="connectionProfile"' in page.text
    assert 'id="saveConnectionProfile"' in page.text
    assert 'id="connectionProfileModal"' in page.text
    assert "refreshConnectionProfiles()" in script.text


def test_configuration_has_contextual_guidance() -> None:
    app = create_app(manager=StaticManager())

    with TestClient(app) as client:
        script = client.get("/app.js")

    assert script.status_code == 200
    assert "configSectionGuidance" in script.text
    assert 'id="configGuidance"' in script.text
    assert "renderConfigGuidance(section)" in script.text
