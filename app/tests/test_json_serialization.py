from __future__ import annotations

import json

from pydantic import BaseModel

from app.models import JSONText


class UsageMetadata(BaseModel):
    prompt_token_count: int
    candidates_token_count: int
    total_token_count: int


def test_json_text_serializes_pydantic_models() -> None:
    payload = {
        "token_usage": UsageMetadata(
            prompt_token_count=120,
            candidates_token_count=80,
            total_token_count=200,
        )
    }

    encoded = JSONText().process_bind_param(payload, None)

    assert json.loads(encoded) == {
        "token_usage": {
            "prompt_token_count": 120,
            "candidates_token_count": 80,
            "total_token_count": 200,
        }
    }
