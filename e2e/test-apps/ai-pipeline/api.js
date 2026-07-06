/**
 * api.js - 服务层：通过本地 /chat 代理调用 AI API
 * 浏览器无法直连 API（跨域），所有请求走 Python 代理转发
 */

class ApiError extends Error {
  constructor(message, status, details = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
  }
}

class ApiService {
  /**
   * 发送对话请求（流式，通过本地代理）
   */
  sendChatStream(config, messages, onChunk, onDone, onError) {
    const controller = new AbortController();

    const fetchAndStream = async () => {
      try {
        const response = await fetch('/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            apiKey: config.apiKey,
            baseUrl: config.baseUrl,
            model: config.model,
            messages: messages,
            maxTokens: config.maxTokens || 2048,
            temperature: config.temperature ?? 0.7,
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          let msg = '';
          try { msg = await response.text(); } catch {}
          throw new ApiError(`HTTP ${response.status}: ${msg.slice(0, 200)}`, response.status);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith(':')) continue;
            if (trimmed === 'data: [DONE]') { onDone(); return; }
            if (trimmed.startsWith('data: ')) {
              try {
                const data = JSON.parse(trimmed.slice(6));
                const delta = data.choices?.[0]?.delta;
                if (delta?.content) onChunk(delta.content);
              } catch {}
            }
          }
        }
        onDone();
      } catch (e) {
        if (e.name === 'AbortError') { onDone(); return; }
        onError(e instanceof ApiError ? e : new ApiError(e.message || '请求失败', 0));
      }
    };

    fetchAndStream();
    return controller;
  }
}

const apiService = new ApiService();
