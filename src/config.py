"""
Configuration for CDO Module
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """CDO module settings from environment variables."""

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/dearborn"

    # Redis for event bus
    redis_url: str = ""

    # This module's public URL (for OAuth callbacks)
    cdo_api_url: str = ""

    # Other module URLs (for data aggregation)
    ceo_api_url: str = ""
    cfo_api_url: str = ""
    cmo_api_url: str = ""
    coo_api_url: str = ""

    # Shopify for sales/customer data
    shopify_store: str = "dearborndenim.myshopify.com"
    shopify_client_id: str = ""
    shopify_client_secret: str = ""
    shopify_access_token: str = ""

    # OpenAI for product recommendations and tech pack generation
    openai_api_key: str = ""

    # App settings
    debug: bool = False
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
