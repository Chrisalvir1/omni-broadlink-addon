"""Security and regression coverage for the Broadlink API."""

from fastapi.testclient import TestClient

from src import main


client = TestClient(main.app, client=("127.0.0.1", 12345))
INGRESS_HEADERS = {
    "X-Hass-Source": "core.ingress",
    "X-Ingress-Path": "/api/hassio_ingress/testtoken",
    "X-Remote-User-Id": "authenticated-user",
    "X-Forwarded-Host": "ha.example.test",
    "X-Forwarded-Proto": "https",
}


def test_api_rejects_direct_requests_without_ingress(monkeypatch):
    monkeypatch.setattr(main, "_trusted_networks", lambda setting="trusted_proxy_cidrs": (__import__("ipaddress").ip_network("127.0.0.1/32"), __import__("ipaddress").ip_network("::1/128")))
    response = client.get("/api/broadlink/devices")
    assert response.status_code == 403


def test_ingress_without_authenticated_user_is_rejected(monkeypatch):
    monkeypatch.setattr(main, "_trusted_networks", lambda setting="trusted_proxy_cidrs": (__import__("ipaddress").ip_network("127.0.0.1/32"), __import__("ipaddress").ip_network("::1/128")))
    headers = {key: value for key, value in INGRESS_HEADERS.items() if key != "X-Remote-User-Id"}
    response = client.get("/api/broadlink/devices", headers=headers)
    assert response.status_code == 403


def test_rejects_forged_ingress_path(monkeypatch):
    monkeypatch.setattr(main, "_trusted_networks", lambda setting="trusted_proxy_cidrs": (__import__("ipaddress").ip_network("127.0.0.1/32"), __import__("ipaddress").ip_network("::1/128")))
    headers = {**INGRESS_HEADERS, "X-Ingress-Path": "/not-home-assistant/anything"}
    response = client.get("/api/broadlink/devices", headers=headers)
    assert response.status_code == 403


def test_ingress_ui_api_remains_available_and_does_not_return_codes(monkeypatch):
    monkeypatch.setattr(main, "_trusted_networks", lambda setting="trusted_proxy_cidrs": (__import__("ipaddress").ip_network("127.0.0.1/32"), __import__("ipaddress").ip_network("::1/128")))
    monkeypatch.setattr(main.manager, "scan_devices", _async_value({"192.0.2.4": {"ip": "192.0.2.4"}}))
    monkeypatch.setattr(
        main.manager,
        "remotes",
        {"TV": {"name": "TV", "commands": {"power": "c2VjcmV0"}}},
    )

    response = client.get("/api/broadlink/devices", headers=INGRESS_HEADERS)
    assert response.status_code == 200
    assert response.json()["discovered"]["192.0.2.4"]["ip"] == "192.0.2.4"
    assert response.json()["remotes"]["TV"]["commands"] == {"power": ""}
    assert "c2VjcmV0" not in response.text


def test_export_requires_a_provisioned_consumer_token(monkeypatch):
    monkeypatch.setattr(main, "_trusted_networks", lambda setting="trusted_proxy_cidrs": (__import__("ipaddress").ip_network("127.0.0.1/32"), __import__("ipaddress").ip_network("::1/128")))
    monkeypatch.setattr(
        main.manager,
        "remotes",
        {"TV": {"name": "TV", "commands": {"power": "c2VjcmV0"}}},
    )

    monkeypatch.setattr(main, "_trusted_export_consumers", lambda: {"omni-tuya": "a" * 48})
    response = client.get(
        "/api/export/remotes",
        headers={"X-Broadlink-Consumer": "omni-tuya", "Authorization": f"Bearer {'a' * 48}"},
    )
    assert response.status_code == 200
    assert response.json()["remotes"]["TV"]["commands"]["power"] == "c2VjcmV0"


def test_export_rejects_missing_and_unknown_consumer_credentials(monkeypatch):
    monkeypatch.setattr(main, "_trusted_export_consumers", lambda: {"known-addon": "b" * 48})
    missing = client.get("/api/export/remotes")
    unknown = client.get(
        "/api/export/remotes",
        headers={"X-Broadlink-Consumer": "unknown-addon", "Authorization": f"Bearer {'b' * 48}"},
    )
    wrong = client.get(
        "/api/export/remotes",
        headers={"X-Broadlink-Consumer": "known-addon", "Authorization": f"Bearer {'c' * 48}"},
    )
    assert [missing.status_code, unknown.status_code, wrong.status_code] == [401, 401, 401]
    assert "b" * 48 not in unknown.text
    assert "c" * 48 not in wrong.text


def test_save_response_never_echoes_codes(monkeypatch):
    monkeypatch.setattr(main, "_trusted_networks", lambda setting="trusted_proxy_cidrs": (__import__("ipaddress").ip_network("127.0.0.1/32"), __import__("ipaddress").ip_network("::1/128")))
    secret = "c2VjcmV0"
    monkeypatch.setattr(
        main.manager,
        "save_remote",
        lambda **_kwargs: {"name": "TV", "commands": {"power": secret}},
    )
    response = client.post(
        "/api/broadlink/save",
        headers=INGRESS_HEADERS,
        json={"name": "TV", "ip": "192.0.2.4", "commands": {"power": secret}},
    )
    assert response.status_code == 200
    assert response.json()["remote"]["commands"] == {"power": ""}
    assert secret not in response.text


