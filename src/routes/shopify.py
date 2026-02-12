"""Shopify OAuth and sync endpoints."""
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db, ShopifyAuth, SalesSnapshot, ProductPerformance

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


ORDERS_QUERY = """
query($cursor: String, $query: String) {
  orders(first: 50, after: $cursor, query: $query, sortKey: CREATED_AT) {
    edges {
      cursor
      node {
        id
        name
        createdAt
        totalPriceSet { shopMoney { amount currencyCode } }
        subtotalPriceSet { shopMoney { amount } }
        currentTotalTax { amount }
        displayFinancialStatus
        displayFulfillmentStatus
        customer { id email numberOfOrders }
        lineItems(first: 50) {
          edges {
            node {
              sku
              name
              quantity
              originalUnitPriceSet { shopMoney { amount } }
              variant { id product { id } }
            }
          }
        }
      }
    }
    pageInfo { hasNextPage }
  }
}
"""


async def _fetch_shopify_orders(access_token: str, days: int) -> list:
    """Fetch orders from Shopify GraphQL API."""
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    url = f"https://{settings.shopify_store}/admin/api/2024-01/graphql.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }

    all_orders = []
    cursor = None

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            variables = {"query": f"created_at:>={since}"}
            if cursor:
                variables["cursor"] = cursor

            resp = await client.post(url, headers=headers, json={
                "query": ORDERS_QUERY,
                "variables": variables,
            })

            if resp.status_code != 200:
                logger.error(f"Shopify GraphQL error: {resp.status_code} - {resp.text[:500]}")
                break

            data = resp.json().get("data", {}).get("orders", {})
            edges = data.get("edges", [])

            for edge in edges:
                all_orders.append(edge["node"])
                cursor = edge["cursor"]

            if not data.get("pageInfo", {}).get("hasNextPage"):
                break

    return all_orders


def _aggregate_daily_snapshots(orders: list, db: Session):
    """Aggregate orders into daily SalesSnapshot records."""
    daily = {}

    for order in orders:
        date_str = order["createdAt"][:10]
        day = datetime.strptime(date_str, "%Y-%m-%d")

        if day not in daily:
            daily[day] = {
                "orders": 0, "revenue": 0.0, "units": 0,
                "new_customers": 0, "returning_customers": 0,
                "product_breakdown": {}, "category_breakdown": {},
            }

        d = daily[day]
        revenue = float(order.get("totalPriceSet", {}).get("shopMoney", {}).get("amount", 0))
        d["orders"] += 1
        d["revenue"] += revenue

        customer = order.get("customer") or {}
        if customer.get("numberOfOrders", 0) <= 1:
            d["new_customers"] += 1
        else:
            d["returning_customers"] += 1

        for li_edge in order.get("lineItems", {}).get("edges", []):
            li = li_edge["node"]
            qty = li.get("quantity", 0)
            d["units"] += qty
            sku = li.get("sku") or "unknown"
            unit_price = float(li.get("originalUnitPriceSet", {}).get("shopMoney", {}).get("amount", 0))
            li_rev = unit_price * qty

            if sku not in d["product_breakdown"]:
                d["product_breakdown"][sku] = {"units": 0, "revenue": 0}
            d["product_breakdown"][sku]["units"] += qty
            d["product_breakdown"][sku]["revenue"] += li_rev

    created = 0
    updated = 0

    for day, d in daily.items():
        aov = d["revenue"] / d["orders"] if d["orders"] > 0 else 0

        existing = db.query(SalesSnapshot).filter(
            SalesSnapshot.snapshot_date == day
        ).first()

        if existing:
            existing.total_orders = d["orders"]
            existing.total_revenue = d["revenue"]
            existing.total_units = d["units"]
            existing.average_order_value = aov
            existing.new_customers = d["new_customers"]
            existing.returning_customers = d["returning_customers"]
            existing.product_breakdown = d["product_breakdown"]
            updated += 1
        else:
            snapshot = SalesSnapshot(
                snapshot_date=day,
                total_orders=d["orders"],
                total_revenue=d["revenue"],
                total_units=d["units"],
                average_order_value=aov,
                new_customers=d["new_customers"],
                returning_customers=d["returning_customers"],
                product_breakdown=d["product_breakdown"],
            )
            db.add(snapshot)
            created += 1

    db.commit()
    return created, updated


