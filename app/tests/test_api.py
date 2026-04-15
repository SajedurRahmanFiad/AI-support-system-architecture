from __future__ import annotations

import os
import sys

from fastapi.testclient import TestClient


def build_client(tmp_path):
    db_path = tmp_path / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["PLATFORM_API_TOKEN"] = "test-platform-token"
    os.environ["LLM_PROVIDER"] = "mock"
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
