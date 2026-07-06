/**
 * AI 对话助手 - 主应用逻辑
 */
class ChatApp {
    constructor() {
        // 状态
        this.chats = this.loadChats();
        this.currentChatId = null;
        this.isGenerating = false;
        this.abortController = null;
        this.settings = this.loadSettings();

        // DOM 元素
        this.elements = {
            sidebar: document.getElementById('sidebar'),
            toggleSidebar: document.getElementById('toggleSidebar'),
            newChatBtn: document.getElementById('newChatBtn'),
            searchInput: document.getElementById('searchInput'),
            chatList: document.getElementById('chatList'),
            clearAllBtn: document.getElementById('clearAllBtn'),
            chatArea: document.getElementById('chatArea'),
            welcomeScreen: document.getElementById('welcomeScreen'),
            messagesContainer: document.getElementById('messagesContainer'),
            messageInput: document.getElementById('messageInput'),
            sendBtn: document.getElementById('sendBtn'),
            stopBtn: document.getElementById('stopBtn'),
            charCount: document.getElementById('charCount'),
            modelSelect: document.getElementById('modelSelect'),
            settingsBtn: document.getElementById('settingsBtn'),
            settingsModal: document.getElementById('settingsModal'),
            closeSettings: document.getElementById('closeSettings'),
            saveSettings: document.getElementById('saveSettings'),
            apiUrl: document.getElementById('apiUrl'),
            apiKey: document.getElementById('apiKey'),
            toggleApiKey: document.getElementById('toggleApiKey'),
            systemPrompt: document.getElementById('systemPrompt'),
            temperature: document.getElementById('temperature'),
            tempValue: document.getElementById('tempValue'),
            maxTokens: document.getElementById('maxTokens'),
            streamToggle: document.getElementById('streamToggle'),
            toastContainer: document.getElementById('toastContainer'),
        };

        this.init();
    }

    init() {
        this.bindEvents();
        this.applySettings();
        this.renderChatList();

        // 如果有对话，打开最后一个
        if (this.chats.length > 0) {
            this.switchChat(this.chats[0].id);
        }

        // 配置 marked
        marked.use(markedHighlight.markedHighlight({
            highlight: (code, lang) => {
                if (lang && hljs.getLanguage(lang)) {
                    return hljs.highlight(code, { language: lang }).value;
                }
                return hljs.highlightAuto(code).value;
            },
            langPrefix: 'language-',
        }));
        marked.setOptions({
            breaks: true,
            gfm: true,
        });
    }

    // ===== 事件绑定 =====
    bindEvents() {
        // 侧边栏切换
        this.elements.toggleSidebar.addEventListener('click', () => {
            this.elements.sidebar.classList.toggle('collapsed');
        });

        // 新建对话
        this.elements.newChatBtn.addEventListener('click', () => this.createNewChat());

        // 搜索
        this.elements.searchInput.addEventListener('input', (e) => {
            this.renderChatList(e.target.value);
        });

        // 清除所有
        this.elements.clearAllBtn.addEventListener('click', () => {
            if (confirm('确定要清除所有对话吗？此操作不可撤销。')) {
                this.chats = [];
                this.currentChatId = null;
                this.saveChats();
                this.renderChatList();
                this.showWelcome();
                this.showToast('已清除所有对话', 'success');
            }
        });

        // 输入框
        this.elements.messageInput.addEventListener('input', () => {
            this.autoResize();
            this.updateCharCount();
            this.updateSendButton();
        });

        this.elements.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // 发送/停止
        this.elements.sendBtn.addEventListener('click', () => this.sendMessage());
        this.elements.stopBtn.addEventListener('click', () => this.stopGeneration());

        // 快捷提示
        document.querySelectorAll('.quick-prompt').forEach(btn => {
            btn.addEventListener('click', () => {
                const prompt = btn.dataset.prompt;
                this.elements.messageInput.value = prompt;
                this.updateCharCount();
                this.updateSendButton();
                this.sendMessage();
            });
        });

        // 设置
        this.elements.settingsBtn.addEventListener('click', () => this.openSettings());
        this.elements.closeSettings.addEventListener('click', () => this.closeSettingsModal());
        this.elements.saveSettings.addEventListener('click', () => this.saveSettingsFromUI());
        this.elements.settingsModal.addEventListener('click', (e) => {
            if (e.target === this.elements.settingsModal) this.closeSettingsModal();
        });

        this.elements.toggleApiKey.addEventListener('click', () => {
            const input = this.elements.apiKey;
            input.type = input.type === 'password' ? 'text' : 'password';
        });

        this.elements.temperature.addEventListener('input', (e) => {
            this.elements.tempValue.textContent = e.target.value;
        });

        // 响应式：移动端点击主内容区关闭侧边栏
        this.elements.chatArea.addEventListener('click', () => {
            if (window.innerWidth <= 768 && !this.elements.sidebar.classList.contains('collapsed')) {
                this.elements.sidebar.classList.add('collapsed');
            }
        });
    }

