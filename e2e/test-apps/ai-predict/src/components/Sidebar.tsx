'use client';

import React from 'react';
import { MessageSquarePlus, Trash2, MessageCircle, ChevronLeft, Settings, Sparkles } from 'lucide-react';
import { Conversation } from '@/lib/types';
import { formatTime } from '@/lib/utils';

interface SidebarProps {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  isOpen: boolean;
  onToggle: () => void;
  selectedModel: string;
  onModelChange: (model: string) => void;
}

export default function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  isOpen,
  onToggle,
  selectedModel,
  onModelChange,
}: SidebarProps) {
  const models = [
    { id: 'gpt-4', name: 'GPT-4', icon: '🧠' },
    { id: 'gpt-3.5', name: 'GPT-3.5', icon: '⚡' },
    { id: 'claude-3', name: 'Claude 3', icon: '🎨' },
    { id: 'local', name: '本地模型', icon: '🔒' },
  ];

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 lg:hidden"
          onClick={onToggle}
        />
      )}

      <aside
        className={`fixed lg:relative z-40 h-full flex flex-col bg-[var(--bg-secondary)] border-r border-[var(--border)] sidebar-transition ${
          isOpen ? 'w-72 translate-x-0' : 'w-0 -translate-x-full lg:translate-x-0 lg:w-0'
        } overflow-hidden`}
      >
        {/* Header */}
        <div className="flex-shrink-0 p-4 border-b border-[var(--border)]">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg gradient-accent flex items-center justify-center">
                <Sparkles className="w-4 h-4 text-white" />
              </div>
              <h1 className="text-lg font-bold glow-text">AI Chat</h1>
            </div>
            <button
              onClick={onToggle}
              className="p-1.5 rounded-lg hover:bg-[var(--bg-hover)] text-[var(--text-secondary)] transition-colors"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
          </div>

          {/* New chat button */}
          <button
            onClick={onNew}
            className="w-full flex items-center gap-2 px-4 py-2.5 rounded-xl border border-dashed border-[var(--border)] hover:border-[var(--accent)] hover:bg-[var(--accent)]/10 text-[var(--text-secondary)] hover:text-[var(--accent-light)] transition-all duration-200"
          >
            <MessageSquarePlus className="w-4 h-4" />
            <span className="text-sm font-medium">新建对话</span>
          </button>
        </div>

        {/* Model selector */}
        <div className="flex-shrink-0 px-4 py-3 border-b border-[var(--border)]">
          <div className="flex items-center gap-2 mb-2">
            <Settings className="w-3.5 h-3.5 text-[var(--text-muted)]" />
            <span className="text-xs text-[var(--text-muted)] uppercase tracking-wider">模型选择</span>
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            {models.map((model) => (
              <button
                key={model.id}
                onClick={() => onModelChange(model.id)}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs transition-all duration-200 ${
                  selectedModel === model.id
                    ? 'bg-[var(--accent)]/20 text-[var(--accent-light)] border border-[var(--accent)]/30'
                    : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:bg-[var(--bg-hover)] border border-transparent'
                }`}
              >
                <span>{model.icon}</span>
                <span>{model.name}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto p-2">
          {conversations.length === 0 ? (
            <div className="text-center py-8 text-[var(--text-muted)]">
              <MessageCircle className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p className="text-sm">暂无对话</p>
              <p className="text-xs mt-1">点击上方按钮开始</p>
            </div>
          ) : (
            <div className="space-y-1">
              {conversations.map((conv) => (
                <div
                  key={conv.id}
                  className={`group flex items-center gap-2 px-3 py-2.5 rounded-xl cursor-pointer transition-all duration-200 ${
                    activeId === conv.id
                      ? 'bg-[var(--accent)]/15 text-[var(--text-primary)] border border-[var(--accent)]/20'
                      : 'hover:bg-[var(--bg-hover)] text-[var(--text-secondary)]'
                  }`}
                  onClick={() => onSelect(conv.id)}
                >
                  <MessageCircle className="w-4 h-4 flex-shrink-0 opacity-50" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm truncate">{conv.title}</p>
                    <p className="text-[10px] text-[var(--text-muted)] mt-0.5">
                      {conv.messages.length} 条消息 · {formatTime(conv.updatedAt)}
                    </p>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(conv.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-[var(--danger)]/20 text-[var(--text-muted)] hover:text-[var(--danger)] transition-all"
                    title="删除对话"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex-shrink-0 p-4 border-t border-[var(--border)]">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full gradient-accent flex items-center justify-center text-white text-xs font-bold">
              U
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-[var(--text-primary)]">用户</p>
              <p className="text-[10px] text-[var(--text-muted)]">免费版</p>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
