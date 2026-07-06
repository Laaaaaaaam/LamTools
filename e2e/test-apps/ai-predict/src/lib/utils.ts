import { Conversation, Message } from './types';

const STORAGE_KEY = 'ai-chat-conversations';
const ACTIVE_KEY = 'ai-chat-active-id';

export function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substr(2, 9);
}

export function saveConversations(conversations: Conversation[]): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations));
  } catch (e) {
    console.error('Failed to save conversations:', e);
  }
}

export function loadConversations(): Conversation[] {
  if (typeof window === 'undefined') return [];
  try {
    const data = localStorage.getItem(STORAGE_KEY);
    return data ? JSON.parse(data) : [];
  } catch {
    return [];
  }
}

export function saveActiveId(id: string): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(ACTIVE_KEY, id);
}

export function loadActiveId(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(ACTIVE_KEY);
}

export function createConversation(model: string = 'gpt-4'): Conversation {
  return {
    id: generateId(),
    title: '新的对话',
    messages: [],
    createdAt: Date.now(),
    updatedAt: Date.now(),
    model,
  };
}

export function createMessage(role: 'user' | 'assistant' | 'system', content: string): Message {
  return {
    id: generateId(),
    role,
    content,
    timestamp: Date.now(),
  };
}

export function generateTitle(firstMessage: string): string {
  const trimmed = firstMessage.trim();
  if (trimmed.length <= 20) return trimmed;
  return trimmed.substring(0, 20) + '...';
}

export function formatTime(timestamp: number): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes}分钟前`;
  if (hours < 24) return `${hours}小时前`;
  if (days < 7) return `${days}天前`;
  
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

// Simulated AI responses for demo
const AI_RESPONSES: Record<string, string[]> = {
  default: [
    '这是一个很好的问题！让我来详细解答一下。\n\n首先，我们需要理解问题的核心。从多个角度来分析，可以得出以下结论：\n\n1. **基础概念**：任何复杂问题都可以分解为更小的、可管理的部分\n2. **方法论**：采用系统化的思维方式，逐步推进\n3. **实践建议**：理论结合实际，不断迭代优化\n\n希望这个回答对你有帮助！如果需要更深入的讨论，请继续提问。😊',
    '我来帮你分析一下这个问题。\n\n## 思路分析\n\n从技术角度来看，这个问题涉及几个关键方面：\n\n- **可行性**：在当前条件下完全可以实现\n- **效率**：选择合适的方法可以大幅提升效率\n- **可维护性**：良好的设计是长期成功的关键\n\n```python\n# 示例代码\ndef solve_problem(input_data):\n    # 第一步：数据预处理\n    processed = preprocess(input_data)\n    # 第二步：核心逻辑\n    result = core_logic(processed)\n    return result\n```\n\n有任何疑问欢迎继续交流！',
    '非常有趣的话题！让我从不同维度来探讨：\n\n### 观点一：传统视角\n传统方法强调循序渐进，注重基础积累。这种方式虽然速度较慢，但根基扎实。\n\n### 观点二：现代视角\n现代方法更注重效率和创新，善用工具和技术可以事半功倍。\n\n### 我的建议\n> 结合两种方法的优点，在保证质量的前提下追求效率。\n\n具体来说：\n1. 先建立扎实的基础\n2. 然后引入现代工具提升效率\n3. 持续学习和调整\n\n你觉得哪种方法更适合你的情况呢？',
  ],
  coding: [
    '好的，让我来帮你写代码！\n\n```javascript\n// 快速排序算法实现\nfunction quickSort(arr) {\n  if (arr.length <= 1) return arr;\n  \n  const pivot = arr[Math.floor(arr.length / 2)];\n  const left = arr.filter(x => x < pivot);\n  const middle = arr.filter(x => x === pivot);\n  const right = arr.filter(x => x > pivot);\n  \n  return [...quickSort(left), ...middle, ...quickSort(right)];\n}\n\n// 使用示例\nconst data = [3, 6, 8, 10, 1, 2, 1];\nconsole.log(quickSort(data));\n// 输出: [1, 1, 2, 3, 6, 8, 10]\n```\n\n### 算法分析\n\n| 指标 | 复杂度 |\n|------|--------|\n| 时间（平均）| O(n log n) |\n| 时间（最坏）| O(n²) |\n| 空间 | O(n) |\n\n需要其他语言的实现或者其他算法吗？',
  ],
  creative: [
    '🌸 **春之韵**\n\n春风轻抚过山岗，\n桃花映水泛红妆。\n燕子归来寻旧梦，\n一帘烟雨润芬芳。\n\n晨露微光花影动，\n蝶舞翩跹入画中。\n若问春光何处好，\n人间处处是诗行。\n\n---\n\n这首诗以春天为主题，运用了以下修辞手法：\n- **拟人**：春风"轻抚"、燕子"寻旧梦"\n- **对仗**：词句工整，韵律和谐\n- **意象**：桃花、燕子、烟雨、晨露等经典春日意象\n\n希望你喜欢！需要修改或者换一种风格吗？✨',
  ],
};

function detectCategory(message: string): string {
  const lower = message.toLowerCase();
  if (/代码|编程|算法|函数|程序|code|python|javascript|java|排序/.test(lower)) return 'coding';
  if (/写|诗|故事|创作|小说|文章|歌/.test(lower)) return 'creative';
  return 'default';
}

export async function simulateAIResponse(userMessage: string): Promise<string> {
  const category = detectCategory(userMessage);
  const responses = AI_RESPONSES[category] || AI_RESPONSES.default;
  const response = responses[Math.floor(Math.random() * responses.length)];
  
  // Simulate streaming delay
  return response;
}

// Stream simulation - yields chunks of text
export async function* streamAIResponse(userMessage: string): AsyncGenerator<string> {
  const category = detectCategory(userMessage);
  const responses = AI_RESPONSES[category] || AI_RESPONSES.default;
  const response = responses[Math.floor(Math.random() * responses.length)];
  
  const words = response.split('');
  const chunkSize = 2;
  
  for (let i = 0; i < words.length; i += chunkSize) {
    const chunk = words.slice(i, i + chunkSize).join('');
    yield chunk;
    // Variable delay for natural feel
    const delay = Math.random() * 20 + 10;
    await new Promise(resolve => setTimeout(resolve, delay));
  }
}