    // ===== 对话管理 =====
    createNewChat() {
        const chat = {
            id: Date.now().toString(),
            title: '新对话',
            messages: [],
            model: this.elements.modelSelect.value,
            createdAt: Date.now(),
        };
        this.chats.unshift(chat);
        this.saveChats();
        this.switchChat(chat.id);
        this.renderChatList();
        this.elements.messageInput.focus();
    }

    switchChat(chatId) {
        this.currentChatId = chatId;
        const chat = this.getCurrentChat();
        if (!chat) return;

        this.elements.modelSelect.value = chat.model;
        this.renderChatList();
        this.renderMessages();
    }

    deleteChat(chatId, e) {
        e.stopPropagation();
        this.chats = this.chats.filter(c => c.id !== chatId);
        this.saveChats();

        if (this.currentChatId === chatId) {
            this.currentChatId = null;
            if (this.chats.length > 0) {
                this.switchChat(this.chats[0].id);
            } else {
                this.showWelcome();
            }
        }
        this.renderChatList();
    }

    getCurrentChat() {
        return this.chats.find(c => c.id === this.currentChatId);
    }

    // ===== 消息发送 =====
    async sendMessage() {
        const text = this.elements.messageInput.value.trim();
        if (!text || this.isGenerating) return;

        // 如果没有当前对话，创建一个
        if (!this.currentChatId) {
            this.createNewChat();
        }

        const chat = this.getCurrentChat();
        if (!chat) return;

        // 添加用户消息
        chat.messages.push({ role: 'user', content: text });
        
        // 更新标题（取第一条消息的前30个字符）
        if (chat.messages.filter(m => m.role === 'user').length === 1) {
            chat.title = text.slice(0, 30) + (text.length > 30 ? '...' : '');
            this.renderChatList();
        }

        // 清空输入
        this.elements.messageInput.value = '';
        this.autoResize();
        this.updateCharCount();
        this.updateSendButton();

        // 渲染消息
        this.renderMessages();
        this.scrollToBottom();

        // 生成AI回复
        await this.generateResponse(chat);
    }

    async generateResponse(chat) {
        this.isGenerating = true;
        this.showStopButton();

        // 添加空的助手消息
        chat.messages.push({ role: 'assistant', content: '' });
        this.renderMessages();
        this.scrollToBottom();

        const assistantMsgIndex = chat.messages.length - 1;

        try {
            // 构建消息列表
            const messages = [
                { role: 'system', content: this.settings.systemPrompt },
                ...chat.messages.filter(m => m.role !== 'system').map(m => ({
                    role: m.role,
                    content: m.content,
                })),
            ];
            // 移除最后一个空的assistant消息
            messages.pop();

            if (this.settings.stream) {
                await this.streamResponse(chat, messages, assistantMsgIndex);
            } else {
                await this.normalResponse(chat, messages, assistantMsgIndex);
            }
        } catch (error) {
            if (error.name === 'AbortError') {
                chat.messages[assistantMsgIndex].content += '\n\n*[生成已停止]*';
            } else {
                console.error('生成错误:', error);
                chat.messages[assistantMsgIndex].content = `⚠️ 生成失败: ${error.message}\n\n请在设置中配置 API 地址和 API Key 后重试。`;
            }
            this.renderMessages();
        } finally {
            this.isGenerating = false;
            this.showSendButton();
            this.saveChats();
        }
    }

