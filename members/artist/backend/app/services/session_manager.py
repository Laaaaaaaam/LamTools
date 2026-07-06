from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import now
from app.models.session import Session
from app.models.message import Message, MessageRole, MessageType
from app.models.billing import BillingRecord
from app.schemas.session import SessionCreate, SessionUpdate, MessageCreate


async def create_session(db: AsyncSession, data: SessionCreate) -> Session:
    session = Session(title=data.title)
    db.add(session)
    await db.commit()
    await db.refresh(session)

    welcome = Message(
        session_id=session.id,
        role=MessageRole.system,
        content=f"欢迎使用 lamartist {session.id}",
        message_type=MessageType.text,
    )
    db.add(welcome)
    await db.commit()
    return session


async def update_session(db: AsyncSession, session_id: str, data: SessionUpdate) -> Session | None:
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        return None
    if data.title is not None:
        session.title = data.title
    session.updated_at = now()
    await db.commit()
    await db.refresh(session)
    return session


async def delete_session(db: AsyncSession, session_id: str) -> bool:
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        return False
    await db.delete(session)
    await db.commit()
    return True


async def get_session(db: AsyncSession, session_id: str) -> Session | None:
    result = await db.execute(select(Session).where(Session.id == session_id))
    return result.scalar_one_or_none()


async def get_session_detail(db: AsyncSession, session_id: str) -> dict | None:
    msg_subq = (
        select(
            Message.session_id,
            func.count(Message.id).label("message_count"),
        )
        .group_by(Message.session_id)
        .subquery()
    )
    billing_subq = (
        select(
            BillingRecord.session_id,
            func.coalesce(func.sum(BillingRecord.cost), 0).label("cost"),
            func.coalesce(func.sum(BillingRecord.tokens_in + BillingRecord.tokens_out), 0).label("tokens"),
        )
        .group_by(BillingRecord.session_id)
        .subquery()
    )
    result = await db.execute(
        select(
            Session,
            func.coalesce(msg_subq.c.message_count, 0).label("message_count"),
            func.coalesce(billing_subq.c.cost, 0).label("cost"),
            func.coalesce(billing_subq.c.tokens, 0).label("tokens"),
        )
        .outerjoin(msg_subq, msg_subq.c.session_id == Session.id)
        .outerjoin(billing_subq, billing_subq.c.session_id == Session.id)
        .where(Session.id == session_id)
    )
    row = result.first()
    if not row:
        return None
    s = row[0]
    return {
        "id": s.id,
        "title": s.title,
        "status": s.status,
        "metadata": s.metadata_,  # expose lineage_head_url, branch renames, etc.
        "created_at": str(s.created_at) if s.created_at else None,
        "updated_at": str(s.updated_at) if s.updated_at else None,
        "message_count": row.message_count,
        "cost": float(row.cost),
        "tokens": int(row.tokens),
    }


async def list_sessions(db: AsyncSession) -> list[dict]:
    msg_subq = (
        select(
            Message.session_id,
            func.count(Message.id).label("message_count"),
        )
        .group_by(Message.session_id)
        .subquery()
    )
    billing_subq = (
        select(
            BillingRecord.session_id,
            func.coalesce(func.sum(BillingRecord.cost), 0).label("cost"),
            func.coalesce(func.sum(BillingRecord.tokens_in + BillingRecord.tokens_out), 0).label("tokens"),
        )
        .group_by(BillingRecord.session_id)
        .subquery()
    )
    result = await db.execute(
        select(
            Session,
            func.coalesce(msg_subq.c.message_count, 0).label("message_count"),
            func.coalesce(billing_subq.c.cost, 0).label("cost"),
            func.coalesce(billing_subq.c.tokens, 0).label("tokens"),
        )
        .outerjoin(msg_subq, msg_subq.c.session_id == Session.id)
        .outerjoin(billing_subq, billing_subq.c.session_id == Session.id)
        .order_by(Session.updated_at.desc())
    )
    response = []
    for row in result:
        s = row[0]
        response.append({
            "id": s.id,
            "title": s.title,
            "status": s.status,
            "created_at": str(s.created_at) if s.created_at else None,
            "updated_at": str(s.updated_at) if s.updated_at else None,
            "message_count": row.message_count,
            "cost": float(row.cost),
            "tokens": int(row.tokens),
        })
    return response


async def add_message(db: AsyncSession, session_id: str, data: MessageCreate) -> Message:
    message = Message(
        session_id=session_id,
        role=MessageRole.user,
        content=data.content,
        message_type=MessageType(data.message_type) if data.message_type else MessageType.text,
        metadata_=data.metadata,
    )
    db.add(message)

    session_result = await db.execute(select(Session).where(Session.id == session_id))
    session = session_result.scalar_one_or_none()
    if session:
        session.updated_at = now()

    await db.commit()
    await db.refresh(message)
    return message


async def add_system_message(
    db: AsyncSession,
    session_id: str,
    content: str,
    message_type: str = "text",
    metadata: dict = None,
) -> Message:
    message = Message(
        session_id=session_id,
        role=MessageRole.assistant,
        content=content,
        message_type=MessageType(message_type),
        metadata_=metadata or {},
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def get_messages(db: AsyncSession, session_id: str) -> list[Message]:
    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.created_at.asc())
    )
    return list(result.scalars().all())


def message_to_response(msg: Message) -> dict:
    return {
        "id": msg.id,
        "session_id": msg.session_id,
        "role": msg.role.value if hasattr(msg.role, "value") else msg.role,
        "content": msg.content,
        "message_type": msg.message_type.value if hasattr(msg.message_type, "value") else msg.message_type,
        "metadata": msg.metadata_ or {},
        "created_at": msg.created_at,
    }
