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


def test_conversation_example_can_be_promoted_into_rag(tmp_path):
    with build_client(tmp_path) as client:
        headers = {"X-Platform-Token": "test-platform-token"}
        brand = client.post("/api/v1/brands", headers=headers, json={"name": "RAG Brand", "slug": "rag-brand"})
        brand_json = brand.json()

        reply = client.post(
            "/api/v1/messages/process",
            headers={"X-Brand-Api-Key": brand_json["api_key"]},
            json={
                "brand_id": brand_json["id"],
                "customer_external_id": "rag-customer",
                "conversation_external_id": "rag-conversation",
                "text": "How quickly do orders inside Dhaka arrive?",
            },
        )
        assert reply.status_code == 200
        reply_json = reply.json()

        example = client.post(
            "/api/v1/knowledge/conversation-examples",
            headers=headers,
            json={
                "brand_id": brand_json["id"],
                "conversation_id": reply_json["conversation_id"],
                "customer_message_id": reply_json["inbound_message_id"],
                "assistant_message_id": reply_json["outbound_message_id"],
                "approved_reply": "Inside Dhaka, approved orders usually arrive within 1 day.",
                "notes": "Use this phrasing for common delivery ETA questions.",
            },
        )
        assert example.status_code == 200
        example_json = example.json()
        assert example_json["source_type"] == "conversation_training"

        search = client.post(
            "/api/v1/knowledge/search",
            headers=headers,
            json={
                "brand_id": brand_json["id"],
                "query": "How long does inside Dhaka delivery take?",
                "top_k": 5,
            },
        )
        assert search.status_code == 200
        hits = search.json()["hits"]
        assert any(hit["document_id"] == example_json["id"] for hit in hits)


def test_manual_conversation_example_can_be_saved_into_rag(tmp_path):
    with build_client(tmp_path) as client:
        headers = {"X-Platform-Token": "test-platform-token"}
        brand = client.post("/api/v1/brands", headers=headers, json={"name": "Manual RAG Brand", "slug": "manual-rag-brand"})
        brand_json = brand.json()

        example = client.post(
            "/api/v1/knowledge/manual-conversation-examples",
            headers=headers,
            json={
                "brand_id": brand_json["id"],
                "customer_text": "Do you deliver on Fridays inside Chattogram?",
                "approved_reply": "Yes, Friday delivery inside Chattogram is available for confirmed orders.",
                "notes": "Use this for weekend delivery availability questions.",
                "metadata": {"source": "manual-dashboard-entry"},
            },
        )
        assert example.status_code == 200
        example_json = example.json()
        assert example_json["source_type"] == "conversation_training"
        assert example_json["metadata_json"]["training_type"] == "manual_conversation_rag_example"

        search = client.post(
            "/api/v1/knowledge/search",
            headers=headers,
            json={
                "brand_id": brand_json["id"],
                "query": "Can you deliver inside Chattogram on Friday?",
                "top_k": 5,
            },
        )
        assert search.status_code == 200
        hits = search.json()["hits"]
        assert any(hit["document_id"] == example_json["id"] for hit in hits)


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


def test_llm_error_handoff_does_not_lock_conversation_to_human(tmp_path):
    with build_client(tmp_path) as client:
        headers = {"X-Platform-Token": "test-platform-token"}
        brand = client.post("/api/v1/brands", headers=headers, json={"name": "Demo 2b", "slug": "demo-2b"})
        brand_json = brand.json()
        api_key = brand_json["api_key"]

        from app.services.llm.mock import MockLLMProvider

        original = MockLLMProvider.generate_reply

        def broken_generate_reply(self, brand, customer, history, incoming_text, knowledge, attachment_insights):
            raise RuntimeError("temporary provider failure")

        MockLLMProvider.generate_reply = broken_generate_reply
        try:
            first_reply = client.post(
                "/api/v1/messages/process",
                headers={"X-Brand-Api-Key": api_key},
                json={
                    "brand_id": brand_json["id"],
                    "customer_external_id": "cust-llm-error",
                    "conversation_external_id": "conv-llm-error",
                    "text": "Hello there",
                },
            )
        finally:
            MockLLMProvider.generate_reply = original

        assert first_reply.status_code == 200
        first_body = first_reply.json()
        assert first_body["status"] == "handoff"
        assert "LLM service error" in first_body["handoff_reason"]

        second_reply = client.post(
            "/api/v1/messages/process",
            headers={"X-Brand-Api-Key": api_key},
            json={
                "brand_id": brand_json["id"],
                "customer_external_id": "cust-llm-error",
                "conversation_external_id": "conv-llm-error",
                "text": "Do you deliver in Dhaka?",
            },
        )
        assert second_reply.status_code == 200
        second_body = second_reply.json()
        assert second_body["status"] == "send"

        conversations = client.get(
            "/api/v1/conversations",
            headers=headers,
            params={"brand_id": brand_json["id"]},
        )
        assert conversations.status_code == 200
        conversation = conversations.json()[0]
        assert conversation["owner_type"] == "ai"


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