def test_external_peer_cannot_spoof_ingress_headers(monkeypatch):
    monkeypatch.setattr(main, "_trusted_networks", lambda setting="trusted_proxy_cidrs": (__import__("ipaddress").ip_network("127.0.0.1/32"), __import__("ipaddress").ip_network("::1/128")))
    external_client = TestClient(main.app, client=("192.0.2.10", 12345))
    response = external_client.get("/api/broadlink/devices", headers=INGRESS_HEADERS)
    assert response.status_code == 403


def test_default_proxy_allowlist_does_not_trust_other_addons():
    external_addon = TestClient(main.app, client=("172.30.32.3", 12345))
    response = external_addon.get("/api/broadlink/devices", headers=INGRESS_HEADERS)
    assert response.status_code == 403


def test_export_rejects_peers_outside_export_allowlist():
    external_client = TestClient(main.app, client=("192.0.2.10", 12345))
    response = external_client.get("/api/export/remotes")
    assert response.status_code == 403


def test_rejects_cross_origin_ingress_request(monkeypatch):
    monkeypatch.setattr(main, "_trusted_networks", lambda setting="trusted_proxy_cidrs": (__import__("ipaddress").ip_network("127.0.0.1/32"), __import__("ipaddress").ip_network("::1/128")))
    response = client.get(
        "/api/broadlink/devices",
        headers={**INGRESS_HEADERS, "Origin": "https://attacker.example"},
    )
    assert response.status_code == 403


def test_rejects_invalid_remote_payloads_before_manager_mutation(monkeypatch):
    monkeypatch.setattr(main, "_trusted_networks", lambda setting="trusted_proxy_cidrs": (__import__("ipaddress").ip_network("127.0.0.1/32"), __import__("ipaddress").ip_network("::1/128")))
    payloads = [
        {"name": "TV", "ip": "127.0.0.1", "commands": {"power": "not base64!"}},
        {"name": "TV", "ip": "not-an-ip", "commands": {"power": "cG93ZXI="}},
        {"name": "TV", "ip": "127.0.0.1", "mode": "shell", "commands": {"power": "cG93ZXI="}},
    ]
    for payload in payloads:
        response = client.post("/api/broadlink/save", json=payload, headers=INGRESS_HEADERS)
        assert response.status_code == 422


def test_rejects_unknown_request_fields(monkeypatch):
    monkeypatch.setattr(main, "_trusted_networks", lambda setting="trusted_proxy_cidrs": (__import__("ipaddress").ip_network("127.0.0.1/32"), __import__("ipaddress").ip_network("::1/128")))
    response = client.post(
        "/api/broadlink/learn/start",
        json={"ip": "127.0.0.1", "mode": "ir", "command": "arbitrary"},
        headers=INGRESS_HEADERS,
    )
    assert response.status_code == 422


def test_rejects_command_injection_characters_in_remote_and_button_names(monkeypatch):
    monkeypatch.setattr(main, "_trusted_networks", lambda setting="trusted_proxy_cidrs": (__import__("ipaddress").ip_network("127.0.0.1/32"), __import__("ipaddress").ip_network("::1/128")))
    response = client.post(
        "/api/broadlink/save",
        json={"name": "TV; touch /tmp/pwned", "ip": "127.0.0.1", "commands": {"power": "cG93ZXI="}},
        headers=INGRESS_HEADERS,
    )
    assert response.status_code == 422

    response = client.post(
        "/api/broadlink/save",
        json={"name": "TV", "ip": "127.0.0.1", "commands": {"power;rm": "cG93ZXI="}},
        headers=INGRESS_HEADERS,
    )
    assert response.status_code == 422


def test_api_has_no_wildcard_cors_headers(monkeypatch):
    monkeypatch.setattr(main, "_trusted_networks", lambda setting="trusted_proxy_cidrs": (__import__("ipaddress").ip_network("127.0.0.1/32"), __import__("ipaddress").ip_network("::1/128")))
    response = client.get("/api/export/remotes", headers={"Origin": "https://attacker.example"})
    assert response.status_code == 401
    assert "access-control-allow-origin" not in response.headers


def test_saved_codes_are_written_atomically_with_private_permissions(tmp_path):
    import os
    from src.broadlink_manager import BroadlinkManager

    path = tmp_path / "remotes.json"
    remote_manager = BroadlinkManager(storage_path=str(path))
    remote_manager.remotes = {"TV": {"commands": {"power": "c2VjcmV0"}}}
    remote_manager._save_remotes()

    assert path.exists()
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert remote_manager._load_remotes()["TV"]["commands"]["power"] == "c2VjcmV0"
    assert not list(tmp_path.glob(".broadlink-*.tmp"))


def test_invalid_base64_is_rejected_before_device_discovery():
    import asyncio
    from unittest.mock import patch

    from src import broadlink_manager
    from src.broadlink_manager import BroadlinkManager

    remote_manager = BroadlinkManager(storage_path="/tmp/broadlink-test-remotes.json")
    with patch.object(broadlink_manager.broadlink, "discover") as discover:
        assert asyncio.run(remote_manager.send_command("192.0.2.1", "invalid!")) is False
    discover.assert_not_called()


def _async_value(value):
    async def return_value(*_args, **_kwargs):
        return value

    return return_value
