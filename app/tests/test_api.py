from __future__ import annotations

import base64
import os
import sys

from fastapi.testclient import TestClient

TINY_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO3Zk3sAAAAASUVORK5CYII=")


def build_client(tmp_path):
    db_path = tmp_path / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["UPLOAD_DIR"] = str((tmp_path / "uploads").as_posix())
    os.environ["PLATFORM_API_TOKEN"] = "test-platform-token"
    os.environ["LLM_PROVIDER"] = "mock"
    os.environ["SPEECH_PROVIDER"] = "mock"
    os.environ.pop("GEMINI_API_KEY", None)

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            sys.modules.pop(module_name)

    from app.main import create_app

    app = create_app()
    return TestClient(app)


def test_brand_setup_and_reply_flow(tmp_path):
    with build_client(tmp_path) as client:
        headers = {"X-Platform-Token": "test-platform-token"}
        brand = client.post(
            "/api/v1/brands",
            headers=headers,
            json={"name": "Demo", "slug": "demo"},
        )
        assert brand.status_code == 200
        brand_data = brand.json()

        knowledge = client.post(
            "/api/v1/knowledge/documents",
            headers=headers,
            json={
                "brand_id": brand_data["id"],
                "title": "FAQ",
                "source_type": "faq",
                "raw_text": "Shipping in Dhaka takes 1 day. Cash on delivery is available.",
            },
        )
        assert knowledge.status_code == 200

        reply = client.post(
            "/api/v1/messages/process",
            headers={"X-Brand-Api-Key": brand_data["api_key"]},
            json={
                "brand_id": brand_data["id"],
                "customer_external_id": "cust-1",
                "customer_name": "Sajed",
                "conversation_external_id": "conv-1",
                "text": "How long does shipping take in Dhaka?",
            },
        )
        assert reply.status_code == 200
        body = reply.json()
        assert body["status"] == "send"
        assert "Dhaka" in body["reply_text"]
        assert body["conversation_id"] is not None


def test_sensitive_message_handoffs(tmp_path):
    with build_client(tmp_path) as client:
        headers = {"X-Platform-Token": "test-platform-token"}
        brand = client.post("/api/v1/brands", headers=headers, json={"name": "Demo 2", "slug": "demo-2"})
        api_key = brand.json()["api_key"]
        reply = client.post(
            "/api/v1/messages/process",
            headers={"X-Brand-Api-Key": api_key},
            json={
                "brand_id": brand.json()["id"],
                "customer_external_id": "cust-2",
                "conversation_external_id": "conv-2",
                "text": "I want a refund and I need a manager.",
            },
        )
        assert reply.status_code == 200
        body = reply.json()
        assert body["status"] == "handoff"
        assert body["handoff_reason"]


def test_async_message_job(tmp_path):
    with build_client(tmp_path) as client:
        headers = {"X-Platform-Token": "test-platform-token"}
        brand = client.post("/api/v1/brands", headers=headers, json={"name": "Demo 3", "slug": "demo-3"})
        brand_json = brand.json()

        queued = client.post(
            "/api/v1/messages/process",
            headers={"X-Brand-Api-Key": brand_json["api_key"]},
            json={
                "brand_id": brand_json["id"],
                "customer_external_id": "cust-3",
                "conversation_external_id": "conv-3",
                "text": "Hello there",
                "process_async": True,
            },
        )
        assert queued.status_code == 200
        assert queued.json()["status"] == "queued"

        job_run = client.post("/api/v1/jobs/process-pending", headers=headers, json={"limit": 10})
        assert job_run.status_code == 200
        jobs = job_run.json()
        assert jobs[0]["status"] == "completed"


def test_product_image_training_and_recognition(tmp_path):
    with build_client(tmp_path) as client:
        headers = {"X-Platform-Token": "test-platform-token"}
        brand = client.post("/api/v1/brands", headers=headers, json={"name": "Catalog", "slug": "catalog"})
        brand_json = brand.json()

        add_image = client.post(
            "/api/v1/products/images/add",
            headers={"X-Brand-Api-Key": brand_json["api_key"]},
            files={"file": ("red-mug.png", TINY_PNG, "image/png")},
            data={
                "brand_id": str(brand_json["id"]),
                "product_name": "Red Mug",
                "category": "mugs",
                "metadata": '{"sku":"RM-1","aliases":["coffee mug","tea mug"]}',
            },
        )
        assert add_image.status_code == 200
        assert add_image.json()["product_name"] == "Red Mug"

        recognize = client.post(
            "/api/v1/products/recognize",
            headers={"X-Brand-Api-Key": brand_json["api_key"]},
            files={"file": ("customer-photo.png", TINY_PNG, "image/png")},
            data={
                "brand_id": str(brand_json["id"]),
                "customer_text": "I want this mug",
            },
        )
        assert recognize.status_code == 200
        body = recognize.json()
        assert body["matched"] is True
        assert body["product_name"] == "Red Mug"


