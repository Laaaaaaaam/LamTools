from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from app.config import settings

engine = create_async_engine(
    settings.DB_URL,
    echo=settings.DEBUG,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def _ensure_session_columns(conn) -> None:
    result = await conn.execute(text("PRAGMA table_info('sessions')"))
    columns = [row[1] for row in result.fetchall()]
    if "status" not in columns:
        await conn.execute(text("ALTER TABLE sessions ADD COLUMN status VARCHAR(20) DEFAULT 'idle' NOT NULL"))
    if "metadata" not in columns:
        await conn.execute(text("ALTER TABLE sessions ADD COLUMN metadata JSON DEFAULT '{}'"))


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='api_vendors'"))
        if not result.fetchone():
            await conn.execute(text("""
                CREATE TABLE api_vendors (
                    id VARCHAR(36) PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    base_url VARCHAR(500) NOT NULL,
                    api_key_enc TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))

        result = await conn.execute(text("PRAGMA table_info('api_providers')"))
        columns = [row[1] for row in result.fetchall()]
        if "vendor_id" not in columns:
            await conn.execute(text("ALTER TABLE api_providers ADD COLUMN vendor_id VARCHAR(36)"))

        result = await conn.execute(text("PRAGMA table_info('billing_records')"))
        columns = [row[1] for row in result.fetchall()]
        if "session_id" not in columns:
            await conn.execute(text("ALTER TABLE billing_records ADD COLUMN session_id VARCHAR(36)"))

        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"))
        if result.fetchone():
            await conn.execute(text("UPDATE billing_records SET session_id = task_id WHERE session_id IS NULL AND task_id IS NOT NULL"))

        await conn.execute(text("DROP TABLE IF EXISTS sub_tasks"))
        await conn.execute(text("DROP TABLE IF EXISTS tasks"))

        await _ensure_session_columns(conn)

        await conn.execute(text("UPDATE sessions SET status = 'idle' WHERE status != 'idle'"))

        # --- Artist branch: widen messages.message_type to accept 'artist' ---
        result = await conn.execute(text("PRAGMA table_info('messages')"))
        msg_columns = {row[1]: row[2] for row in result.fetchall()}
        mt_type = msg_columns.get("message_type", "")
        if mt_type and "VARCHAR(9)" in mt_type and "artist" not in mt_type:
            # Recreate messages table with widened message_type — no CHECK constraint
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS _messages_new (
                    id VARCHAR(36) NOT NULL,
                    session_id VARCHAR(36) NOT NULL,
                    role VARCHAR(9) NOT NULL,
                    content TEXT,
                    message_type VARCHAR(20) NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME,
                    metadata JSON DEFAULT '{}',
                    PRIMARY KEY (id),
                    FOREIGN KEY(session_id) REFERENCES sessions (id)
                )
            """))
            await conn.execute(text("""
                INSERT INTO _messages_new
                SELECT id, session_id, role, content, message_type, created_at, updated_at, metadata
                FROM messages
            """))
            await conn.execute(text("DROP TABLE messages"))
            await conn.execute(text("ALTER TABLE _messages_new RENAME TO messages"))

        # --- Video branch: widen enum columns for new values ---
        # provider_type VARCHAR(9) → VARCHAR(20) to fit "video_gen"
        # billing_type VARCHAR(9) → VARCHAR(20) to fit "per_video_call"/"per_video_duration"
        result = await conn.execute(text("PRAGMA table_info('api_providers')"))
        provider_cols = {row[1]: row[2] for row in result.fetchall()}
        if provider_cols.get("provider_type") == "VARCHAR(9)":
            await conn.execute(text("""
                CREATE TABLE _api_providers_new (
                    id VARCHAR(36) NOT NULL,
                    nickname VARCHAR(100) NOT NULL,
                    base_url VARCHAR(500),
                    model_id VARCHAR(200) NOT NULL,
                    api_key_enc TEXT,
                    vendor_id VARCHAR(36),
                    provider_type VARCHAR(20) NOT NULL,
                    billing_type VARCHAR(20) NOT NULL,
                    unit_price NUMERIC(10, 6) NOT NULL,
                    currency VARCHAR(10) NOT NULL,
                    is_active BOOLEAN NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(vendor_id) REFERENCES api_vendors (id)
                )
            """))
            await conn.execute(text("""
                INSERT INTO _api_providers_new
                SELECT id, nickname, base_url, model_id, api_key_enc, vendor_id,
                       provider_type, billing_type, unit_price, currency, is_active,
                       created_at, updated_at
                FROM api_providers
            """))
            await conn.execute(text("DROP TABLE api_providers"))
            await conn.execute(text("ALTER TABLE _api_providers_new RENAME TO api_providers"))

        result = await conn.execute(text("PRAGMA table_info('billing_records')"))
        billing_cols = {row[1]: row[2] for row in result.fetchall()}
        if billing_cols.get("billing_type") == "VARCHAR(9)":
            await conn.execute(text("""
                CREATE TABLE _billing_records_new (
                    id VARCHAR(36) NOT NULL,
                    session_id VARCHAR(36),
                    provider_id VARCHAR(36),
                    billing_type VARCHAR(20) NOT NULL,
                    tokens_in INTEGER NOT NULL,
                    tokens_out INTEGER NOT NULL,
                    cost NUMERIC(10, 6) NOT NULL,
                    currency VARCHAR(10) NOT NULL,
                    detail JSON NOT NULL,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(session_id) REFERENCES sessions (id),
                    FOREIGN KEY(provider_id) REFERENCES api_providers (id)
                )
            """))
            await conn.execute(text("""
                INSERT INTO _billing_records_new
                SELECT id, session_id, provider_id, billing_type,
                       tokens_in, tokens_out, cost, currency, detail, created_at
                FROM billing_records
            """))
            await conn.execute(text("DROP TABLE billing_records"))
            await conn.execute(text("ALTER TABLE _billing_records_new RENAME TO billing_records"))

    async with async_session() as session:
        from app.services.api_manager import migrate_providers_to_vendors
        await migrate_providers_to_vendors(session)
