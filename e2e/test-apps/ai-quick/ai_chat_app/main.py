"""
AI对话应用 - 后端服务 (FastAPI)
"""

import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
import uvicorn

app = FastAPI(title="AI Chat App")

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 默认使用环境变量中的API密钥
# 设置 OPENAI_API_KEY 环境变量，或在这里直接设置
# 也支持兼容OpenAI接口的服务（如DeepSeek、硅基流动等）
API_KEY = os.getenv("OPENAI_API_KEY", "")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


class Message(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    stream: bool = False
    temperature: float = 0.7
    max_tokens: Optional[int] = None


class ChatResponse(BaseModel):
    message: Message
    usage: Optional[dict] = None


@app.get("/")
async def root():
    return {"status": "ok", "message": "AI Chat App API is running"}


@app.get("/v1/models")
async def list_models():
    """获取可用模型列表"""
    try:
        models = client.models.list()
        return {"models": [m.id for m in models]}
    except Exception as e:
        return {"models": [MODEL], "note": f"Using default model: {MODEL}"}


@app.post("/v1/chat/completions", response_model=ChatResponse)
async def chat_completion(request: ChatRequest):
    """
    非流式对话接口
    """
    try:
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        
        kwargs = {
            "model": MODEL,
            "messages": messages,
            "temperature": request.temperature,
        }
        if request.max_tokens:
            kwargs["max_tokens"] = request.max_tokens
        
        response = client.chat.completions.create(**kwargs)
        
        return ChatResponse(
            message=Message(
                role="assistant",
                content=response.choices[0].message.content
            ),
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            } if response.usage else None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    流式对话接口 - 返回SSE流
    """
    from fastapi.responses import StreamingResponse
    
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    
    async def generate():
        try:
            kwargs = {
                "model": MODEL,
                "messages": messages,
                "temperature": request.temperature,
                "stream": True,
            }
            if request.max_tokens:
                kwargs["max_tokens"] = request.max_tokens
            
            stream = client.chat.completions.create(**kwargs)
            
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield f"data: {chunk.choices[0].delta.content}\n\n"
            
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@app.post("/v1/chat/check")
async def check_config():
    """检查API配置是否有效"""
    if not API_KEY:
        return {"configured": False, "message": "未设置API密钥，请在环境变量中设置 OPENAI_API_KEY"}
    
    try:
        client.models.list()
        return {"configured": True, "message": "API配置有效", "model": MODEL, "base_url": BASE_URL}
    except Exception as e:
        return {"configured": False, "message": f"API配置无效: {str(e)}", "model": MODEL, "base_url": BASE_URL}


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    print(f"🚀 AI Chat App 后端服务启动中...")
    print(f"📡 API地址: http://localhost:{port}")
    print(f"🤖 当前模型: {MODEL}")
    print(f"🔗 API地址: {BASE_URL}")
    print(f"🔑 API密钥: {'已设置' if API_KEY else '未设置 - 请在环境变量中设置 OPENAI_API_KEY'}")
    uvicorn.run(app, host="0.0.0.0", port=port)
