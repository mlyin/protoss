-- A legion can be backed by a Hyperliquid vault: the non-custodial pool.
ALTER TABLE orgs ADD COLUMN IF NOT EXISTS hl_vault VARCHAR(42);
