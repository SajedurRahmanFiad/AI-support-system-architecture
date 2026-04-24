from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException, status


class FacebookPageCredentialValidator:
    graph_api_base_url = "https://graph.facebook.com"

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = timeout_seconds

    def validate_page_access_token(
        self,
        *,
        app_id: str,
        app_secret: str,
        page_id: str,
        page_access_token: str,
    ) -> None:
        app_access_token = f"{app_id.strip()}|{app_secret.strip()}"

        try:
            response = httpx.get(
                f"{self.graph_api_base_url}/debug_token",
                params={
                    "input_token": page_access_token.strip(),
                    "access_token": app_access_token,
                },
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not validate Facebook page credentials: {exc}",
            ) from exc

        payload = self._parse_json(response)
        if response.status_code >= 400:
            detail = self._extract_error_detail(payload) or response.text or f"HTTP {response.status_code}"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Facebook rejected the supplied page credentials: {detail}",
            )

        token_data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(token_data, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Facebook credential validation returned an invalid response payload.",
            )

        if not bool(token_data.get("is_valid")):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Facebook page access token is invalid or expired.",
            )

        token_type = str(token_data.get("type") or "").strip().upper()
        if token_type != "PAGE":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Facebook page access token must be a PAGE token. "
                    f"The supplied token is {token_type or 'unknown'}."
                ),
            )

        profile_id = str(token_data.get("profile_id") or "").strip()
        if profile_id and profile_id != page_id.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Facebook page access token does not belong to the selected Page ID. "
                    f"Expected {page_id.strip()}, got {profile_id}."
                ),
            )

        if not self._has_page_scope(token_data, page_id.strip(), "pages_messaging"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Facebook page access token is missing the pages_messaging permission "
                    "for the selected page."
                ),
            )

    @staticmethod
    def _parse_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Facebook credential validation returned non-JSON output.",
            ) from exc

    @staticmethod
    def _extract_error_detail(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        error = payload.get("error")
        if not isinstance(error, dict):
            return None
        message = str(error.get("message") or "").strip()
        code = str(error.get("code") or "").strip()
        subcode = str(error.get("error_subcode") or "").strip()
        parts = [item for item in (message, code, subcode) if item]
        return " | ".join(parts) if parts else None

    @staticmethod
    def _has_page_scope(token_data: dict[str, Any], page_id: str, expected_scope: str) -> bool:
        scopes = token_data.get("scopes")
        if isinstance(scopes, list) and expected_scope in {str(item).strip() for item in scopes}:
            return True

        granular_scopes = token_data.get("granular_scopes")
        if not isinstance(granular_scopes, list):
            return False

        for scope_entry in granular_scopes:
            if not isinstance(scope_entry, dict):
                continue
            scope_name = str(scope_entry.get("scope") or "").strip()
            if scope_name != expected_scope:
                continue
            target_ids = scope_entry.get("target_ids")
            if not isinstance(target_ids, list):
                continue
            if page_id in {str(item).strip() for item in target_ids}:
                return True
        return False
