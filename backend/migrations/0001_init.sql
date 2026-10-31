-- Protoss schema (generated from SQLAlchemy models for PostgreSQL / Supabase)
-- apply once; the app also runs create_all on startup, which is a no-op when tables exist

CREATE TABLE IF NOT EXISTS orgs (
	id VARCHAR(32) NOT NULL, 
	slug VARCHAR(48) NOT NULL, 
	name VARCHAR(64) NOT NULL, 
	mandate TEXT NOT NULL, 
	leader VARCHAR(64) NOT NULL, 
	owner_key_hash VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	halted_reason TEXT, 
	profit_share_pct FLOAT NOT NULL, 
	pool_cash FLOAT NOT NULL, 
	total_deposited FLOAT NOT NULL, 
	peak_equity FLOAT NOT NULL, 
	day_start_equity FLOAT NOT NULL, 
	day_start_date VARCHAR(10) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (slug)
);

CREATE TABLE IF NOT EXISTS agents (
	id VARCHAR(32) NOT NULL, 
	name VARCHAR(64) NOT NULL, 
	owner VARCHAR(64) NOT NULL, 
	runtime VARCHAR(64) NOT NULL, 
	strategy TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	owner_key_hash VARCHAR(64) NOT NULL, 
	agent_key_hash VARCHAR(64) NOT NULL, 
	key_prefix VARCHAR(16) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	halted_reason TEXT, 
	starting_equity FLOAT NOT NULL, 
	cash FLOAT NOT NULL, 
	peak_equity FLOAT NOT NULL, 
	day_start_equity FLOAT NOT NULL, 
	day_start_date VARCHAR(10) NOT NULL, 
	hl_subaccount VARCHAR(42), 
	org_id VARCHAR(32), 
	PRIMARY KEY (id), 
	UNIQUE (name), 
	FOREIGN KEY(org_id) REFERENCES orgs (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS deposits (
	id VARCHAR(32) NOT NULL, 
	org_id VARCHAR(32) NOT NULL, 
	depositor VARCHAR(64) NOT NULL, 
	amount_usd FLOAT NOT NULL, 
	ts TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(org_id) REFERENCES orgs (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_deposits_org ON deposits (org_id);

CREATE TABLE IF NOT EXISTS org_limits (
	org_id VARCHAR(32) NOT NULL, 
	max_leverage FLOAT NOT NULL, 
	max_notional_usd FLOAT NOT NULL, 
	daily_loss_pct FLOAT NOT NULL, 
	drawdown_flatten_pct FLOAT NOT NULL, 
	max_orders_per_min INTEGER NOT NULL, 
	allowed_markets JSON NOT NULL, 
	PRIMARY KEY (org_id), 
	FOREIGN KEY(org_id) REFERENCES orgs (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS equity_snapshots (
	id SERIAL NOT NULL, 
	agent_id VARCHAR(32) NOT NULL, 
	ts TIMESTAMP WITH TIME ZONE NOT NULL, 
	equity FLOAT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(agent_id) REFERENCES agents (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_snap_agent_ts ON equity_snapshots (agent_id, ts);

CREATE TABLE IF NOT EXISTS events (
	id SERIAL NOT NULL, 
	agent_id VARCHAR(32), 
	ts TIMESTAMP WITH TIME ZONE NOT NULL, 
	kind VARCHAR(32) NOT NULL, 
	detail TEXT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(agent_id) REFERENCES agents (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_events_agent_ts ON events (agent_id, ts);

CREATE TABLE IF NOT EXISTS limits (
	agent_id VARCHAR(32) NOT NULL, 
	max_leverage FLOAT NOT NULL, 
	max_notional_usd FLOAT NOT NULL, 
	daily_loss_pct FLOAT NOT NULL, 
	drawdown_flatten_pct FLOAT NOT NULL, 
	max_orders_per_min INTEGER NOT NULL, 
	allowed_markets JSON NOT NULL, 
	PRIMARY KEY (agent_id), 
	FOREIGN KEY(agent_id) REFERENCES agents (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS orders (
	id VARCHAR(32) NOT NULL, 
	agent_id VARCHAR(32) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	market VARCHAR(32) NOT NULL, 
	side VARCHAR(4) NOT NULL, 
	requested_size FLOAT NOT NULL, 
	order_type VARCHAR(8) NOT NULL, 
	limit_px FLOAT, 
	reduce_only BOOLEAN NOT NULL, 
	reason TEXT, 
	verdict VARCHAR(16) NOT NULL, 
	verdict_reason TEXT, 
	approved_size FLOAT NOT NULL, 
	filled_size FLOAT NOT NULL, 
	fill_px FLOAT, 
	exchange_fee_usd FLOAT NOT NULL, 
	builder_fee_usd FLOAT NOT NULL, 
	realized_pnl_usd FLOAT NOT NULL, 
	exchange_ref VARCHAR(64), 
	PRIMARY KEY (id), 
	FOREIGN KEY(agent_id) REFERENCES agents (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_orders_agent_created ON orders (agent_id, created_at);

CREATE TABLE IF NOT EXISTS positions (
	agent_id VARCHAR(32) NOT NULL, 
	market VARCHAR(32) NOT NULL, 
	size FLOAT NOT NULL, 
	entry_px FLOAT NOT NULL, 
	PRIMARY KEY (agent_id, market), 
	FOREIGN KEY(agent_id) REFERENCES agents (id) ON DELETE CASCADE
);
