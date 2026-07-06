"""
AI Chat Server - Flask backend with SSE streaming support
Supports both mock mode and OpenAI API mode
"""

import os
import json
import time
import uuid
import threading
import random
from flask import Flask, request, jsonify, Response, stream_with_context, send_from_directory

app = Flask(__name__, static_folder='.')

# ============ Configuration ============
USE_OPENAI = os.environ.get('USE_OPENAI', 'false').lower() == 'true'
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-3.5-turbo')
OPENAI_BASE_URL = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')

# ============ In-memory Storage ============
conversations = {}  # conv_id -> conversation dict
messages_store = {}  # msg_id -> message content (for SSE streaming)
stream_events = {}   # msg_id -> threading.Event

# ============ Mock Responses ============
MOCK_RESPONSES = [
    """你好！我是 AI 助手，很高兴为你服务！有什么我可以帮助你的吗？""",

    """这是一个很好的问题！让我来为你详细解答：

1. **首先**，我们需要理解问题的本质
2. **其次**，分析可能的解决方案
3. **最后**，选择最优方案并实施

希望这个回答对你有帮助！如果还有其他问题，随时问我。""",

    """当然可以！让我来帮你。

## 关键要点

### 1. 基础知识
- 这是第一点重要内容
- 这是第二点重要内容
- 这是第三点重要内容

### 2. 进阶技巧
> 提示：这里有一些实用的建议

### 3. 总结
总的来说，**核心思路**是：
1. 先理解需求
2. 再设计方案
3. 最后实施验证

希望这些信息对你有用！""",

    """这个问题很有趣！让我从几个角度来分析：

## 角度一：技术层面
从技术角度看，这涉及到以下几个关键概念：
- 数据结构的选择
- 算法的优化
- 系统架构的设计

## 角度二：实践层面
在实际应用中，我们需要注意：
1. 性能优化
2. 可维护性
3. 扩展性

## 角度三：未来展望
随着技术的发展，这个领域还有很多值得期待的方向。

如果你对某个方面特别感兴趣，欢迎继续深入探讨！""",

    """好的，我来帮你梳理一下思路：

### 步骤 1：明确目标
首先，我们需要明确具体要达成什么目标。

### 步骤 2：收集信息
然后，收集相关的信息和资源。

### 步骤 3：制定计划
接下来，制定详细的实施计划。

### 步骤 4：执行与调整
最后，按计划执行并根据实际情况进行调整。

---
**温馨提示**：如果在执行过程中遇到任何问题，随时可以回来继续讨论！"""
]


def generate_message_id():
    return uuid.uuid4().hex


def generate_conversation_id():
    return uuid.uuid4().hex


def generate_mock_response():
    """Generate a mock AI response word by word for SSE streaming."""
    response = random.choice(MOCK_RESPONSES)
    for char in response:
        yield char
        time.sleep(0.03)  # Simulate streaming delay
    # Add a small pause at the end
    time.sleep(0.1)


def generate_openai_response(messages):
    """Generate AI response using OpenAI API streaming."""
    try:
        import openai
        client = openai.OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL
        )
        stream = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as e:
        yield f"\n\n[Error calling OpenAI API: {str(e)}]"


# ============ Routes ============

@app.route('/')
def index():
    """Serve the chat HTML file."""
    return send_from_directory('.', 'chat.html')