def test_product_image_training_accepts_multiple_files_and_groups_matches(tmp_path):
    with build_client(tmp_path) as client:
        headers = {"X-Platform-Token": "test-platform-token"}
        brand = client.post("/api/v1/brands", headers=headers, json={"name": "Catalog Groups", "slug": "catalog-groups"})
        brand_json = brand.json()

        add_images = client.post(
            "/api/v1/products/images/add",
            headers={"X-Brand-Api-Key": brand_json["api_key"]},
            files=[
                ("files", ("front-view.png", TINY_PNG, "image/png")),
                ("files", ("side-view.png", TINY_PNG, "image/png")),
            ],
            data={
                "brand_id": str(brand_json["id"]),
                "product_name": "Green Bottle",
                "category": "bottles",
            },
        )
        assert add_images.status_code == 200
        assert add_images.json()["count"] == 2

        listing = client.get(
            "/api/v1/products/images",
            headers=headers,
            params={"brand_id": brand_json["id"]},
        )
        assert listing.status_code == 200
        listing_json = listing.json()
        assert listing_json["count"] == 2
        assert listing_json["group_count"] == 1
        assert listing_json["product_groups"][0]["image_count"] == 2

        recognize = client.post(
            "/api/v1/products/recognize",
            headers={"X-Brand-Api-Key": brand_json["api_key"]},
            files={"file": ("customer-photo.png", TINY_PNG, "image/png")},
            data={
                "brand_id": str(brand_json["id"]),
                "customer_text": "I need this bottle",
            },
        )
        assert recognize.status_code == 200
        body = recognize.json()
        assert body["matched"] is True
        assert body["product_name"] == "Green Bottle"
        assert body["reference_image_count"] == 2


def test_product_recognition_handles_provider_analysis_failure(tmp_path):
    with build_client(tmp_path) as client:
        headers = {"X-Platform-Token": "test-platform-token"}
        brand = client.post("/api/v1/brands", headers=headers, json={"name": "Catalog Fallback", "slug": "catalog-fallback"})
        brand_json = brand.json()

        add_image = client.post(
            "/api/v1/products/images/add",
            headers={"X-Brand-Api-Key": brand_json["api_key"]},
            files={"file": ("red-mug.png", TINY_PNG, "image/png")},
            data={
                "brand_id": str(brand_json["id"]),
                "product_name": "Red Mug",
                "category": "mugs",
                "metadata": '{"sku":"RM-1"}',
            },
        )
        assert add_image.status_code == 200

        from app.services.llm.mock import MockLLMProvider

        original = MockLLMProvider.analyze_attachment

        def broken_analyze_attachment(self, attachment_type, mime_type, data):
            raise RuntimeError("temporary provider failure")

        MockLLMProvider.analyze_attachment = broken_analyze_attachment
        try:
            recognize = client.post(
                "/api/v1/products/recognize",
                headers={"X-Brand-Api-Key": brand_json["api_key"]},
                files={"file": ("customer-photo.png", TINY_PNG, "image/png")},
                data={
                    "brand_id": str(brand_json["id"]),
                    "customer_text": "I want this mug",
                },
            )
        finally:
            MockLLMProvider.analyze_attachment = original

        assert recognize.status_code == 200
        body = recognize.json()
        assert body["matched"] is True
        assert body["product_name"] == "Red Mug"
        assert "warning" in body


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
