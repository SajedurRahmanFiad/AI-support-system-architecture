from __future__ import annotations

from app.tests.test_api import TINY_PNG, build_client


def test_dashboard_admin_routes(tmp_path):
    with build_client(tmp_path) as client:
        platform_headers = {"X-Platform-Token": "test-platform-token"}
        brand = client.post(
            "/api/v1/brands",
            headers=platform_headers,
            json={"name": "Admin Brand", "slug": "admin-brand"},
        )
        assert brand.status_code == 200
        brand_json = brand.json()
        brand_id = brand_json["id"]
        brand_headers = {"X-Brand-Api-Key": brand_json["api_key"]}

        rule = client.post(
            f"/api/v1/brands/{brand_id}/rules",
            headers=platform_headers,
            json={
                "title": "Escalate refunds",
                "content": "Hand off refund disputes.",
                "handoff_on_match": True,
                "priority": 10,
            },
        )
        assert rule.status_code == 200
        rule_id = rule.json()["id"]

        update_rule = client.patch(
            f"/api/v1/brands/{brand_id}/rules/{rule_id}",
            headers=platform_headers,
            json={"title": "Escalate payment refunds", "priority": 5},
        )
        assert update_rule.status_code == 200
        assert update_rule.json()["priority"] == 5

        style = client.post(
            f"/api/v1/brands/{brand_id}/style-examples",
            headers=platform_headers,
            json={
                "title": "Friendly Bangla availability",
                "trigger_text": "ভাই এটা আছে?",
                "ideal_reply": "জ্বি ভাই, available আছে।",
                "priority": 20,
            },
        )
        assert style.status_code == 200
        example_id = style.json()["id"]

        update_style = client.patch(
            f"/api/v1/brands/{brand_id}/style-examples/{example_id}",
            headers=platform_headers,
            json={"notes": "Use mixed Bangla-English", "priority": 8},
        )
        assert update_style.status_code == 200
        assert update_style.json()["priority"] == 8

        document = client.post(
            "/api/v1/knowledge/documents",
            headers=platform_headers,
            json={
                "brand_id": brand_id,
                "title": "Delivery Policy",
                "source_type": "policy",
                "raw_text": "Inside Dhaka delivery takes 1 day.",
            },
        )
        assert document.status_code == 200
        document_id = document.json()["id"]

        updated_document = client.patch(
            f"/api/v1/knowledge/documents/{document_id}",
            headers=platform_headers,
            json={"raw_text": "Inside Dhaka delivery takes 1 day. Outside Dhaka takes 3 days."},
        )
        assert updated_document.status_code == 200
        assert "Outside Dhaka" in updated_document.json()["raw_text"]

        upload = client.post(
            "/api/v1/uploads",
            headers=brand_headers,
            files={"file": ("guide.png", TINY_PNG, "image/png")},
            data={"brand_id": str(brand_id)},
        )
        assert upload.status_code == 200
        attachment_id = upload.json()["attachment"]["id"]

        uploads = client.get(
            "/api/v1/uploads",
            headers=platform_headers,
            params={"brand_id": brand_id},
        )
        assert uploads.status_code == 200
        assert uploads.json()[0]["id"] == attachment_id

        download_upload = client.get(
            f"/api/v1/uploads/{attachment_id}/download",
            headers=platform_headers,
            params={"brand_id": brand_id},
        )
        assert download_upload.status_code == 200
        assert download_upload.content == TINY_PNG

        reply = client.post(
            "/api/v1/messages/process",
            headers=brand_headers,
            json={
                "brand_id": brand_id,
                "customer_external_id": "dash-customer",
                "customer_name": "Rahim",
                "conversation_external_id": "dash-conversation",
                "text": "How long does outside Dhaka delivery take?",
            },
        )
        assert reply.status_code == 200
        reply_json = reply.json()
        assert reply_json["status"] == "send"

        dashboard_overview = client.get(
            "/api/v1/dashboard/overview",
            headers=platform_headers,
        )
        assert dashboard_overview.status_code == 200
        assert dashboard_overview.json()["totals"]["brands"] == 1
        assert dashboard_overview.json()["brand_options"][0]["id"] == brand_id

        dashboard_brands = client.get(
            "/api/v1/dashboard/brands",
            headers=platform_headers,
        )
        assert dashboard_brands.status_code == 200
        assert dashboard_brands.json()[0]["stats"]["conversations"] >= 1
        assert dashboard_brands.json()[0]["stats"]["uploads"] >= 1

        conversation_summaries = client.get(
            "/api/v1/conversations/summary",
            headers=platform_headers,
            params={"brand_id": brand_id},
        )
        assert conversation_summaries.status_code == 200
        assert "messages" not in conversation_summaries.json()[0]
        assert "last_message_text" in conversation_summaries.json()[0]

        customers = client.get(
            "/api/v1/customers",
            headers=platform_headers,
            params={"brand_id": brand_id},
        )
        assert customers.status_code == 200
        customer_id = customers.json()[0]["id"]

        update_customer = client.patch(
            f"/api/v1/customers/{customer_id}",
            headers=platform_headers,
            json={"city": "Dhaka", "short_summary": "Important repeat buyer"},
        )
        assert update_customer.status_code == 200
        assert update_customer.json()["city"] == "Dhaka"

        fact = client.post(
            f"/api/v1/customers/{customer_id}/facts",
            headers=platform_headers,
            json={"fact_key": "preferred_color", "fact_value": "blue", "confidence": 0.9},
        )
        assert fact.status_code == 200
        fact_id = fact.json()["id"]

        update_fact = client.patch(
            f"/api/v1/customers/{customer_id}/facts/{fact_id}",
            headers=platform_headers,
            json={"fact_value": "navy"},
        )
        assert update_fact.status_code == 200
        assert update_fact.json()["fact_value"] == "navy"

        feedback = client.post(
            f"/api/v1/messages/{reply_json['outbound_message_id']}/feedback",
            headers=platform_headers,
            json={
                "feedback_type": "correction",
                "corrected_reply": "ঢাকার বাইরে সাধারণত ৩ দিনের মতো সময় লাগে।",
                "notes": "Shorten the wording.",
                "metadata": {"rating": "negative"},
            },
        )
        assert feedback.status_code == 200

        feedback_list = client.get(
            "/api/v1/feedback",
            headers=platform_headers,
            params={"brand_id": brand_id},
        )
        assert feedback_list.status_code == 200
        assert feedback_list.json()[0]["message_id"] == reply_json["outbound_message_id"]
        feedback_id = feedback_list.json()[0]["id"]

        feedback_update = client.patch(
            f"/api/v1/feedback/{feedback_id}",
            headers=platform_headers,
            json={"notes": "Reviewed by dashboard", "metadata": {"rating": "negative", "reviewed": True}},
        )
        assert feedback_update.status_code == 200
        assert feedback_update.json()["metadata_json"]["reviewed"] is True

        audit_logs = client.get(
            "/api/v1/audit-logs",
            headers=platform_headers,
            params={"brand_id": brand_id},
        )
        assert audit_logs.status_code == 200
        assert any(item["event_type"] == "reply_generated" for item in audit_logs.json())

        product = client.post(
            "/api/v1/products/images/add",
            headers=brand_headers,
            files={"file": ("product.png", TINY_PNG, "image/png")},
            data={
                "brand_id": str(brand_id),
                "product_name": "Blue Chair",
                "category": "chairs",
            },
        )
        assert product.status_code == 200
        product_image_id = product.json()["product_image_id"]

        update_product = client.patch(
            f"/api/v1/products/images/{product_image_id}",
            headers=platform_headers,
            json={"category": "dining-chairs", "metadata": {"sku": "CHAIR-1"}},
        )
        assert update_product.status_code == 200
        assert update_product.json()["category"] == "dining-chairs"

        download_product = client.get(
            f"/api/v1/products/images/{product_image_id}/download",
            headers=platform_headers,
            params={"brand_id": brand_id},
        )
        assert download_product.status_code == 200
        assert download_product.content == TINY_PNG

        delete_upload = client.delete(
            f"/api/v1/uploads/{attachment_id}",
            headers=platform_headers,
            params={"brand_id": brand_id},
        )
        assert delete_upload.status_code == 200

        delete_style = client.delete(
            f"/api/v1/brands/{brand_id}/style-examples/{example_id}",
            headers=platform_headers,
        )
        assert delete_style.status_code == 200

        delete_rule = client.delete(
            f"/api/v1/brands/{brand_id}/rules/{rule_id}",
            headers=platform_headers,
        )
        assert delete_rule.status_code == 200

        delete_fact = client.delete(
            f"/api/v1/customers/{customer_id}/facts/{fact_id}",
            headers=platform_headers,
        )
        assert delete_fact.status_code == 200

        delete_document = client.delete(
            f"/api/v1/knowledge/documents/{document_id}",
            headers=platform_headers,
        )
        assert delete_document.status_code == 200
