export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  createdAt: number;
  updatedAt: number;
  model: string;
}

export interface AIModel {
  id: string;
  name: string;
  description: string;
  icon: string;
}

export const AI_MODELS: AIModel[] = [
  { id: 'gpt-4', name: 'GPT-4', description: '最强大的推理能力', icon: '🧠' },
  { id: 'gpt-3.5', name: 'GPT-3.5', description: '快速响应，性价比高', icon: '⚡' },
  { id: 'claude-3', name: 'Claude 3', description: '深度理解与创作', icon: '🎨' },
  { id: 'local', name: '本地模型', description: '离线运行，隐私安全', icon: '🔒' },
];

export const SUGGESTIONS = [
  { icon: '💡', title: '创意写作', prompt: '帮我写一首关于春天的诗' },
  { icon: '💻', title: '编程助手', prompt: '用Python实现一个快速排序算法' },
  { icon: '📚', title: '知识问答', prompt: '解释一下量子计算的基本原理' },
  { icon: '🎯', title: '解决问题', prompt: '如何提高工作效率？给出5个实用建议' },
];