def test_message_flow_uses_product_match_for_knowledge(tmp_path):
    with build_client(tmp_path) as client:
        headers = {"X-Platform-Token": "test-platform-token"}
        brand = client.post("/api/v1/brands", headers=headers, json={"name": "Store", "slug": "store"})
        brand_json = brand.json()

        add_image = client.post(
            "/api/v1/products/images/add",
            headers={"X-Brand-Api-Key": brand_json["api_key"]},
            files={"file": ("red-mug.png", TINY_PNG, "image/png")},
            data={
                "brand_id": str(brand_json["id"]),
                "product_name": "Red Mug",
                "category": "mugs",
            },
        )
        assert add_image.status_code == 200

        knowledge = client.post(
            "/api/v1/knowledge/documents",
            headers=headers,
            json={
                "brand_id": brand_json["id"],
                "title": "Red Mug",
                "source_type": "catalog",
                "raw_text": "Red Mug price is 500 taka and it is available in stock.",
            },
        )
        assert knowledge.status_code == 200

        upload = client.post(
            "/api/v1/uploads",
            headers={"X-Brand-Api-Key": brand_json["api_key"]},
            files={"file": ("customer-photo.png", TINY_PNG, "image/png")},
            data={"brand_id": str(brand_json["id"])},
        )
        assert upload.status_code == 200
        attachment_id = upload.json()["attachment"]["id"]

        reply = client.post(
            "/api/v1/messages/process",
            headers={"X-Brand-Api-Key": brand_json["api_key"]},
            json={
                "brand_id": brand_json["id"],
                "customer_external_id": "cust-visual",
                "conversation_external_id": "conv-visual",
                "text": "What is the price of this?",
                "attachment_ids": [attachment_id],
            },
        )
        assert reply.status_code == 200
        body = reply.json()
        assert body["status"] == "send"
        assert "500" in body["reply_text"]
        assert any(flag.startswith("product-match:Red Mug") for flag in body["flags"])


def test_audio_attachment_transcription_flow(tmp_path):
    with build_client(tmp_path) as client:
        headers = {"X-Platform-Token": "test-platform-token"}
        brand = client.post(
            "/api/v1/brands",
            headers=headers,
            json={"name": "Bangla Store", "slug": "bangla-store", "default_language": "bn-BD"},
        )
        brand_json = brand.json()

        upload = client.post(
            "/api/v1/uploads",
            headers={"X-Brand-Api-Key": brand_json["api_key"]},
            files={"file": ("voice.mp3", b"FAKEAUDIO123", "audio/mpeg")},
            data={"brand_id": str(brand_json["id"])},
        )
        assert upload.status_code == 200
        attachment_id = upload.json()["attachment"]["id"]

        reply = client.post(
            "/api/v1/messages/process",
            headers={"X-Brand-Api-Key": brand_json["api_key"]},
            json={
                "brand_id": brand_json["id"],
                "customer_external_id": "voice-customer",
                "conversation_external_id": "voice-conv",
                "text": "",
                "attachment_ids": [attachment_id],
            },
        )
        assert reply.status_code == 200
        body = reply.json()
        assert body["status"] == "send"
        assert "audio-transcribed" in body["flags"]


def test_unclear_audio_requests_clarification(tmp_path):
    with build_client(tmp_path) as client:
        headers = {"X-Platform-Token": "test-platform-token"}
        brand = client.post(
            "/api/v1/brands",
            headers=headers,
            json={"name": "Clarify Store", "slug": "clarify-store", "default_language": "bn-BD"},
        )
        brand_json = brand.json()

        upload = client.post(
            "/api/v1/uploads",
            headers={"X-Brand-Api-Key": brand_json["api_key"]},
            files={"file": ("noise.mp3", b"NOISY-VOICE-DATA", "audio/mpeg")},
            data={"brand_id": str(brand_json["id"])},
        )
        assert upload.status_code == 200
        attachment_id = upload.json()["attachment"]["id"]

        reply = client.post(
            "/api/v1/messages/process",
            headers={"X-Brand-Api-Key": brand_json["api_key"]},
            json={
                "brand_id": brand_json["id"],
                "customer_external_id": "noisy-customer",
                "conversation_external_id": "noisy-conv",
                "text": "",
                "attachment_ids": [attachment_id],
            },
        )
        assert reply.status_code == 200
        body = reply.json()
        assert body["status"] == "clarify"
        assert "ভয়েস" in body["reply_text"]
