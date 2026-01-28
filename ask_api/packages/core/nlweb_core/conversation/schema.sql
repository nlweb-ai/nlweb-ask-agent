-- PostgreSQL Schema for NLWeb Conversation Storage
-- Copyright (c) 2025 Microsoft Corporation.
-- Licensed under the MIT License

-- Conversations table
CREATE TABLE IF NOT EXISTS conversations (
    id BIGSERIAL PRIMARY KEY,
    message_id VARCHAR(255) UNIQUE NOT NULL,
    conversation_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255),
    site VARCHAR(255),
    timestamp TIMESTAMPTZ NOT NULL,
    request JSONB NOT NULL,
    results JSONB,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_conversation_id ON conversations(conversation_id);
CREATE INDEX IF NOT EXISTS idx_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_user_site ON conversations(user_id, site);
CREATE INDEX IF NOT EXISTS idx_timestamp ON conversations(timestamp);
CREATE INDEX IF NOT EXISTS idx_conversation_timestamp ON conversations(conversation_id, timestamp);

-- GIN indexes for searching within JSONB fields
CREATE INDEX IF NOT EXISTS idx_request_query ON conversations USING GIN ((request->'query'));
CREATE INDEX IF NOT EXISTS idx_results ON conversations USING GIN (results);

-- Function for updating updated_at timestamp automatically
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at on row changes
CREATE TRIGGER update_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function for cleanup/retention policy (optional - can be run as scheduled job)
CREATE OR REPLACE FUNCTION delete_old_conversations(retention_days INTEGER DEFAULT 365)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM conversations
    WHERE timestamp < NOW() - (retention_days || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Grant permissions (adjust as needed)
-- GRANT SELECT, INSERT, UPDATE, DELETE ON conversations TO nlwebadmin;
-- GRANT USAGE, SELECT ON SEQUENCE conversations_id_seq TO nlwebadmin;
