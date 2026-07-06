'use client';

import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Copy, Check, User, Bot } from 'lucide-react';
import { Message } from '@/lib/types';

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
}

export default function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  return (
    <div className={`message-appear flex gap-3 ${isUser ? 'flex-row-reverse' : ''} mb-6`}>
      {/* Avatar */}
      <div className={`flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center text-sm ${
        isUser 
          ? 'gradient-accent text-white' 
          : 'bg-[var(--bg-tertiary)] border border-[var(--border)]'
      }`}>
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4 text-[var(--accent-light)]" />}
      </div>

      {/* Message content */}
      <div className={`group relative max-w-[80%] ${isUser ? 'items-end' : 'items-start'}`}>
        <div className={`rounded-2xl px-4 py-3 ${
          isUser
            ? 'bg-[var(--user-bubble)] text-white rounded-tr-sm'
            : 'bg-[var(--ai-bubble)] border border-[var(--border)] text-[var(--text-primary)] rounded-tl-sm'
        }`}>
          {isUser ? (
            <p className="text-[0.95rem] leading-relaxed whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className="markdown-body">
              <ReactMarkdown
                components={{
                  code({ node, className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className || '');
                    const isInline = !match;
                    
                    if (isInline) {
                      return <code className={className} {...props}>{children}</code>;
                    }
                    
                    return (
                      <div className="relative group/code">
                        <div className="flex items-center justify-between px-4 py-2 bg-[#0d0d15] border-b border-[var(--border)] rounded-t-lg text-xs text-[var(--text-muted)]">
                          <span>{match[1]}</span>
                          <button
                            onClick={() => copyToClipboard(String(children).replace(/\n$/, ''))}
                            className="flex items-center gap-1 hover:text-[var(--text-primary)] transition-colors"
                          >
                            {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                            {copied ? '已复制' : '复制'}
                          </button>
                        </div>
                        <SyntaxHighlighter
                          style={oneDark}
                          language={match[1]}
                          PreTag="div"
                          customStyle={{
                            margin: 0,
                            borderRadius: '0 0 8px 8px',
                            background: '#0d0d15',
                            border: '1px solid var(--border)',
                            borderTop: 'none',
                          }}
                        >
                          {String(children).replace(/\n$/, '')}
                        </SyntaxHighlighter>
                      </div>
                    );
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>
              {isStreaming && (
                <span className="inline-block w-2 h-5 bg-[var(--accent-light)] ml-0.5 animate-pulse" />
              )}
            </div>
          )}
        </div>
        
        {/* Timestamp & actions */}
        <div className={`flex items-center gap-2 mt-1 px-1 opacity-0 group-hover:opacity-100 transition-opacity ${
          isUser ? 'flex-row-reverse' : ''
        }`}>
          <span className="text-[10px] text-[var(--text-muted)]">
            {new Date(message.timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
          </span>
          {!isUser && (
            <button
              onClick={() => copyToClipboard(message.content)}
              className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
              title="复制回答"
            >
              {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
