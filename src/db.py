"""
Database models for CDO Module

Handles:
- Analytics aggregation
- Tech packs
- Pattern files (DXF/AAMA)
- Product development
- Reports
"""
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional, List
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean,
    DateTime, Text, ForeignKey, JSON, Enum, UniqueConstraint, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

from .config import get_settings

settings = get_settings()

CDO_SCHEMA = "cdo"

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args={"options": f"-csearch_path={CDO_SCHEMA},public"}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ============== Enums ==============

class ReportType(str, PyEnum):
    SALES = "sales"
    INVENTORY = "inventory"
    CUSTOMER = "customer"
    PRODUCT = "product"
    FINANCIAL = "financial"
    CROSS_MODULE = "cross_module"


class ReportFrequency(str, PyEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ON_DEMAND = "on_demand"


class TechPackStatus(str, PyEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    IN_PRODUCTION = "in_production"
    ARCHIVED = "archived"


class PatternStatus(str, PyEnum):
    DRAFT = "draft"
    GRADED = "graded"
    APPROVED = "approved"
    IN_PRODUCTION = "in_production"


class ProductIdeaStatus(str, PyEnum):
    CONCEPT = "concept"
    RESEARCH = "research"
    APPROVED = "approved"
    IN_DEVELOPMENT = "in_development"
    LAUNCHED = "launched"
    REJECTED = "rejected"


class AlertSeverity(str, PyEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# ============== Analytics Models ==============

class SalesSnapshot(Base):
    """Daily sales snapshot for trend analysis."""
    __tablename__ = "sales_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    snapshot_date = Column(DateTime, nullable=False, index=True)

    # Sales metrics
    total_orders = Column(Integer, default=0)
    total_revenue = Column(Float, default=0)
    total_units = Column(Integer, default=0)
    average_order_value = Column(Float, default=0)

    # Channel breakdown
    online_revenue = Column(Float, default=0)
    wholesale_revenue = Column(Float, default=0)
    retail_revenue = Column(Float, default=0)

    # Customer metrics
    new_customers = Column(Integer, default=0)
    returning_customers = Column(Integer, default=0)

    # Product breakdown (JSON for flexibility)
    product_breakdown = Column(JSON)  # {sku: {units, revenue}, ...}
    category_breakdown = Column(JSON)  # {category: {units, revenue}, ...}

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('snapshot_date', name='uq_sales_snapshot_date'),
        {'schema': CDO_SCHEMA}
    )


class ProductPerformance(Base):
    """Product-level performance tracking."""
    __tablename__ = "product_performance"

    id = Column(Integer, primary_key=True, index=True)
    shopify_product_id = Column(String(100), index=True)
    sku = Column(String(100), index=True)
    product_name = Column(String(255))

    # Performance metrics (rolling 30 days)
    units_sold_30d = Column(Integer, default=0)
    revenue_30d = Column(Float, default=0)
    return_rate_30d = Column(Float, default=0)

    # Lifetime metrics
    units_sold_lifetime = Column(Integer, default=0)
    revenue_lifetime = Column(Float, default=0)
    first_sale_date = Column(DateTime)

    # Inventory velocity
    days_of_stock = Column(Float)  # At current sell rate
    sell_through_rate = Column(Float)  # % of inventory sold

    # Calculated scores
    performance_score = Column(Float)  # 0-100 composite score
    trend_direction = Column(String(20))  # up, down, stable

    last_updated = Column(DateTime, default=datetime.utcnow)

    __table_args__ = ({'schema': CDO_SCHEMA},)


class CustomerSegment(Base):
    """Customer segmentation for analytics."""
    __tablename__ = "customer_segments"

    id = Column(Integer, primary_key=True, index=True)
    segment_name = Column(String(100), unique=True)
    description = Column(Text)

    # Segment criteria (JSON for flexibility)
    criteria = Column(JSON)  # {min_orders: 3, min_ltv: 500, ...}

    # Current segment stats
    customer_count = Column(Integer, default=0)
    total_ltv = Column(Float, default=0)
    average_order_frequency = Column(Float, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = ({'schema': CDO_SCHEMA},)


class CustomerAnalytics(Base):
    """Individual customer analytics record."""
    __tablename__ = "customer_analytics"

    id = Column(Integer, primary_key=True, index=True)
    shopify_customer_id = Column(String(100), unique=True, index=True)
    email = Column(String(255), index=True)

    # Purchase history
    first_order_date = Column(DateTime)
    last_order_date = Column(DateTime)
    total_orders = Column(Integer, default=0)
    total_spent = Column(Float, default=0)
    average_order_value = Column(Float, default=0)

    # Behavioral
    preferred_categories = Column(JSON)  # [{category, count, revenue}, ...]
    preferred_sizes = Column(JSON)  # [{size, count}, ...]
    preferred_fits = Column(JSON)  # [{fit, count}, ...]

    # Calculated
    lifetime_value = Column(Float, default=0)
    predicted_next_order_date = Column(DateTime)
    churn_risk_score = Column(Float)  # 0-1

    segment_id = Column(Integer, ForeignKey(f'{CDO_SCHEMA}.customer_segments.id'))
    segment = relationship("CustomerSegment")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = ({'schema': CDO_SCHEMA},)


# ============== Tech Pack Models ==============

class TechPack(Base):
    """Technical package for garment manufacturing."""
    __tablename__ = "tech_packs"

    id = Column(Integer, primary_key=True, index=True)
    tech_pack_number = Column(String(50), unique=True, index=True)

    # Product info
    style_name = Column(String(255), nullable=False)
    style_number = Column(String(100))
    category = Column(String(100))  # jeans, jacket, shirt, etc.
    season = Column(String(50))  # F24, S25, etc.

    # Design details
    description = Column(Text)
    design_notes = Column(Text)
    inspiration = Column(Text)
    target_customer = Column(String(255))

    # Fit info
    fit_type = Column(String(100))  # slim, relaxed, athletic, etc.
    rise = Column(String(50))  # low, mid, high
    leg_opening = Column(String(50))  # skinny, tapered, straight, bootcut

    # Fabric
    primary_fabric = Column(String(255))
    fabric_weight = Column(String(50))  # oz/yd or gsm
    fabric_content = Column(String(255))  # 98% cotton, 2% elastane
    fabric_supplier = Column(String(255))

    # Pricing
    target_cost = Column(Float)
    target_retail = Column(Float)
    target_margin = Column(Float)

    # Status
    status = Column(Enum(TechPackStatus), default=TechPackStatus.DRAFT)
    created_by = Column(String(100))
    approved_by = Column(String(100))
    approved_date = Column(DateTime)

    # AI generation metadata
    ai_generated = Column(Boolean, default=False)
    ai_prompt = Column(Text)
    ai_model = Column(String(100))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    measurements = relationship("TechPackMeasurement", back_populates="tech_pack", cascade="all, delete-orphan")
    materials = relationship("TechPackMaterial", back_populates="tech_pack", cascade="all, delete-orphan")
    construction = relationship("TechPackConstruction", back_populates="tech_pack", cascade="all, delete-orphan")
    patterns = relationship("PatternFile", back_populates="tech_pack")

    __table_args__ = ({'schema': CDO_SCHEMA},)


class TechPackMeasurement(Base):
    """Size specifications for tech pack."""
    __tablename__ = "tech_pack_measurements"

    id = Column(Integer, primary_key=True, index=True)
    tech_pack_id = Column(Integer, ForeignKey(f'{CDO_SCHEMA}.tech_packs.id'), nullable=False)

    size = Column(String(20), nullable=False)  # 28, 30, 32, S, M, L, etc.

    # Common measurements (in inches)
    waist = Column(Float)
    front_rise = Column(Float)
    back_rise = Column(Float)
    hip = Column(Float)
    thigh = Column(Float)
    knee = Column(Float)
    leg_opening = Column(Float)
    inseam = Column(Float)
    outseam = Column(Float)

    # Additional measurements (JSON for flexibility)
    additional_measurements = Column(JSON)  # {yoke_depth: 3.5, pocket_placement: {...}}

    # Tolerances
    tolerance_plus = Column(Float, default=0.25)
    tolerance_minus = Column(Float, default=0.25)

    tech_pack = relationship("TechPack", back_populates="measurements")

    __table_args__ = (
        UniqueConstraint('tech_pack_id', 'size', name='uq_techpack_size'),
        {'schema': CDO_SCHEMA}
    )


class TechPackMaterial(Base):
    """Bill of materials for tech pack."""
    __tablename__ = "tech_pack_materials"

    id = Column(Integer, primary_key=True, index=True)
    tech_pack_id = Column(Integer, ForeignKey(f'{CDO_SCHEMA}.tech_packs.id'), nullable=False)

    material_type = Column(String(100), nullable=False)  # fabric, trim, thread, label, etc.
    material_name = Column(String(255), nullable=False)
    supplier = Column(String(255))
    supplier_code = Column(String(100))

    color = Column(String(100))
    color_code = Column(String(50))

    # Usage
    placement = Column(String(255))  # where it's used
    quantity_per_unit = Column(Float)  # yards, pieces, etc.
    unit_of_measure = Column(String(50))

    # Cost
    unit_cost = Column(Float)

    notes = Column(Text)

    tech_pack = relationship("TechPack", back_populates="materials")

    __table_args__ = ({'schema': CDO_SCHEMA},)


class TechPackConstruction(Base):
    """Construction details and operations."""
    __tablename__ = "tech_pack_construction"

    id = Column(Integer, primary_key=True, index=True)
    tech_pack_id = Column(Integer, ForeignKey(f'{CDO_SCHEMA}.tech_packs.id'), nullable=False)

    operation_number = Column(Integer, nullable=False)
    operation_name = Column(String(255), nullable=False)
    description = Column(Text)

    # Machine/method
    machine_type = Column(String(100))  # single needle, serger, coverstitch, etc.
    stitch_type = Column(String(100))  # 301, 401, 504, etc.
    stitches_per_inch = Column(Float)

    # Thread
    thread_type = Column(String(100))
    thread_color = Column(String(100))

    # Quality
    seam_allowance = Column(Float)
    topstitch_width = Column(Float)

    notes = Column(Text)
    diagram_url = Column(String(500))  # Link to construction diagram

    tech_pack = relationship("TechPack", back_populates="construction")

    __table_args__ = (
        UniqueConstraint('tech_pack_id', 'operation_number', name='uq_techpack_operation'),
        {'schema': CDO_SCHEMA}
    )


# ============== Pattern File Models ==============

class PatternFile(Base):
    """DXF/AAMA pattern file record."""
    __tablename__ = "pattern_files"

    id = Column(Integer, primary_key=True, index=True)
    tech_pack_id = Column(Integer, ForeignKey(f'{CDO_SCHEMA}.tech_packs.id'))

    file_name = Column(String(255), nullable=False)
    file_type = Column(String(20), nullable=False)  # dxf, aama, pdf
    file_path = Column(String(500))  # Storage path (S3, etc.)
    file_size = Column(Integer)  # bytes

    # Pattern info
    version = Column(String(20), default="1.0")
    base_size = Column(String(20))  # The size the pattern is graded from
    sizes_included = Column(JSON)  # ["28", "30", "32", "34", "36", "38"]

    # Metadata
    total_pieces = Column(Integer)
    marker_length = Column(Float)  # yards
    marker_width = Column(Float)  # inches
    fabric_utilization = Column(Float)  # percentage

    status = Column(Enum(PatternStatus), default=PatternStatus.DRAFT)

    # AI generation
    ai_generated = Column(Boolean, default=False)
    requires_human_review = Column(Boolean, default=True)
    review_notes = Column(Text)
    reviewed_by = Column(String(100))
    reviewed_date = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tech_pack = relationship("TechPack", back_populates="patterns")
    pieces = relationship("PatternPiece", back_populates="pattern_file", cascade="all, delete-orphan")

    __table_args__ = ({'schema': CDO_SCHEMA},)


class PatternPiece(Base):
    """Individual pattern piece within a pattern file."""
    __tablename__ = "pattern_pieces"

    id = Column(Integer, primary_key=True, index=True)
    pattern_file_id = Column(Integer, ForeignKey(f'{CDO_SCHEMA}.pattern_files.id'), nullable=False)

    piece_name = Column(String(100), nullable=False)  # front_panel, back_panel, waistband, etc.
    piece_code = Column(String(50))  # FP, BP, WB, etc.

    # Cutting info
    fabric_type = Column(String(100))  # shell, lining, interlining
    cut_quantity = Column(Integer, default=1)  # per garment
    grain_line = Column(String(50))  # straight, bias, cross
    mirror = Column(Boolean, default=False)  # cut on fold or mirror

    # Size info (for graded patterns)
    size_measurements = Column(JSON)  # {size: {length, width, area}, ...}

    notes = Column(Text)

    pattern_file = relationship("PatternFile", back_populates="pieces")

    __table_args__ = ({'schema': CDO_SCHEMA},)


# ============== Product Development Models ==============

class ProductIdea(Base):
    """Product development ideas and recommendations."""
    __tablename__ = "product_ideas"

    id = Column(Integer, primary_key=True, index=True)
    idea_number = Column(String(50), unique=True, index=True)

    title = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(100))

    # Source of idea
    source = Column(String(100))  # ai_recommendation, trend_analysis, customer_feedback, internal
    source_data = Column(JSON)  # Supporting data/analysis

    # Market analysis
    target_market = Column(String(255))
    market_size_estimate = Column(Float)
    competition_analysis = Column(Text)

    # Financial projections
    estimated_cost = Column(Float)
    estimated_retail = Column(Float)
    estimated_margin = Column(Float)
    estimated_annual_units = Column(Integer)
    estimated_annual_revenue = Column(Float)

    # Priority and scoring
    priority_score = Column(Float)  # AI-calculated priority
    trend_alignment_score = Column(Float)
    margin_score = Column(Float)
    feasibility_score = Column(Float)

    status = Column(Enum(ProductIdeaStatus), default=ProductIdeaStatus.CONCEPT)

    # Approval
    approved_by = Column(String(100))
    approved_date = Column(DateTime)
    rejection_reason = Column(Text)

    # Links
    tech_pack_id = Column(Integer, ForeignKey(f'{CDO_SCHEMA}.tech_packs.id'))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = ({'schema': CDO_SCHEMA},)


class TrendAnalysis(Base):
    """Market and fashion trend tracking."""
    __tablename__ = "trend_analysis"

    id = Column(Integer, primary_key=True, index=True)

    trend_name = Column(String(255), nullable=False)
    category = Column(String(100))  # denim, fashion, consumer, sustainability

    description = Column(Text)

    # Trend metrics
    trend_score = Column(Float)  # 0-100 strength score
    growth_rate = Column(Float)  # % change
    peak_forecast = Column(DateTime)  # When trend expected to peak

    # Sources
    data_sources = Column(JSON)  # [{source, url, date}, ...]
    keywords = Column(JSON)  # ["raw denim", "selvedge", ...]

    # Relevance to Dearborn
    relevance_score = Column(Float)
    recommended_actions = Column(JSON)  # [{action, priority}, ...]

    # AI analysis
    ai_analysis = Column(Text)
    ai_confidence = Column(Float)

    analysis_date = Column(DateTime, default=datetime.utcnow)
    next_analysis_date = Column(DateTime)

    __table_args__ = ({'schema': CDO_SCHEMA},)


# ============== Report Models ==============

class Report(Base):
    """Generated reports."""
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    report_number = Column(String(50), unique=True, index=True)

    title = Column(String(255), nullable=False)
    report_type = Column(Enum(ReportType), nullable=False)

    # Date range
    period_start = Column(DateTime)
    period_end = Column(DateTime)

    # Content
    summary = Column(Text)
    data = Column(JSON)  # Full report data
    insights = Column(JSON)  # AI-generated insights
    recommendations = Column(JSON)  # AI-generated recommendations

    # File
    file_path = Column(String(500))  # PDF/Excel export path
    file_type = Column(String(20))

    # Metadata
    generated_by = Column(String(100))  # user or "system"
    generation_time_seconds = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = ({'schema': CDO_SCHEMA},)


class ReportSchedule(Base):
    """Scheduled report generation."""
    __tablename__ = "report_schedules"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(255), nullable=False)
    report_type = Column(Enum(ReportType), nullable=False)
    frequency = Column(Enum(ReportFrequency), nullable=False)

    # Recipients
    recipients = Column(JSON)  # [{email, name}, ...]
    slack_channel = Column(String(100))

    # Config
    config = Column(JSON)  # Report-specific config

    is_active = Column(Boolean, default=True)
    last_run = Column(DateTime)
    next_run = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = ({'schema': CDO_SCHEMA},)


# ============== Alerts & Events ==============

class CDOAlert(Base):
    """CDO module alerts."""
    __tablename__ = "cdo_alerts"

    id = Column(Integer, primary_key=True, index=True)
    severity = Column(Enum(AlertSeverity), default=AlertSeverity.INFO)
    category = Column(String(100), nullable=False)  # trend, performance, tech_pack, etc.

    title = Column(String(255), nullable=False)
    message = Column(Text)

    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime)
    resolved_by = Column(String(100))

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = ({'schema': CDO_SCHEMA},)


class CDOEvent(Base):
    """Event bus audit trail."""
    __tablename__ = "cdo_events"

    id = Column(Integer, primary_key=True, index=True)
    direction = Column(String(20))  # inbound, outbound
    other_module = Column(String(50))
    event_type = Column(String(100))
    payload = Column(JSON)
    status = Column(String(50))

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = ({'schema': CDO_SCHEMA},)


# ============== Shopify Auth ==============

class ShopifyAuth(Base):
    """Stored Shopify OAuth tokens."""
    __tablename__ = "shopify_auth"

    id = Column(Integer, primary_key=True, index=True)
    store = Column(String(255), unique=True, nullable=False)
    access_token = Column(String(500), nullable=False)
    scope = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = ({'schema': CDO_SCHEMA},)


# ============== Database Initialization ==============

def init_db():
    """Create all tables."""
    # Create schema first
    with engine.connect() as conn:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {CDO_SCHEMA}")
        conn.commit()

    # Create tables
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency for FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
