-- Protoss social layer: profiles and follows (the feed is derived from orders / events / deposits)

CREATE TABLE IF NOT EXISTS profiles (
	handle VARCHAR(32) NOT NULL,
	display_name VARCHAR(64) NOT NULL,
	bio TEXT,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (handle)
);

CREATE TABLE IF NOT EXISTS follows (
	handle VARCHAR(32) NOT NULL,
	target_type VARCHAR(8) NOT NULL,
	target_id VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (handle, target_type, target_id),
	FOREIGN KEY(handle) REFERENCES profiles (handle) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_follows_handle ON follows (handle);

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE follows ENABLE ROW LEVEL SECURITY;
