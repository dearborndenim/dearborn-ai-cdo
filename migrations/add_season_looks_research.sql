-- Migration: Add season_looks, season_research tables and new columns on season_product_ideas
-- Date: 2026-02-12

-- Season Research table (structured research replacing single text blob)
CREATE TABLE IF NOT EXISTS cdo.season_research (
    id SERIAL PRIMARY KEY,
    season_id INTEGER NOT NULL REFERENCES cdo.seasons(id),
    research_type VARCHAR(50) NOT NULL,
    content TEXT,
    citations JSONB,
    source VARCHAR(50),
    model_used VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_season_research_season_id ON cdo.season_research(season_id);

-- Season Looks table (coordinated outfits)
CREATE TABLE IF NOT EXISTS cdo.season_looks (
    id SERIAL PRIMARY KEY,
    season_id INTEGER NOT NULL REFERENCES cdo.seasons(id),
    look_number INTEGER NOT NULL,
    name VARCHAR(255),
    theme TEXT,
    occasion VARCHAR(255),
    styling_notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(season_id, look_number)
);

CREATE INDEX IF NOT EXISTS idx_season_looks_season_id ON cdo.season_looks(season_id);

-- New columns on season_product_ideas
ALTER TABLE cdo.season_product_ideas ADD COLUMN IF NOT EXISTS look_id INTEGER REFERENCES cdo.season_looks(id);
ALTER TABLE cdo.season_product_ideas ADD COLUMN IF NOT EXISTS style VARCHAR(100);
ALTER TABLE cdo.season_product_ideas ADD COLUMN IF NOT EXISTS fabric_recommendation VARCHAR(255);
ALTER TABLE cdo.season_product_ideas ADD COLUMN IF NOT EXISTS fabric_weight VARCHAR(50);
ALTER TABLE cdo.season_product_ideas ADD COLUMN IF NOT EXISTS fabric_weave VARCHAR(50);
ALTER TABLE cdo.season_product_ideas ADD COLUMN IF NOT EXISTS fabric_composition VARCHAR(255);
ALTER TABLE cdo.season_product_ideas ADD COLUMN IF NOT EXISTS fabric_type VARCHAR(50);
ALTER TABLE cdo.season_product_ideas ADD COLUMN IF NOT EXISTS colorway JSONB;
ALTER TABLE cdo.season_product_ideas ADD COLUMN IF NOT EXISTS sourced_externally BOOLEAN DEFAULT FALSE;
ALTER TABLE cdo.season_product_ideas ADD COLUMN IF NOT EXISTS trend_citations JSONB;
ALTER TABLE cdo.season_product_ideas ADD COLUMN IF NOT EXISTS suggested_vendors JSONB;

CREATE INDEX IF NOT EXISTS idx_season_product_ideas_look_id ON cdo.season_product_ideas(look_id);
