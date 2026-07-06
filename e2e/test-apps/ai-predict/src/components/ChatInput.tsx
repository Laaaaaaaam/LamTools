'use client';

import React, { useState, useRef, useEffect, KeyboardEvent } from 'react';
import { Send, Square, Sparkles } from 'lucide-react';

interface ChatInputProps {
  onSend: (message: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
}

export default function ChatInput({ onSend, onStop, isStreaming, disabled }: ChatInputProps) {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + 'px';
    }
  }, [input]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="border-t border-[var(--border)] bg-[var(--bg-secondary)]/80 backdrop-blur-xl p-4">
      <div className="max-w-3xl mx-auto">
        <div className="relative flex items-end gap-3 bg-[var(--bg-tertiary)] rounded-2xl border border-[var(--border)] px-4 py-3 focus-within:border-[var(--accent)] focus-within:shadow-[0_0_15px_var(--accent-glow)] transition-all duration-300">
          <Sparkles className="w-5 h-5 text-[var(--accent-light)] mb-1 flex-shrink-0 opacity-60" />
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入你的问题... (Enter 发送, Shift+Enter 换行)"
            rows={1}
            disabled={disabled}
            className="flex-1 bg-transparent text-[var(--text-primary)] placeholder-[var(--text-muted)] resize-none outline-none text-[0.95rem] leading-relaxed min-h-[24px] max-h-[200px]"
          />
          {isStreaming ? (
            <button
              onClick={onStop}
              className="flex-shrink-0 w-9 h-9 flex items-center justify-center rounded-xl bg-[var(--danger)] hover:bg-red-500 text-white transition-all duration-200 hover:scale-105 mb-0.5"
              title="停止生成"
            >
              <Square className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim() || disabled}
              className="flex-shrink-0 w-9 h-9 flex items-center justify-center rounded-xl gradient-accent text-white transition-all duration-200 hover:scale-105 disabled:opacity-30 disabled:hover:scale-100 disabled:cursor-not-allowed mb-0.5"
              title="发送消息"
            >
              <Send className="w-4 h-4" />
            </button>
          )}
        </div>
        <p className="text-center text-[var(--text-muted)] text-xs mt-2">
          AI 回答仅供参考，请注意甄别信息的准确性
        </p>
      </div>
    </div>
  );
}
