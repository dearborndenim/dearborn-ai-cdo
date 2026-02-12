# CLAUDE.md - Dearborn AI CDO Module

Product development: tech packs, patterns, trends, product ideas, seasonal collections, and pipeline management.

## Architecture

- **Framework:** FastAPI (Python)
- **Database:** PostgreSQL (schema: `cdo`)
- **Event Bus:** Redis pub/sub (sync, threading-based)
- **AI:** OpenAI GPT-4o for research/ideas, DALL-E 3 for concepts
- **Port:** 8004 (configurable via `PORT`)
- **Deploy:** Railway

## API Endpoints

### Health
- `GET /health` - Health check (DB, Redis, Shopify status)

### Dashboard
- `GET /cdo/dashboard` - Product development overview

### Tech Packs (`/cdo/tech-packs`)
- `GET /cdo/tech-packs` - List tech packs (filter: `?status=draft`)
- `POST /cdo/tech-packs` - Create tech pack
- `GET /cdo/tech-packs/{id}` - Detail with measurements, materials, operations
- `POST /cdo/tech-packs/{id}/generate` - AI-generate tech pack from description
- `GET /cdo/tech-packs/{id}/pdf` - Download tech pack as PDF

### Patterns (`/cdo/patterns`)
- `GET /cdo/patterns` - List pattern files
- `POST /cdo/patterns` - Upload/create pattern
- `GET /cdo/patterns/{id}` - Pattern detail
- `POST /cdo/patterns/{id}/generate-dxf` - Generate DXF pattern file

### Product Ideas (`/cdo/product-ideas`)
- `GET /cdo/product-ideas` - List ideas with scoring
- `POST /cdo/product-ideas` - Create idea
- `GET /cdo/product-ideas/{id}` - Idea detail

### Trends / Discovery (`/cdo/trends`)
- `GET /cdo/trends` - List discovered trends
- `POST /cdo/trends/scan` - Trigger trend discovery scan

### Seasonal Collections (`/cdo/seasons`)
- `GET /cdo/seasons` - List seasons
- `POST /cdo/seasons` - Create season with target demo
- `GET /cdo/seasons/{id}` - Season detail with ideas
- `POST /cdo/seasons/{id}/research` - AI customer research
- `POST /cdo/seasons/{id}/generate-ideas` - AI product ideation
- `POST /cdo/seasons/{id}/ideas/{idea_id}/promote` - Promote idea to pipeline

### Pipeline (`/cdo/pipeline`)
- `GET /cdo/pipeline` - Full pipeline (DISCOVERY through COMPLETE)
- `POST /cdo/pipeline` - Create pipeline item
- `PUT /cdo/pipeline/{id}` - Update pipeline item
- `POST /cdo/pipeline/{id}/advance` - Advance stage
- `POST /cdo/pipeline/{id}/validate` - Trigger cross-module validation

### Shopify Sync (`/cdo/sync`)
- `POST /cdo/sync/orders` - Sync Shopify orders via GraphQL

### Reports (`/cdo/reports`)
- `POST /cdo/reports` - Generate report (types: sales, product, inventory, customer, financial, cross_module)
- `GET /cdo/reports` - List reports

### Alerts (`/cdo/alerts`)
- `GET /cdo/alerts` - List alerts (filter: `?severity=high`)
- `POST /cdo/alerts` - Create alert
- `GET /cdo/alerts/{id}` - Alert detail
- `POST /cdo/alerts/{id}/resolve` - Resolve alert
- `DELETE /cdo/alerts/{id}` - Delete alert

### Analytics (`/cdo/analytics`)
- `GET /cdo/analytics` - Product analytics

## Event Bus

### Publishes:
| Event | Target | Trigger |
|-------|--------|---------|
| `trend_alert` | CEO | High-scoring trend detected |
| `product_recommendation` | CEO | Product idea ready for approval |
| `tech_pack_ready` | COO | Tech pack finalized |
| `demand_forecast` | COO | Sales forecast generated |
| `margin_check_request` | CFO | Request margin validation |
| `capacity_check_request` | COO | Request production capacity check |

### Subscribes to:
| Event | Source | Action |
|-------|--------|--------|
| `approval_decided` | CEO | Creates CDOAlert |
| `sales_data_updated` | (none yet) | Triggers analytics refresh |
| `inventory_updated` | COO | Creates inventory alert |
| `campaign_performance` | CMO | Creates performance alert |
| `financial_report` | CFO | Creates financial alert |
| `margin_check_response` | CFO | Updates validation status |
| `capacity_check_response` | COO | Updates validation status |

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `postgresql://localhost:5432/dearborn` | PostgreSQL |
| `REDIS_URL` | Yes | `redis://localhost:6379` | Redis event bus |
| `PORT` | No | 8004 | Server port |
| `ALLOWED_ORIGINS` | No | `""` | CORS origins |
| `OPENAI_API_KEY` | Yes | | OpenAI for AI features |
| `SHOPIFY_STORE` | No | `dearborndenim.myshopify.com` | Shopify store |
| `SHOPIFY_ACCESS_TOKEN` | No | | Shopify API token |
| `CEO_API_URL` | No | `""` | CEO HTTP fallback |
| `CFO_API_URL` | No | `""` | CFO HTTP fallback |
| `COO_API_URL` | No | `""` | COO HTTP fallback |
| `CMO_API_URL` | No | `""` | CMO webhook delivery |
| `ONEDRIVE_CLIENT_ID` | No | | OneDrive integration |
| `ONEDRIVE_CLIENT_SECRET` | No | | OneDrive integration |
| `ONEDRIVE_TENANT_ID` | No | | OneDrive integration |

## File Structure

```
src/
  config.py          - Pydantic settings
  db.py              - SQLAlchemy models (TechPack, Pattern, ProductIdea, Season, etc.)
  event_bus.py       - Redis pub/sub + HTTP fallback (threading)
  server.py          - FastAPI app + lifespan
  cdo/               - Core business logic
    techpack_gen.py  - AI tech pack generation
    pattern_gen.py   - DXF pattern generation (ezdxf)
    discovery.py     - Trend discovery
    concept.py       - Concept generation
    validation.py    - Cross-module validation orchestrator
    pipeline.py      - Pipeline state management
  routes/            - FastAPI route modules (13 files)
    health.py, dashboard.py, tech_packs.py, patterns.py,
    trends.py, product_ideas.py, pipeline.py, seasonal.py,
    shopify.py, reports.py, alerts.py, analytics.py, events.py
```
