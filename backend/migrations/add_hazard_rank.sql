-- Migration: Add hazard rank framework columns
-- Run this on existing databases to add the new columns.

-- Create enum types
DO $$ BEGIN
    CREATE TYPE hazardrank AS ENUM ('R1','R2','R3','R4','R5','R6','R7','R8','R9','R10','R11','R12','NG');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Add hazard rank columns to risk_scores
ALTER TABLE risk_scores ADD COLUMN IF NOT EXISTS hazard_rank hazardrank;
ALTER TABLE risk_scores ADD COLUMN IF NOT EXISTS aware_tier VARCHAR(10);
ALTER TABLE risk_scores ADD COLUMN IF NOT EXISTS transmissibility_level INTEGER;
ALTER TABLE risk_scores ADD COLUMN IF NOT EXISTS worst_case_arg VARCHAR(255);
ALTER TABLE risk_scores ADD COLUMN IF NOT EXISTS worst_case_drug_class VARCHAR(255);
ALTER TABLE risk_scores ADD COLUMN IF NOT EXISTS worst_case_location VARCHAR(100);
ALTER TABLE risk_scores ADD COLUMN IF NOT EXISTS mdr_flag BOOLEAN DEFAULT FALSE;
ALTER TABLE risk_scores ADD COLUMN IF NOT EXISTS drug_class_count INTEGER;
ALTER TABLE risk_scores ADD COLUMN IF NOT EXISTS vf_category_count INTEGER;

-- Add host range columns to plasmid_results
ALTER TABLE plasmid_results ADD COLUMN IF NOT EXISTS mash_neighbor_identification VARCHAR(255);
ALTER TABLE plasmid_results ADD COLUMN IF NOT EXISTS mash_neighbor_distance FLOAT;
