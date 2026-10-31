-- Protoss: join-with-card sessions (fiat onramp -> user's own wallet -> legion vault). No funds or keys here.

CREATE TABLE IF NOT EXISTS onboard_sessions (
	id VARCHAR(24) NOT NULL,
	legion_slug VARCHAR(48),
	provider VARCHAR(16) NOT NULL,
	amount_usd FLOAT NOT NULL,
	wallet VARCHAR(42) NOT NULL,
	destination_kind VARCHAR(8) NOT NULL,
	destination VARCHAR(42) NOT NULL,
	region VARCHAR(2),
	status VARCHAR(12) NOT NULL,
	funded_usd FLOAT NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_onboard_sessions_wallet ON onboard_sessions (wallet);

ALTER TABLE onboard_sessions ENABLE ROW LEVEL SECURITY;
