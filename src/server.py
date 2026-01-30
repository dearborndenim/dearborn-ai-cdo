"""
Dearborn AI CDO Module - FastAPI Server

Chief Data Officer: Analytics, Tech Packs, Pattern Files, Product Development
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .event_bus import event_bus
from .routes import health, dashboard, tech_packs, patterns, product_ideas
from .routes import trends, analytics, reports, shopify, events, alerts

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    logger.info("Starting Dearborn AI CDO Module...")

    try:
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

    logger.info("CDO Module startup complete")
    yield

    logger.info("Shutting down CDO Module...")
    event_bus.disconnect()


app = FastAPI(
    title="Dearborn AI CDO",
    description="""
    Chief Data Officer Module for Dearborn Denim AI

    ## Features
    - **Analytics**: Sales, customer, and product performance analytics
    - **Tech Packs**: Technical package creation and management
    - **Pattern Files**: DXF/AAMA pattern file generation
    - **Product Development**: AI-powered product recommendations
    - **Reports**: Automated reporting and insights
    - **Trend Analysis**: Market and fashion trend tracking
    """,
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include route modules
app.include_router(health.router)
app.include_router(dashboard.router)
app.include_router(tech_packs.router)
app.include_router(patterns.router)
app.include_router(product_ideas.router)
app.include_router(trends.router)
app.include_router(analytics.router)
app.include_router(reports.router)
app.include_router(shopify.router)
app.include_router(events.router)
app.include_router(alerts.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
