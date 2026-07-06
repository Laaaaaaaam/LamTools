from sqlalchemy import text

from app.database import _ensure_session_columns
from app.schemas.session import SessionCreate
from app.services.session_manager import create_session


async def test_init_db_adds_missing_session_metadata_column(test_db):
    await test_db.execute(text("DROP TABLE IF EXISTS sessions"))
    await test_db.execute(text("""
        CREATE TABLE sessions (
            id VARCHAR(36) PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            status VARCHAR(20) DEFAULT 'idle' NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
    """))
    await test_db.commit()

    async with test_db.bind.begin() as conn:
        await _ensure_session_columns(conn)

    result = await test_db.execute(text("PRAGMA table_info('sessions')"))
    columns = [row[1] for row in result.fetchall()]
    assert "metadata" in columns

    session = await create_session(test_db, SessionCreate(title="迁移后会话"))
    assert session.id
