'use client';

import React from 'react';
import { Menu, PanelLeftClose } from 'lucide-react';

interface ChatHeaderProps {
  title: string;
  model: string;
  onToggleSidebar: () => void;
  sidebarOpen: boolean;
  messageCount: number;
}

const MODEL_NAMES: Record<string, string> = {
  'gpt-4': 'GPT-4',
  'gpt-3.5': 'GPT-3.5',
  'claude-3': 'Claude 3',
  'local': '本地模型',
};

export default function ChatHeader({
  title,
  model,
  onToggleSidebar,
  sidebarOpen,
  messageCount,
}: ChatHeaderProps) {
  return (
    <div className="flex-shrink-0 h-14 flex items-center justify-between px-4 border-b border-[var(--border)] bg-[var(--bg-secondary)]/80 backdrop-blur-xl">
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="p-2 rounded-lg hover:bg-[var(--bg-hover)] text-[var(--text-secondary)] transition-colors"
        >
          {sidebarOpen ? <PanelLeftClose className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
        <div>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h2>
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--success)] animate-pulse" />
            <span className="text-[10px] text-[var(--text-muted)]">
              {MODEL_NAMES[model] || model} · {messageCount} 条消息
            </span>
          </div>
        </div>
      </div>
      
      <div className="flex items-center gap-2">
        <span className="px-2.5 py-1 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--border)] text-[10px] text-[var(--text-muted)]">
          {MODEL_NAMES[model] || model}
        </span>
      </div>
    </div>
  );
}