@app.route('/chat', methods=['POST'])
def chat():
    """Receive user message and return a message ID for SSE streaming."""
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({'error': 'Missing message'}), 400

    user_message = data['message']
    conversation_id = data.get('conversation_id', '')

    # Generate IDs
    msg_id = generate_message_id()

    # Create or get conversation
    if not conversation_id or conversation_id not in conversations:
        conversation_id = generate_conversation_id()
        conversations[conversation_id] = {
            'id': conversation_id,
            'title': user_message[:50] + ('...' if len(user_message) > 50 else ''),
            'messages': [],
            'created_at': time.time()
        }

    # Store user message
    user_msg = {
        'id': generate_message_id(),
        'role': 'user',
        'content': user_message,
        'timestamp': time.time()
    }
    conversations[conversation_id]['messages'].append(user_msg)

    # Prepare messages for AI
    ai_messages = [{'role': m['role'], 'content': m['content']}
                   for m in conversations[conversation_id]['messages']]

    # Store AI response placeholder
    ai_msg = {
        'id': msg_id,
        'role': 'assistant',
        'content': '',
        'timestamp': time.time()
    }
    conversations[conversation_id]['messages'].append(ai_msg)

    # Store streaming data
    messages_store[msg_id] = {
        'conversation_id': conversation_id,
        'content': '',
        'done': False
    }
    stream_events[msg_id] = threading.Event()

    # Start background thread to generate AI response
    def generate_response():
        full_content = ''
        if USE_OPENAI and OPENAI_API_KEY:
            generator = generate_openai_response(ai_messages)
        else:
            generator = generate_mock_response()

        for chunk in generator:
            full_content += chunk
            messages_store[msg_id]['content'] = full_content
            stream_events[msg_id].set()  # Signal that new data is available
            time.sleep(0.01)

        messages_store[msg_id]['done'] = True
        messages_store[msg_id]['content'] = full_content
        # Update the actual message content
        for conv in conversations.values():
            for m in conv['messages']:
                if m['id'] == msg_id:
                    m['content'] = full_content
                    break
        stream_events[msg_id].set()

    thread = threading.Thread(target=generate_response, daemon=True)
    thread.start()

    return jsonify({
        'message_id': msg_id,
        'conversation_id': conversation_id
    })


@app.route('/stream/<message_id>')
def stream(message_id):
    """SSE endpoint for streaming AI response."""
    if message_id not in messages_store:
        return jsonify({'error': 'Message not found'}), 404

    def generate():
        last_content = ''
        while True:
            msg_data = messages_store.get(message_id)
            if not msg_data:
                break

            current_content = msg_data['content']
            # Send only new content
            if len(current_content) > len(last_content):
                new_chunk = current_content[len(last_content):]
                yield f"data: {json.dumps({'content': new_chunk})}\n\n"
                last_content = current_content

            if msg_data['done']:
                yield "event: done\ndata: {}\n\n"
                break

            # Wait for new data
            event = stream_events.get(message_id)
            if event:
                event.wait(timeout=0.5)
                event.clear()
            else:
                time.sleep(0.1)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        }
    )


@app.route('/history')
def get_history():
    """Get all conversations history."""
    conv_list = []
    for conv in conversations.values():
        conv_list.append({
            'id': conv['id'],
            'title': conv['title'],
            'created_at': conv['created_at'],
            'message_count': len(conv['messages'])
        })
    # Sort by created_at descending
    conv_list.sort(key=lambda x: x['created_at'], reverse=True)
    return jsonify({'conversations': conv_list})


@app.route('/history/<conversation_id>')
def get_conversation(conversation_id):
    """Get a specific conversation's messages."""
    conv = conversations.get(conversation_id)
    if not conv:
        return jsonify({'error': 'Conversation not found'}), 404
    return jsonify({
        'id': conv['id'],
        'title': conv['title'],
        'messages': conv['messages']
    })


@app.route('/clear', methods=['POST'])
def clear_history():
    """Clear all conversations."""
    conversations.clear()
    messages_store.clear()
    stream_events.clear()
    return jsonify({'status': 'ok'})


@app.route('/delete/<conversation_id>', methods=['POST'])
def delete_conversation(conversation_id):
    """Delete a specific conversation."""
    if conversation_id in conversations:
        # Clean up related message stores
        for msg in conversations[conversation_id]['messages']:
            if msg['id'] in messages_store:
                del messages_store[msg['id']]
            if msg['id'] in stream_events:
                del stream_events[msg['id']]
        del conversations[conversation_id]
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    print("=" * 50)
    print("AI Chat Server")
    print("=" * 50)
    print(f"Mode: {'OpenAI' if USE_OPENAI and OPENAI_API_KEY else 'Mock'}")
    print(f"OpenAI: {'Enabled' if USE_OPENAI else 'Disabled'}")
    print(f"API Key: {'Set' if OPENAI_API_KEY else 'Not Set'}")
    print("-" * 50)
    print("Starting server at http://localhost:5000")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
