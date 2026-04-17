import hashlib
import hmac
from fastapi import Request, HTTPException


async def verify_github_signature(request: Request, secret: str) -> None:
    signature = request.headers.get("X-Hub-Signature-256", "")
    body = await request.body()
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid signature")


async def verify_zoho_webhook(request: Request, token: str) -> None:
    if not token:
        return
    incoming = request.headers.get("X-ZOHO-WEBHOOK-TOKEN", "")
    if not hmac.compare_digest(incoming, token):
        raise HTTPException(status_code=401, detail="Invalid Zoho webhook token")