def _update_product_performance(orders: list, db: Session):
    """Update ProductPerformance records from order data."""
    product_agg = {}

    for order in orders:
        for li_edge in order.get("lineItems", {}).get("edges", []):
            li = li_edge["node"]
            sku = li.get("sku") or "unknown"
            qty = li.get("quantity", 0)
            unit_price = float(li.get("originalUnitPriceSet", {}).get("shopMoney", {}).get("amount", 0))
            product_id = None
            variant = li.get("variant") or {}
            product = variant.get("product") or {}
            product_id = product.get("id")

            if sku not in product_agg:
                product_agg[sku] = {
                    "name": li.get("name", ""),
                    "shopify_product_id": product_id,
                    "units": 0,
                    "revenue": 0.0,
                }
            product_agg[sku]["units"] += qty
            product_agg[sku]["revenue"] += unit_price * qty

    updated_count = 0
    for sku, data in product_agg.items():
        existing = db.query(ProductPerformance).filter(
            ProductPerformance.sku == sku
        ).first()

        if existing:
            existing.units_sold_30d = data["units"]
            existing.revenue_30d = data["revenue"]
            existing.units_sold_lifetime = (existing.units_sold_lifetime or 0) + data["units"]
            existing.revenue_lifetime = (existing.revenue_lifetime or 0) + data["revenue"]
            existing.last_updated = datetime.utcnow()
        else:
            perf = ProductPerformance(
                sku=sku,
                product_name=data["name"],
                shopify_product_id=data.get("shopify_product_id"),
                units_sold_30d=data["units"],
                revenue_30d=data["revenue"],
                units_sold_lifetime=data["units"],
                revenue_lifetime=data["revenue"],
                first_sale_date=datetime.utcnow(),
                last_updated=datetime.utcnow(),
            )
            db.add(perf)
        updated_count += 1

    db.commit()
    return updated_count


@router.get("/cdo/sync/status", tags=["Sync"])
async def sync_status(db: Session = Depends(get_db)):
    """Return age and freshness of latest ProductPerformance data."""
    latest = db.query(ProductPerformance).order_by(
        ProductPerformance.last_updated.desc().nullslast()
    ).first()

    if not latest or not latest.last_updated:
        return {
            "has_data": False,
            "last_updated": None,
            "age_hours": None,
            "is_fresh": False,
            "record_count": 0,
        }

    age = datetime.utcnow() - latest.last_updated
    age_hours = age.total_seconds() / 3600
    record_count = db.query(ProductPerformance).count()

    return {
        "has_data": True,
        "last_updated": latest.last_updated.isoformat(),
        "age_hours": round(age_hours, 1),
        "is_fresh": age_hours < 168,  # < 7 days
        "record_count": record_count,
    }


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

    token = auth.access_token or settings.shopify_access_token
    if not token:
        raise HTTPException(status_code=400, detail="No Shopify access token available")

    try:
        orders = await _fetch_shopify_orders(token, days)
    except Exception as e:
        logger.error(f"Failed to fetch Shopify orders: {e}")
        raise HTTPException(status_code=502, detail=f"Shopify API error: {str(e)}")

    if not orders:
        return {
            "success": True,
            "orders_fetched": 0,
            "snapshots_created": 0,
            "snapshots_updated": 0,
            "products_updated": 0,
            "message": f"No orders found in last {days} days"
        }

    snapshots_created, snapshots_updated = _aggregate_daily_snapshots(orders, db)
    products_updated = _update_product_performance(orders, db)

    return {
        "success": True,
        "orders_fetched": len(orders),
        "snapshots_created": snapshots_created,
        "snapshots_updated": snapshots_updated,
        "products_updated": products_updated,
        "message": f"Synced {len(orders)} orders from last {days} days"
    }
