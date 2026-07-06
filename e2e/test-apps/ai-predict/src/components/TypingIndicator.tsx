'use client';

import React from 'react';

export default function TypingIndicator() {
  return (
    <div className="message-appear flex gap-3 mb-6">
      <div className="flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center bg-[var(--bg-tertiary)] border border-[var(--border)]">
        <span className="text-sm">🤖</span>
      </div>
      <div className="bg-[var(--ai-bubble)] border border-[var(--border)] rounded-2xl rounded-tl-sm px-4 py-3">
        <div className="flex items-center gap-1.5">
          <span className="typing-dot animate-pulse-dot" />
          <span className="typing-dot animate-pulse-dot" />
          <span className="typing-dot animate-pulse-dot" />
        </div>
      </div>
    </div>
  );
}
