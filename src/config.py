"""
Configuration for CDO Module
"""
import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """CDO module settings from environment variables."""

    # Database
    database_url: str = os.getenv("DATABASE_URL", "postgresql://localhost:5432/dearborn")

    # Redis for event bus
    redis_url: str = os.getenv("REDIS_URL", "")

    # Module identification
    module_name: str = "cdo"

    # This module's public URL (for OAuth callbacks)
    cdo_api_url: str = os.getenv("CDO_API_URL", "")

    # Other module URLs
    ceo_api_url: str = os.getenv("CEO_API_URL", "")
    cfo_api_url: str = os.getenv("CFO_API_URL", "")
    cmo_api_url: str = os.getenv("CMO_API_URL", "")
    coo_api_url: str = os.getenv("COO_API_URL", "")

    # Shopify for sales/customer data
    shopify_store: str = os.getenv("SHOPIFY_STORE", "dearborndenim.myshopify.com")
    shopify_client_id: str = os.getenv("SHOPIFY_CLIENT_ID", "")
    shopify_client_secret: str = os.getenv("SHOPIFY_CLIENT_SECRET", "")
    shopify_access_token: str = os.getenv("SHOPIFY_ACCESS_TOKEN", "")

    # Perplexity for web-grounded trend research
    perplexity_api_key: str = os.getenv("PERPLEXITY_API_KEY", "")

    # OpenAI for product recommendations and tech pack generation
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    dall_e_model: str = os.getenv("DALL_E_MODEL", "dall-e-3")

    # Microsoft OneDrive for file storage (patterns, sketches, tech packs)
    onedrive_client_id: str = os.getenv("ONEDRIVE_CLIENT_ID", "")
    onedrive_client_secret: str = os.getenv("ONEDRIVE_CLIENT_SECRET", "")
    onedrive_tenant_id: str = os.getenv("ONEDRIVE_TENANT_ID", "")
    onedrive_user_id: str = os.getenv("ONEDRIVE_USER_ID", "")
    onedrive_folder_path: str = os.getenv("ONEDRIVE_FOLDER_PATH", "Dearborn AI/CDO")

    # Scheduler
    discovery_cron: str = os.getenv("DISCOVERY_CRON", "0 6 * * 1")

    # App settings
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    class Config:
        env_file = ".env"
        extra = "allow"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
