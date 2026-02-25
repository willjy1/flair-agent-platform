CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    email TEXT,
    phone TEXT,
    language_preference TEXT DEFAULT 'en',
    tier TEXT DEFAULT 'STANDARD',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bookings (
    id BIGSERIAL PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    flight_number TEXT NOT NULL,
    route TEXT NOT NULL,
    status TEXT NOT NULL,
    pnr TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS interaction_history (
    id BIGSERIAL PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    channel TEXT NOT NULL,
    intent TEXT NOT NULL,
    resolution TEXT NOT NULL,
    sentiment_score DOUBLE PRECISION DEFAULT 0,
    duration_seconds INTEGER DEFAULT 0,
    agent_type TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS preferences (
    customer_id TEXT PRIMARY KEY REFERENCES customers(id) ON DELETE CASCADE,
    seat_preference TEXT,
    meal_preference TEXT,
    notification_channel TEXT,
    special_assistance TEXT
);

CREATE TABLE IF NOT EXISTS compensation_history (
    id BIGSERIAL PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    booking_id BIGINT REFERENCES bookings(id) ON DELETE SET NULL,
    amount NUMERIC(10,2) NOT NULL,
    regulation TEXT NOT NULL,
    issued_at TIMESTAMPTZ DEFAULT NOW(),
    payment_status TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bookings_customer_id ON bookings(customer_id);
CREATE INDEX IF NOT EXISTS idx_bookings_flight_number ON bookings(flight_number);
CREATE INDEX IF NOT EXISTS idx_interaction_history_customer_id ON interaction_history(customer_id);
CREATE INDEX IF NOT EXISTS idx_interaction_history_created_at ON interaction_history(created_at);
CREATE INDEX IF NOT EXISTS idx_compensation_history_customer_id ON compensation_history(customer_id);
