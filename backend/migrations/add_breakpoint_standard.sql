ALTER TABLE breakpoints ADD COLUMN IF NOT EXISTS standard VARCHAR(32);
-- existing rows were all seeded from the APQA monitoring panel
UPDATE breakpoints SET standard = 'APQA' WHERE standard IS NULL;
CREATE INDEX IF NOT EXISTS ix_breakpoints_lookup ON breakpoints (lower(antibiotic), lower(standard));
