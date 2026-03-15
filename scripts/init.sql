-- Supply Chain AI Platform - Database Initialization
-- This script runs on first PostgreSQL startup

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Create MLflow database
CREATE DATABASE mlflow OWNER supply_chain;

-- Set timezone
SET timezone = 'UTC';

-- Indexes will be created by SQLAlchemy/Alembic migrations
-- This script only sets up extensions and the mlflow database

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE supply_chain TO supply_chain;
GRANT ALL PRIVILEGES ON DATABASE mlflow TO supply_chain;
