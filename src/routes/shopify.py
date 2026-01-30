"""Shopify OAuth and sync endpoints."""
import secrets
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db, ShopifyAuth

settings = get_settings()
router = APIRouter()


@router.get("/cdo/auth/shopify", tags=["Auth"])
async def shopify_auth_redirect():
    """Initiate Shopify OAuth flow."""
    if not settings.shopify_client_id:
        raise HTTPException(status_code=400, detail="Shopify credentials not configured")

    state = secrets.token_urlsafe(32)
    scopes = "read_products,read_orders,read_customers,read_inventory"

    auth_url = (
        f"https://{settings.shopify_store}/admin/oauth/authorize"
        f"?client_id={settings.shopify_client_id}"
        f"&scope={scopes}"
        f"&redirect_uri={settings.cdo_api_url or 'http://localhost:8000'}/cdo/auth/shopify/callback"
        f"&state={state}"
    )

    return {"auth_url": auth_url, "state": state}


@router.get("/cdo/auth/shopify/callback", tags=["Auth"])
async def shopify_callback(
    code: str,
    state: str,
    shop: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Handle Shopify OAuth callback."""
    if not settings.shopify_client_id or not settings.shopify_client_secret:
        raise HTTPException(status_code=400, detail="Shopify credentials not configured")

    token_url = f"https://{settings.shopify_store}/admin/oauth/access_token"

    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, json={
            "client_id": settings.shopify_client_id,
            "client_secret": settings.shopify_client_secret,
            "code": code
        })

        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to exchange code for token")

        data = response.json()
        access_token = data.get("access_token")
        scope = data.get("scope")

    auth = db.query(ShopifyAuth).filter(ShopifyAuth.store == settings.shopify_store).first()
    if auth:
        auth.access_token = access_token
        auth.scope = scope
        auth.updated_at = datetime.utcnow()
    else:
        auth = ShopifyAuth(
            store=settings.shopify_store,
            access_token=access_token,
            scope=scope
        )
        db.add(auth)

    db.commit()

    return {"success": True, "message": "Shopify connected successfully", "scope": scope}


@router.post("/cdo/sync/orders", tags=["Sync"])
async def sync_shopify_orders(
    days: int = 30,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """Sync orders from Shopify for analytics."""
    auth = db.query(ShopifyAuth).filter(ShopifyAuth.store == settings.shopify_store).first()
    if not auth:
        raise HTTPException(status_code=400, detail="Shopify not connected")

    return {
        "success": True,
        "message": f"Order sync initiated for last {days} days",
        "note": "Full implementation would sync from Shopify GraphQL API"
    }
