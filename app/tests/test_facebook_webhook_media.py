from __future__ import annotations

from app.tests.test_api import TINY_PNG, build_client


def _create_brand_and_page(client):
    platform_headers = {"X-Platform-Token": "test-platform-token"}
    brand = client.post(
        "/api/v1/brands",
        headers=platform_headers,
        json={"name": "Facebook Media Brand", "slug": "facebook-media-brand"},
    )
    assert brand.status_code == 200
    brand_json = brand.json()

    page = client.post(
        "/api/v1/facebook-pages",
        headers=platform_headers,
        json={
            "brand_id": brand_json["id"],
            "page_name": "Facebook Media Brand Page",
            "page_id": "1234567890",
            "page_username": "facebook-media-brand",
            "app_id": "meta-app-1",
            "app_secret": "super-secret",
            "page_access_token": "page-token-1",
            "verify_token": "verify-token-1",
            "active": True,
            "automation_enabled": True,
            "reply_to_messages": True,
            "reply_to_comments": True,
            "private_reply_to_comments": False,
            "auto_hide_spam_comments": False,
            "handoff_enabled": True,
            "business_hours_only": False,
            "reply_delay_seconds": 15,
            "allowed_reply_window_hours": 24,
            "default_language": "bn-BD",
            "timezone": "Asia/Dhaka",
        },
    )
    assert page.status_code == 200
    return platform_headers, brand_json


def test_facebook_webhook_downloads_image_attachments_into_conversations(tmp_path, monkeypatch):
    with build_client(tmp_path) as client:
        from app.services import facebook_webhooks

        send_calls = []
        download_calls = []

        class FakeSendResponse:
            status_code = 200
            text = '{"recipient_id":"psid-2","message_id":"fb-mid-image"}'

            def json(self):
                return {"recipient_id": "psid-2", "message_id": "fb-mid-image"}

        class FakeDownloadResponse:
            status_code = 200
            headers = {"content-type": "image/png"}
            content = TINY_PNG

        def fake_post(url, params=None, json=None, timeout=None):
            send_calls.append({"url": url, "params": params, "json": json, "timeout": timeout})
            return FakeSendResponse()

        def fake_get(url, params=None, timeout=None, follow_redirects=None):
            download_calls.append({"url": url, "params": params, "timeout": timeout})
            return FakeDownloadResponse()

        monkeypatch.setattr(facebook_webhooks.httpx, "post", fake_post)
        monkeypatch.setattr(facebook_webhooks.httpx, "get", fake_get)
        platform_headers, brand_json = _create_brand_and_page(client)

        webhook = client.post(
            "/api/v1/facebook/webhook",
            json={
                "object": "page",
                "entry": [
                    {
                        "id": "1234567890",
                        "time": 1713900000,
                        "messaging": [
                            {
                                "sender": {"id": "psid-2"},
                                "recipient": {"id": "1234567890"},
                                "timestamp": 1713900001,
                                "message": {
                                    "mid": "mid-image-1",
                                    "attachments": [
                                        {
                                            "type": "image",
                                            "payload": {"url": "https://cdn.example.com/customer-image.png"},
                                        }
                                    ],
                                },
                            }
                        ],
                    }
                ],
            },
        )
        assert webhook.status_code == 200
        assert webhook.json()["processed"] == 1
        assert len(download_calls) == 1
        assert len(send_calls) == 1

        conversations = client.get(
            "/api/v1/conversations",
            headers=platform_headers,
            params={"brand_id": brand_json["id"]},
        )
        assert conversations.status_code == 200
        conversation = conversations.json()[0]
        inbound = conversation["messages"][0]
        assert len(inbound["attachments"]) == 1
        assert inbound["attachments"][0]["attachment_type"] == "image"
        assert inbound["attachments"][0]["mime_type"] == "image/png"
        assert conversation["messages"][1]["external_message_id"] == "fb-mid-image"


def test_facebook_webhook_downloads_audio_attachments_and_transcribes_them(tmp_path, monkeypatch):
    with build_client(tmp_path) as client:
        from app.services import facebook_webhooks

        send_calls = []
        download_calls = []

        class FakeSendResponse:
            status_code = 200
            text = '{"recipient_id":"psid-3","message_id":"fb-mid-audio"}'

            def json(self):
                return {"recipient_id": "psid-3", "message_id": "fb-mid-audio"}

        class FakeDownloadResponse:
            status_code = 200
            headers = {"content-type": "audio/mpeg"}
            content = b"FAKEAUDIO123"

        def fake_post(url, params=None, json=None, timeout=None):
            send_calls.append({"url": url, "params": params, "json": json, "timeout": timeout})
            return FakeSendResponse()

        def fake_get(url, params=None, timeout=None, follow_redirects=None):
            download_calls.append({"url": url, "params": params, "timeout": timeout})
            return FakeDownloadResponse()

        monkeypatch.setattr(facebook_webhooks.httpx, "post", fake_post)
        monkeypatch.setattr(facebook_webhooks.httpx, "get", fake_get)
        platform_headers, brand_json = _create_brand_and_page(client)

        webhook = client.post(
            "/api/v1/facebook/webhook",
            json={
                "object": "page",
                "entry": [
                    {
                        "id": "1234567890",
                        "time": 1713900000,
                        "messaging": [
                            {
                                "sender": {"id": "psid-3"},
                                "recipient": {"id": "1234567890"},
                                "timestamp": 1713900001,
                                "message": {
                                    "mid": "mid-audio-1",
                                    "attachments": [
                                        {
                                            "type": "audio",
                                            "payload": {"url": "https://cdn.example.com/customer-audio.mp3"},
                                        }
                                    ],
                                },
                            }
                        ],
                    }
                ],
            },
        )
        assert webhook.status_code == 200
        assert webhook.json()["processed"] == 1
        assert len(download_calls) == 1
        assert len(send_calls) == 1

        conversations = client.get(
            "/api/v1/conversations",
            headers=platform_headers,
            params={"brand_id": brand_json["id"]},
        )
        assert conversations.status_code == 200
        conversation = conversations.json()[0]
        inbound = conversation["messages"][0]
        outbound = conversation["messages"][1]
        assert len(inbound["attachments"]) == 1
        assert inbound["attachments"][0]["attachment_type"] == "audio"
        assert inbound["attachments"][0]["transcript"] == "Mock audio transcript"
        assert "audio-transcribed" in (outbound["flags_json"] or [])
        assert outbound["external_message_id"] == "fb-mid-audio"
