-- Add estimated_minutes column to tech_pack_construction table
-- Run this migration if the column doesn't exist yet

ALTER TABLE cdo.tech_pack_construction
ADD COLUMN IF NOT EXISTS estimated_minutes INTEGER;

-- Optional: Update existing records with default values based on operation type
-- This is optional since NULL is acceptable for existing records
