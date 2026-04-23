from __future__ import annotations

from app.tests.test_api import build_client


def _create_brand_and_page(client):
    platform_headers = {"X-Platform-Token": "test-platform-token"}
    brand = client.post(
        "/api/v1/brands",
        headers=platform_headers,
        json={"name": "Facebook Brand", "slug": "facebook-brand"},
    )
    assert brand.status_code == 200
    brand_json = brand.json()

    knowledge = client.post(
        "/api/v1/knowledge/documents",
        headers=platform_headers,
        json={
            "brand_id": brand_json["id"],
            "title": "Facebook FAQ",
            "source_type": "faq",
            "raw_text": "Dhaka delivery takes 1 day. Comment replies should stay polite and concise.",
        },
    )
    assert knowledge.status_code == 200

    page = client.post(
        "/api/v1/facebook-pages",
        headers=platform_headers,
        json={
            "brand_id": brand_json["id"],
            "page_name": "Facebook Brand Page",
            "page_id": "1234567890",
            "page_username": "facebook-brand",
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
    return platform_headers, brand_json, page.json()


def test_facebook_webhook_verification_uses_saved_verify_token(tmp_path):
    with build_client(tmp_path) as client:
        _create_brand_and_page(client)

        verified = client.get(
            "/api/v1/facebook/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "verify-token-1",
                "hub.challenge": "challenge-123",
            },
        )
        assert verified.status_code == 200
        assert verified.text == "challenge-123"

        rejected = client.get(
            "/api/v1/facebook/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong-token",
                "hub.challenge": "challenge-456",
            },
        )
        assert rejected.status_code == 403


def test_facebook_webhook_processes_messenger_messages_into_conversations(tmp_path, monkeypatch):
    with build_client(tmp_path) as client:
        from app.services import facebook_webhooks

        calls = []

        class FakeResponse:
            status_code = 200
            text = '{"recipient_id":"psid-1","message_id":"fb-mid-1"}'

            def json(self):
                return {"recipient_id": "psid-1", "message_id": "fb-mid-1"}

        def fake_post(url, params=None, json=None, timeout=None):
            calls.append(
                {
                    "url": url,
                    "params": params,
                    "json": json,
                    "timeout": timeout,
                }
            )
            return FakeResponse()

        monkeypatch.setattr(facebook_webhooks.httpx, "post", fake_post)
        platform_headers, brand_json, _ = _create_brand_and_page(client)

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
                                "sender": {"id": "psid-1"},
                                "recipient": {"id": "1234567890"},
                                "timestamp": 1713900001,
                                "message": {
                                    "mid": "mid-1",
                                    "text": "How long does shipping take in Dhaka?",
                                },
                            }
                        ],
                    }
                ],
            },
        )
        assert webhook.status_code == 200
        body = webhook.json()
        assert body["processed"] == 1
        assert body["errors"] == 0
        assert len(calls) == 1
        assert calls[0]["url"] == "https://graph.facebook.com/v25.0/me/messages"
        assert calls[0]["params"] == {"access_token": "page-token-1"}
        assert calls[0]["json"]["recipient"] == {"id": "psid-1"}
        assert calls[0]["json"]["messaging_type"] == "RESPONSE"
        assert "Dhaka delivery takes 1 day" in calls[0]["json"]["message"]["text"]

        conversations = client.get(
            "/api/v1/conversations",
            headers=platform_headers,
            params={"brand_id": brand_json["id"]},
        )
        assert conversations.status_code == 200
        conversation = conversations.json()[0]
        assert conversation["channel"] == "facebook_messenger"
        assert conversation["external_conversation_id"] == "facebook:1234567890:psid-1"
        assert len(conversation["messages"]) == 2
        assert conversation["messages"][0]["text"] == "How long does shipping take in Dhaka?"
        assert "Dhaka delivery takes 1 day" in conversation["messages"][1]["text"]
        assert conversation["messages"][1]["external_message_id"] == "fb-mid-1"


def test_facebook_webhook_retries_messenger_delivery_after_a_send_api_failure(tmp_path, monkeypatch):
    with build_client(tmp_path) as client:
        from app.services import facebook_webhooks

        calls = []

        class FakeFailureResponse:
            status_code = 400
            text = '{"error":{"message":"Token expired","code":190}}'

            def json(self):
                return {"error": {"message": "Token expired", "code": 190}}

        class FakeSuccessResponse:
            status_code = 200
            text = '{"recipient_id":"psid-1","message_id":"fb-mid-2"}'

            def json(self):
                return {"recipient_id": "psid-1", "message_id": "fb-mid-2"}

        def fake_post(url, params=None, json=None, timeout=None):
            calls.append(
                {
                    "url": url,
                    "params": params,
                    "json": json,
                    "timeout": timeout,
                }
            )
            if len(calls) == 1:
                return FakeFailureResponse()
            return FakeSuccessResponse()

        monkeypatch.setattr(facebook_webhooks.httpx, "post", fake_post)
        platform_headers, brand_json, _ = _create_brand_and_page(client)

        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "1234567890",
                    "time": 1713900000,
                    "messaging": [
                        {
                            "sender": {"id": "psid-1"},
                            "recipient": {"id": "1234567890"},
                            "timestamp": 1713900001,
                            "message": {
                                "mid": "mid-1",
                                "text": "How long does shipping take in Dhaka?",
                            },
                        }
                    ],
                }
            ],
        }

        first_attempt = client.post("/api/v1/facebook/webhook", json=payload)
        assert first_attempt.status_code == 200
        assert first_attempt.json()["errors"] == 1
        assert len(calls) == 1

        second_attempt = client.post("/api/v1/facebook/webhook", json=payload)
        assert second_attempt.status_code == 200
        assert second_attempt.json()["processed"] == 1
        assert second_attempt.json()["errors"] == 0
        assert len(calls) == 2

        conversations = client.get(
            "/api/v1/conversations",
            headers=platform_headers,
            params={"brand_id": brand_json["id"]},
        )
        assert conversations.status_code == 200
        conversation = conversations.json()[0]
        assert len(conversation["messages"]) == 2
        assert conversation["messages"][1]["external_message_id"] == "fb-mid-2"


def test_facebook_webhook_processes_page_comment_events(tmp_path):
    with build_client(tmp_path) as client:
        platform_headers, brand_json, _ = _create_brand_and_page(client)

        webhook = client.post(
            "/api/v1/facebook/webhook",
            json={
                "object": "page",
                "entry": [
                    {
                        "id": "1234567890",
                        "time": 1713900100,
                        "changes": [
                            {
                                "field": "feed",
                                "value": {
                                    "item": "comment",
                                    "verb": "add",
                                    "comment_id": "comment-1",
                                    "post_id": "post-1",
                                    "message": "Do you deliver outside Dhaka?",
                                    "from": {"id": "commenter-1", "name": "Rahim"},
                                },
                            }
                        ],
                    }
                ],
            },
        )
        assert webhook.status_code == 200
        body = webhook.json()
        assert body["processed"] == 1
        assert body["errors"] == 0

        conversations = client.get(
            "/api/v1/conversations",
            headers=platform_headers,
            params={"brand_id": brand_json["id"]},
        )
        assert conversations.status_code == 200
        conversation = conversations.json()[0]
        assert conversation["channel"] == "facebook_comment"
        assert conversation["external_conversation_id"] == "facebook-comment:1234567890:comment-1"
        assert len(conversation["messages"]) == 2
        assert conversation["messages"][0]["text"] == "Do you deliver outside Dhaka?"
        assert "Dhaka delivery takes 1 day" in conversation["messages"][1]["text"]