    async streamResponse(chat, messages, assistantMsgIndex) {
        this.abortController = new AbortController();

        const response = await fetch(this.settings.apiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.settings.apiKey}`,
            },
            body: JSON.stringify({
                model: chat.model,
                messages: messages,
                temperature: parseFloat(this.settings.temperature),
                max_tokens: parseInt(this.settings.maxTokens),
                stream: true,
            }),
            signal: this.abortController.signal,
        });

        if (!response.ok) {
            const errText = await response.text();
            throw new Error(`API 返回错误 (${response.status}): ${errText}`);
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
                if (!trimmed || trimmed === 'data: [DONE]') continue;
                if (!trimmed.startsWith('data: ')) continue;

                try {
                    const data = JSON.parse(trimmed.slice(6));
                    const delta = data.choices?.[0]?.delta?.content;
                    if (delta) {
                        chat.messages[assistantMsgIndex].content += delta;
                        this.updateStreamingMessage(chat.messages[assistantMsgIndex].content);
                        this.scrollToBottom();
                    }
                } catch (e) {
                    // 忽略解析错误
                }
            }
        }

        // 最终渲染 - remove streaming cursor
        const msgElements = this.elements.messagesContainer.querySelectorAll('.message.assistant');
        const lastMsg = msgElements[msgElements.length - 1];
        if (lastMsg) {
            const contentEl = lastMsg.querySelector('.message-content');
            contentEl.classList.remove('streaming-cursor');
        }
        this.renderMessages();
    }

    async normalResponse(chat, messages, assistantMsgIndex) {
        this.abortController = new AbortController();

        const response = await fetch(this.settings.apiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${this.settings.apiKey}`,
            },
            body: JSON.stringify({
                model: chat.model,
                messages: messages,
                temperature: parseFloat(this.settings.temperature),
                max_tokens: parseInt(this.settings.maxTokens),
            }),
            signal: this.abortController.signal,
        });

        if (!response.ok) {
            const errText = await response.text();
            throw new Error(`API 返回错误 (${response.status}): ${errText}`);
        }

        const data = await response.json();
        const content = data.choices?.[0]?.message?.content || '（无回复内容）';
        chat.messages[assistantMsgIndex].content = content;

        // 模拟打字效果
        await this.typewriterEffect(content);
    }

    async typewriterEffect(fullText) {
        const msgElements = this.elements.messagesContainer.querySelectorAll('.message.assistant');
        const lastMsg = msgElements[msgElements.length - 1];
        if (!lastMsg) return;

        const contentEl = lastMsg.querySelector('.message-content');
        contentEl.innerHTML = '';
        contentEl.classList.add('streaming-cursor');

        let displayed = '';
        const chars = fullText.split('');
        const chunkSize = 3;

        for (let i = 0; i < chars.length; i += chunkSize) {
            if (!this.isGenerating) break;
            displayed += chars.slice(i, i + chunkSize).join('');
            contentEl.innerHTML = this.renderMarkdown(displayed);
            this.scrollToBottom();
            await this.sleep(20);
        }

        contentEl.classList.remove('streaming-cursor');
        contentEl.innerHTML = this.renderMarkdown(fullText);
        this.addCodeCopyButtons();
    }

    updateStreamingMessage(content) {
        const msgElements = this.elements.messagesContainer.querySelectorAll('.message.assistant');
        const lastMsg = msgElements[msgElements.length - 1];
        if (!lastMsg) return;

        const contentEl = lastMsg.querySelector('.message-content');
        // Remove streaming cursor before rendering markdown (to avoid it being inside block elements)
        contentEl.classList.remove('streaming-cursor');
        contentEl.innerHTML = this.renderMarkdown(content);
        // Re-add streaming cursor after markdown render
        if (this.isGenerating) {
            contentEl.classList.add('streaming-cursor');
        }
        this.addCodeCopyButtons();
    }

    stopGeneration() {
        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
    }

    // ===== 渲染 =====
    renderChatList(filter = '') {
        const list = this.elements.chatList;
        const filtered = filter
            ? this.chats.filter(c => c.title.toLowerCase().includes(filter.toLowerCase()))
            : this.chats;

        list.innerHTML = filtered.map(chat => `
            <div class="chat-item ${chat.id === this.currentChatId ? 'active' : ''}" 
                 data-id="${chat.id}">
                <span class="chat-item-icon">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                    </svg>
                </span>
                <span class="chat-item-text">${this.escapeHtml(chat.title)}</span>
                <button class="chat-item-delete" data-id="${chat.id}" title="删除对话">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18"/>
                        <line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                </button>
            </div>
        `).join('');

        // 绑定事件
        list.querySelectorAll('.chat-item').forEach(item => {
            item.addEventListener('click', () => {
                this.switchChat(item.dataset.id);
            });
        });

        list.querySelectorAll('.chat-item-delete').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.deleteChat(btn.dataset.id, e);
            });
        });
    }

    renderMessages() {
        const chat = this.getCurrentChat();
        if (!chat || chat.messages.length === 0) {
            this.showWelcome();
            return;
        }

        this.elements.welcomeScreen.style.display = 'none';
        this.elements.messagesContainer.style.display = 'block';

        this.elements.messagesContainer.innerHTML = chat.messages.map((msg, index) => {
            if (msg.role === 'user') {
                return this.renderUserMessage(msg.content);
            } else if (msg.role === 'assistant') {
                return this.renderAssistantMessage(msg.content, index === chat.messages.length - 1);
            }
            return '';
        }).join('');

        this.addCodeCopyButtons();
        this.addMessageActions();
        this.scrollToBottom();
    }

    renderUserMessage(content) {
        return `
            <div class="message user">
                <div class="message-inner">
                    <div class="message-avatar">U</div>
                    <div class="message-content">${this.escapeHtml(content).replace(/\n/g, '<br>')}</div>
                </div>
            </div>
        `;
    }

    renderAssistantMessage(content, isLast) {
        const html = content ? this.renderMarkdown(content) : `
            <div class="typing-indicator">
                <span></span><span></span><span></span>
            </div>
        `;

        return `
            <div class="message assistant">
                <div class="message-inner">
                    <div class="message-avatar">AI</div>
                    <div class="message-content ${isLast && this.isGenerating ? 'streaming-cursor' : ''}">${html}</div>
                </div>
                ${content ? `
                <div class="message-inner" style="margin-top: 0;">
                    <div style="width: 36px; flex-shrink: 0;"></div>
                    <div class="message-actions">
                        <button class="msg-action-btn copy-msg-btn" data-content="${this.escapeAttr(content)}" title="复制">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                            </svg>
                            复制
                        </button>
                        <button class="msg-action-btn regen-btn" title="重新生成">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="23 4 23 10 17 10"/>
                                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
                            </svg>
                            重新生成
                        </button>
                    </div>
                </div>` : ''}
            </div>
        `;
    }

    renderMarkdown(text) {
        if (!text) return '';
        try {
            let html = marked.parse(text);
            if (typeof html !== 'string') return this.escapeHtml(text).replace(/\n/g, '<br>');
            // 为代码块添加语言标签和复制按钮
            html = html.replace(/<pre><code class="language-(\w+)">/g, (match, lang) => {
                return `<div class="code-header"><span>${this.escapeHtml(lang)}</span><button class="copy-code-btn" onclick="app.copyCode(this)">复制代码</button></div><pre><code class="language-${this.escapeHtml(lang)}">`;
            });
            html = html.replace(/<pre><code>/g, () => {
                return `<div class="code-header"><span>code</span><button class="copy-code-btn" onclick="app.copyCode(this)">复制代码</button></div><pre><code>`;
            });
            return html;
        } catch (e) {
            console.error('Markdown render error:', e);
            return this.escapeHtml(text).replace(/\n/g, '<br>');
        }
    }

    addCodeCopyButtons() {
        // 已在 renderMarkdown 中处理
    }

    addMessageActions() {
        // 复制消息
        this.elements.messagesContainer.querySelectorAll('.copy-msg-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const content = btn.dataset.content;
                if (!content) return;
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(content).then(() => {
                        this.showToast('已复制到剪贴板', 'success');
                    }).catch(() => {
                        this.showToast('复制失败', 'error');
                    });
                } else {
                    // Fallback
                    const textarea = document.createElement('textarea');
                    textarea.value = content;
                    textarea.style.position = 'fixed';
                    textarea.style.opacity = '0';
                    document.body.appendChild(textarea);
                    textarea.select();
                    document.execCommand('copy');
                    document.body.removeChild(textarea);
                    this.showToast('已复制到剪贴板', 'success');
                }
            });
        });

        // 重新生成
        this.elements.messagesContainer.querySelectorAll('.regen-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                if (this.isGenerating) return;
                const chat = this.getCurrentChat();
                if (!chat) return;
                // 移除最后一条助手消息
                if (chat.messages.length > 0 && chat.messages[chat.messages.length - 1].role === 'assistant') {
                    chat.messages.pop();
                }
                this.renderMessages();
                await this.generateResponse(chat);
            });
        });
    }

    copyCode(btn) {
        try {
            const header = btn.closest('.code-header');
            if (!header) return;
            const pre = header.nextElementSibling;
            if (!pre) return;
            const code = pre.querySelector('code');
            if (!code) return;
            navigator.clipboard.writeText(code.textContent).then(() => {
                btn.textContent = '已复制!';
                setTimeout(() => { btn.textContent = '复制代码'; }, 2000);
            }).catch(() => {
                // Fallback for older browsers
                const range = document.createRange();
                range.selectNodeContents(code);
                const selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
                document.execCommand('copy');
                selection.removeAllRanges();
                btn.textContent = '已复制!';
                setTimeout(() => { btn.textContent = '复制代码'; }, 2000);
            });
        } catch (e) {
            console.error('Copy failed:', e);
        }
    }

    showWelcome() {
        this.elements.welcomeScreen.style.display = 'flex';
        this.elements.messagesContainer.style.display = 'none';
        this.elements.messagesContainer.innerHTML = '';
        this.currentChatId = null;
        this.renderChatList();
    }

    // ===== 设置 =====
    openSettings() {
        this.elements.apiUrl.value = this.settings.apiUrl;
        this.elements.apiKey.value = this.settings.apiKey;
        this.elements.systemPrompt.value = this.settings.systemPrompt;
        this.elements.temperature.value = this.settings.temperature;
        this.elements.tempValue.textContent = this.settings.temperature;
        this.elements.maxTokens.value = this.settings.maxTokens;
        this.elements.streamToggle.checked = this.settings.stream;
        this.elements.settingsModal.style.display = 'flex';
    }

    closeSettingsModal() {
        this.elements.settingsModal.style.display = 'none';
    }

    saveSettingsFromUI() {
        this.settings = {
            apiUrl: this.elements.apiUrl.value.trim(),
            apiKey: this.elements.apiKey.value.trim(),
            systemPrompt: this.elements.systemPrompt.value.trim(),
            temperature: this.elements.temperature.value,
            maxTokens: this.elements.maxTokens.value,
            stream: this.elements.streamToggle.checked,
        };
        localStorage.setItem('ai-chat-settings', JSON.stringify(this.settings));
        this.closeSettingsModal();
        this.showToast('设置已保存', 'success');
    }

    loadSettings() {
        const saved = localStorage.getItem('ai-chat-settings');
        if (saved) {
            return JSON.parse(saved);
        }
        return {
            apiUrl: 'https://api.openai.com/v1/chat/completions',
            apiKey: '',
            systemPrompt: '你是一个有帮助的AI助手，请用中文回答问题。',
            temperature: '0.7',
            maxTokens: '2048',
            stream: true,
        };
    }

    applySettings() {
        this.settings = this.loadSettings();
    }

    // ===== 持久化 =====
    loadChats() {
        const saved = localStorage.getItem('ai-chat-chats');
        return saved ? JSON.parse(saved) : [];
    }

    saveChats() {
        localStorage.setItem('ai-chat-chats', JSON.stringify(this.chats));
    }

    // ===== UI 辅助 =====
    autoResize() {
        const textarea = this.elements.messageInput;
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
    }

    updateCharCount() {
        const len = this.elements.messageInput.value.length;
        this.elements.charCount.textContent = `${len} / 4000`;
        if (len > 4000) {
            this.elements.charCount.style.color = 'var(--error)';
        } else {
            this.elements.charCount.style.color = '';
        }
    }

    updateSendButton() {
        const hasText = this.elements.messageInput.value.trim().length > 0;
        this.elements.sendBtn.disabled = !hasText || this.isGenerating;
    }

    showSendButton() {
        this.elements.sendBtn.style.display = 'flex';
        this.elements.stopBtn.style.display = 'none';
        this.updateSendButton();
    }

    showStopButton() {
        this.elements.sendBtn.style.display = 'none';
        this.elements.stopBtn.style.display = 'flex';
    }

    scrollToBottom() {
        requestAnimationFrame(() => {
            this.elements.chatArea.scrollTop = this.elements.chatArea.scrollHeight;
        });
    }

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        this.elements.toastContainer.appendChild(toast);
        setTimeout(() => {
            toast.remove();
        }, 3000);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    escapeAttr(text) {
        return text.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// 启动应用
const app = new ChatApp();
