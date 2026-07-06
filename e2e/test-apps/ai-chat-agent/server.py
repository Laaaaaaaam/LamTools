"""
AI Chat Server - FastAPI backend with SSE streaming
"""

import json
import os
import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
from pydantic import BaseModel

# ─── Configuration ────────────────────────────────────────────────────────────

AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_API_BASE = os.getenv("AI_API_BASE", "https://api.openai.com/v1")
AI_MODEL = os.getenv("AI_MODEL", "gpt-3.5-turbo")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
HISTORY_DIR = os.path.join(os.path.dirname(__file__), "histories")

os.makedirs(HISTORY_DIR, exist_ok=True)

# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(title="AI Chat")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Models ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    history: list = []

class HistorySave(BaseModel):
    conversation_id: str
    title: str
    messages: list

class HistoryItem(BaseModel):
    conversation_id: str
    title: str
    updated_at: str
    message_count: int

# ─── AI Chat Streaming ────────────────────────────────────────────────────────

async def stream_ai_response(messages: list) -> AsyncGenerator[str, None]:
    """Stream AI response tokens via SSE."""
    api_key = AI_API_KEY
    api_base = AI_API_BASE.rstrip("/")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": AI_MODEL,
        "messages": messages,
        "stream": True,
        "temperature": 0.7,
        "max_tokens": 2048,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            async with client.stream(
                "POST",
                f"{api_base}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    yield f"data: {json.dumps({'error': f'API error {response.status_code}: {error_body.decode()}'})}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            yield "data: [DONE]\n\n"
                            return
                        try:
                            data = json.loads(data_str)
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield f"data: {json.dumps({'content': content})}\n\n"
                        except json.JSONDecodeError:
                            continue

        except httpx.RequestError as e:
            yield f"data: {json.dumps({'error': f'Network error: {str(e)}'})}\n\n"
            yield "data: [DONE]\n\n"

# ─── API Routes ───────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Send message and receive streaming AI response."""
    # Build message list
    messages = []
    if request.history:
        for msg in request.history[-20:]:  # limit context window
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": request.message})

    return StreamingResponse(
        stream_ai_response(messages),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@app.post("/api/chat/history")
async def save_history(data: HistorySave):
    """Save conversation history to a JSON file."""
    conv_id = data.conversation_id or str(uuid.uuid4())
    filepath = os.path.join(HISTORY_DIR, f"{conv_id}.json")
    record = {
        "conversation_id": conv_id,
        "title": data.title or "New Chat",
        "updated_at": datetime.now().isoformat(),
        "messages": data.messages,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return {"status": "ok", "conversation_id": conv_id}

@app.get("/api/chat/history")
async def list_histories():
    """List all saved conversation histories."""
    if not os.path.isdir(HISTORY_DIR):
        return {"histories": []}
    histories = []
    for fname in os.listdir(HISTORY_DIR):
        if fname.endswith(".json"):
            filepath = os.path.join(HISTORY_DIR, fname)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                histories.append({
                    "conversation_id": data.get("conversation_id", fname[:-5]),
                    "title": data.get("title", "Untitled"),
                    "updated_at": data.get("updated_at", ""),
                    "message_count": len(data.get("messages", [])),
                })
            except (json.JSONDecodeError, OSError):
                continue
    histories.sort(key=lambda h: h.get("updated_at", ""), reverse=True)
    return {"histories": histories}

@app.get("/api/chat/history/{conversation_id}")
async def get_history(conversation_id: str):
    """Get a specific conversation history."""
    filepath = os.path.join(HISTORY_DIR, f"{conversation_id}.json")
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Conversation not found")
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data

@app.delete("/api/chat/history/{conversation_id}")
async def delete_history(conversation_id: str):
    """Delete a conversation history."""
    filepath = os.path.join(HISTORY_DIR, f"{conversation_id}.json")
    if os.path.isfile(filepath):
        os.remove(filepath)
    return {"status": "ok"}

# ─── Serve Frontend ───────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve the chat frontend."""
    html_path = os.path.join(os.path.dirname(__file__), "chat.html")
    if os.path.isfile(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h1>chat.html not found</h1>", status_code=404)

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"🚀 AI Chat Server starting on http://{HOST}:{PORT}")
    print(f"   AI API Base: {AI_API_BASE}")
    print(f"   AI Model: {AI_MODEL}")
    uvicorn.run(app, host=HOST, port=PORT)
