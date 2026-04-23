from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse

from app.api.deps import DbSession
from app.services.facebook_webhooks import FacebookWebhookService

router = APIRouter(prefix="/v1/facebook")


@router.get("/webhook", response_class=PlainTextResponse)
def verify_facebook_webhook(
    db: DbSession,
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> PlainTextResponse:
    challenge = FacebookWebhookService(db).verify_subscription(
        mode=hub_mode,
        verify_token=hub_verify_token,
        challenge=hub_challenge,
    )
    return PlainTextResponse(content=challenge)


@router.post("/webhook")
async def receive_facebook_webhook(request: Request, db: DbSession) -> dict[str, object]:
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    return FacebookWebhookService(db).handle_payload(raw_body=raw_body, signature_header=signature)
