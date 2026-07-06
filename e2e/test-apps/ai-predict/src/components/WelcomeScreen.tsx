'use client';

import React from 'react';
import { SUGGESTIONS } from '@/lib/types';
import { Sparkles } from 'lucide-react';

interface WelcomeScreenProps {
  onSelectSuggestion: (prompt: string) => void;
}

export default function WelcomeScreen({ onSelectSuggestion }: WelcomeScreenProps) {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-2xl w-full text-center animate-fade-in">
        {/* Logo */}
        <div className="mb-8">
          <div className="w-20 h-20 mx-auto rounded-2xl gradient-accent flex items-center justify-center mb-6 shadow-lg shadow-[var(--accent-glow)]">
            <Sparkles className="w-10 h-10 text-white" />
          </div>
          <h2 className="text-3xl font-bold mb-3">
            <span className="glow-text">你好，</span>
            <span className="text-[var(--accent-light)]">有什么可以帮你？</span>
          </h2>
          <p className="text-[var(--text-secondary)] text-base">
            我是一个AI对话助手，可以帮你回答问题、编写代码、创意写作等
          </p>
        </div>

        {/* Suggestion cards */}
        <div className="grid grid-cols-2 gap-3 max-w-lg mx-auto">
          {SUGGESTIONS.map((suggestion, index) => (
            <button
              key={index}
              onClick={() => onSelectSuggestion(suggestion.prompt)}
              className="group text-left p-4 rounded-xl bg-[var(--bg-tertiary)] border border-[var(--border)] hover:border-[var(--accent)]/50 hover:bg-[var(--bg-hover)] transition-all duration-300 hover:shadow-lg hover:shadow-[var(--accent-glow)]"
              style={{ animationDelay: `${index * 100}ms` }}
            >
              <span className="text-2xl mb-2 block">{suggestion.icon}</span>
              <p className="text-sm font-medium text-[var(--text-primary)] mb-1 group-hover:text-[var(--accent-light)] transition-colors">
                {suggestion.title}
              </p>
              <p className="text-xs text-[var(--text-muted)] line-clamp-2">
                {suggestion.prompt}
              </p>
            </button>
          ))}
        </div>

        {/* Feature badges */}
        <div className="flex items-center justify-center gap-4 mt-8">
          {['智能对话', '代码生成', '创意写作', '知识问答'].map((feat) => (
            <span
              key={feat}
              className="px-3 py-1 rounded-full bg-[var(--bg-tertiary)] border border-[var(--border)] text-xs text-[var(--text-secondary)]"
            >
              {feat}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
