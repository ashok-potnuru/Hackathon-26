import hmac

from fastapi import HTTPException, Request


async def verify_zoho_webhook(request: Request, token: str) -> None:
    if not token:
        return
    incoming = request.headers.get("X-ZOHO-WEBHOOK-TOKEN", "")
    if not hmac.compare_digest(incoming, token):
        raise HTTPException(status_code=401, detail="Invalid Zoho webhook token")
