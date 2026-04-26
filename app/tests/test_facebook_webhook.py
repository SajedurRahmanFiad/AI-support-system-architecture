from __future__ import annotations

import time

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


def test_facebook_webhook_batches_short_messenger_bursts_before_processing(tmp_path, monkeypatch):
    with build_client(
        tmp_path,
        env={
            "FACEBOOK_MESSAGE_BATCHING_ENABLED": "true",
            "FACEBOOK_MESSAGE_BATCH_WINDOW_SECONDS": "1",
        },
    ) as client:
        from app.services import facebook_webhooks

        calls = []

        class FakeResponse:
            status_code = 200
            text = '{"recipient_id":"psid-1","message_id":"fb-batch-mid-1"}'

            def json(self):
                return {"recipient_id": "psid-1", "message_id": "fb-batch-mid-1"}

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

        def send_message(mid: str, text: str) -> None:
            response = client.post(
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
                                        "mid": mid,
                                        "text": text,
                                    },
                                }
                            ],
                        }
                    ],
                },
            )
            assert response.status_code == 200
            assert response.json()["processed"] == 1

        send_message("mid-1", "I want to order")
        send_message("mid-2", "The nebulizer")
        send_message("mid-3", "From Dhaka")
        assert len(calls) == 0

        time.sleep(1.1)
        job_run = client.post("/api/v1/jobs/process-pending", headers=platform_headers, json={"limit": 10})
        assert job_run.status_code == 200
        assert len(calls) == 1

        conversations = client.get(
            "/api/v1/conversations",
            headers=platform_headers,
            params={"brand_id": brand_json["id"]},
        )
        assert conversations.status_code == 200
        conversation = conversations.json()[0]
        assert len(conversation["messages"]) == 2
        assert conversation["messages"][0]["text"] == "I want to order\nThe nebulizer\nFrom Dhaka"
        assert conversation["messages"][1]["external_message_id"] == "fb-batch-mid-1"


def test_facebook_webhook_batches_image_then_followup_text_and_preserves_ad_context(tmp_path, monkeypatch):
    with build_client(
        tmp_path,
        env={
            "FACEBOOK_MESSAGE_BATCHING_ENABLED": "true",
            "FACEBOOK_MESSAGE_BATCH_WINDOW_SECONDS": "1",
        },
    ) as client:
        from app.services import facebook_webhooks

        send_calls = []
        download_calls = []

        class FakeSendResponse:
            status_code = 200
            text = '{"recipient_id":"psid-4","message_id":"fb-batch-image-1"}'

            def json(self):
                return {"recipient_id": "psid-4", "message_id": "fb-batch-image-1"}

        class FakeDownloadResponse:
            status_code = 200
            headers = {"content-type": "image/png"}
            content = b"PNGDATA"

        def fake_post(url, params=None, json=None, timeout=None):
            send_calls.append({"url": url, "params": params, "json": json, "timeout": timeout})
            return FakeSendResponse()

        def fake_get(url, params=None, timeout=None, follow_redirects=None):
            download_calls.append({"url": url, "params": params, "timeout": timeout})
            return FakeDownloadResponse()

        monkeypatch.setattr(facebook_webhooks.httpx, "post", fake_post)
        monkeypatch.setattr(facebook_webhooks.httpx, "get", fake_get)
        platform_headers, brand_json, _ = _create_brand_and_page(client)

        image_message = client.post(
            "/api/v1/facebook/webhook",
            json={
                "object": "page",
                "entry": [
                    {
                        "id": "1234567890",
                        "time": 1713900000,
                        "messaging": [
                            {
                                "sender": {"id": "psid-4"},
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
                                "referral": {
                                    "ref": "campaign-a",
                                    "ad_id": "ad-123",
                                    "ads_context_data": {"ad_id": "ad-123", "ad_title": "Nebulizer ad"},
                                },
                            }
                        ],
                    }
                ],
            },
        )
        assert image_message.status_code == 200

        followup_message = client.post(
            "/api/v1/facebook/webhook",
            json={
                "object": "page",
                "entry": [
                    {
                        "id": "1234567890",
                        "time": 1713900002,
                        "messaging": [
                            {
                                "sender": {"id": "psid-4"},
                                "recipient": {"id": "1234567890"},
                                "timestamp": 1713900003,
                                "message": {
                                    "mid": "mid-image-2",
                                    "text": "Can you tell me about this item?",
                                },
                            }
                        ],
                    }
                ],
            },
        )
        assert followup_message.status_code == 200
        assert len(send_calls) == 0
        assert any(call["url"] == "https://cdn.example.com/customer-image.png" for call in download_calls)

        time.sleep(1.1)
        job_run = client.post("/api/v1/jobs/process-pending", headers=platform_headers, json={"limit": 10})
        assert job_run.status_code == 200
        assert len(send_calls) == 1

        conversations = client.get(
            "/api/v1/conversations",
            headers=platform_headers,
            params={"brand_id": brand_json["id"]},
        )
        assert conversations.status_code == 200
        conversation = conversations.json()[0]
        assert len(conversation["messages"]) == 2
        assert conversation["messages"][0]["text"] == "Can you tell me about this item?"
        assert len(conversation["messages"][0]["attachments"]) == 1
        assert conversation["metadata_json"]["ad_id"] == "ad-123"
        assert conversation["metadata_json"]["referral"]["ad_title"] == "Nebulizer ad"


def test_facebook_webhook_async_handoff_applies_pending_review_label(tmp_path, monkeypatch):
    with build_client(
        tmp_path,
        env={
            "FACEBOOK_WEBHOOK_ASYNC_ENABLED": "true",
        },
    ) as client:
        from app.services import facebook_webhooks

        label_calls = []

        def fake_send_text_message(self, recipient_id: str, text: str):
            return {"recipient_id": recipient_id, "message_id": "fb-handoff-1"}

        def fake_ensure_custom_label(self, page_id: str, label_name: str):
            return "label-pending-review"

        def fake_associate_label(self, recipient_id: str, label_id: str):
            label_calls.append((recipient_id, label_id))
            return True

        monkeypatch.setattr(facebook_webhooks.FacebookMessengerClient, "send_text_message", fake_send_text_message)
        monkeypatch.setattr(facebook_webhooks.FacebookMessengerClient, "ensure_custom_label", fake_ensure_custom_label)
        monkeypatch.setattr(facebook_webhooks.FacebookMessengerClient, "associate_label", fake_associate_label)
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
                                "sender": {"id": "psid-handoff"},
                                "recipient": {"id": "1234567890"},
                                "timestamp": 1713900001,
                                "message": {
                                    "mid": "mid-handoff-1",
                                    "text": "I need a refund right now",
                                },
                            }
                        ],
                    }
                ],
            },
        )
        assert webhook.status_code == 200
        assert webhook.json()["processed"] == 1

        job_run = client.post("/api/v1/jobs/process-pending", headers=platform_headers, json={"limit": 10})
        assert job_run.status_code == 200
        assert label_calls == [("psid-handoff", "label-pending-review")]

        conversations = client.get(
            "/api/v1/conversations",
            headers=platform_headers,
            params={"brand_id": brand_json["id"]},
        )
        assert conversations.status_code == 200
        conversation = conversations.json()[0]
        assert conversation["status"] == "handoff"
        assert conversation["metadata_json"]["labels"]["pending_review"] == "label-pending-review"


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
