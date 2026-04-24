from __future__ import annotations

from app.tests.test_api import build_client


def test_brand_specific_llm_settings_override_global_provider(tmp_path):
    with build_client(tmp_path) as client:
        headers = {"X-Platform-Token": "test-platform-token"}
        brand = client.post(
            "/api/v1/brands",
            headers=headers,
            json={
                "name": "Provider Override Brand",
                "slug": "provider-override-brand",
                "llm_settings": {
                    "provider": "openrouter",
                    "model": "openai/gpt-4.1-mini",
                    "api_key": "or-test-key",
                    "summary_model": "openai/gpt-4.1-mini",
                    "embedding_model": "openai/text-embedding-3-small",
                    "temperature": 0.4,
                    "site_url": "https://example.com",
                    "app_name": "Provider Override",
                },
            },
        )
        assert brand.status_code == 200
        brand_json = brand.json()
        assert brand_json["llm_settings"]["provider"] == "openrouter"
        assert brand_json["llm_settings"]["api_key"] == "or-test-key"
        assert brand_json["llm_settings"]["masked_api_key"]

        from app import models
        from app.database import SessionLocal
        from app.services.llm.factory import build_llm_provider

        with SessionLocal() as db:
            stored_brand = db.get(models.Brand, brand_json["id"])
            provider = build_llm_provider(stored_brand)

        assert provider.provider_name == "openrouter"
