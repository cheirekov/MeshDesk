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
    assert 'id="connectionIdentityStatus"' in page.text
    assert 'id="rebindConnectionProfile"' in page.text
    assert 'id="connectionHealthPanel"' in page.text
    assert 'id="connectionHealthCompact"' in page.text
    assert 'id="discoverTcpButton"' in page.text
    assert 'id="tcpDiscoveryResults"' in page.text
    assert 'id="tcpDiscoveryDetails"' in page.text
    assert "refreshConnectionProfiles()" in script.text
    assert "verifySelectedConnectionProfile(status)" in script.text
    assert "updateConnectionHealth(status)" in script.text
    assert "Remote състояние: неизвестно" in script.text
    assert 'data-action="favorite">Добави' in script.text
    assert 'data-action="unfavorite">Премахни' in script.text
    assert "собствено радио" in script.text
    assert "Admin session</small><strong>подновена" in script.text
    assert "discoverTcpDevices" in script.text
    assert "matchingProfileForDiscoveredDevice" in script.text


def test_configuration_has_contextual_guidance() -> None:
    app = create_app(manager=StaticManager())

    with TestClient(app) as client:
        script = client.get("/app.js")

    assert script.status_code == 200
    assert "configSectionGuidance" in script.text
    assert 'id="configGuidance"' in script.text
    assert "renderConfigGuidance(section)" in script.text


def test_chat_network_and_channel_manager_have_stable_controls() -> None:
    app = create_app(manager=StaticManager())

    with TestClient(app) as client:
        page = client.get("/")
        script = client.get("/app.js")

    assert 'id="closeConversation"' in page.text
    assert 'id="channelPanel"' in page.text
    assert 'id="settingsConfigTab"' in page.text
    assert 'id="settingsChannelsTab"' in page.text
    assert page.text.index('id="configPanel"') < page.text.index('id="channelPanel"')
    assert 'id="channelSlotList"' in page.text
    assert 'id="nodePreferenceFilter"' in page.text
    assert 'id="showSelfNode"' in page.text
    assert 'id="helpTooltip"' in page.text
    assert "clearDeviceBoundUi" in script.text
    assert "refreshChannelSlots" in script.text
    assert "revealCurrentChannelPsk" in script.text
    assert "secureRandomChannelPsk" in script.text
    assert "Random AES-128" in script.text
    assert "simple0–simple254" in script.text
    assert "Custom PSK и потвърждението не съвпадат" in script.text
    assert "olderThanDay" in script.text
    assert "neighborInfoHtml" in script.text
    assert "директен отчет от първоизточника" in script.text
    assert "Raw Neighbor Info packet" in script.text


def test_contextual_help_covers_dynamic_config_and_admin_controls() -> None:
    app = create_app(manager=StaticManager())

    with TestClient(app) as client:
        page = client.get("/")
        script = client.get("/app.js")

    assert "configFieldHelp" in script.text
    assert "configHelpFor(sectionName, field)" in script.text
    assert "button_gpio" in script.text
    assert "auto_screen_carousel_secs" in script.text
    assert "initHelpTips(form)" in script.text
    assert "Помощ за рестартиране" in page.text
    assert "Помощ за изчистване на NodeDB" in page.text
    assert "Помощ за пълно фабрично нулиране" in page.text
