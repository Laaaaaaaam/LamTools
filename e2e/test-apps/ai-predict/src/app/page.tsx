'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import Sidebar from '@/components/Sidebar';
import ChatHeader from '@/components/ChatHeader';
import ChatInput from '@/components/ChatInput';
import MessageBubble from '@/components/MessageBubble';
import TypingIndicator from '@/components/TypingIndicator';
import WelcomeScreen from '@/components/WelcomeScreen';
import { Conversation, Message } from '@/lib/types';
import {
  loadConversations,
  saveConversations,
  loadActiveId,
  saveActiveId,
  createConversation,
  createMessage,
  generateTitle,
  streamAIResponse,
} from '@/lib/utils';

export default function Home() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [selectedModel, setSelectedModel] = useState('gpt-4');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef(false);

  // Load data from localStorage
  useEffect(() => {
    const loaded = loadConversations();
    const savedActiveId = loadActiveId();
    setConversations(loaded);
    if (savedActiveId && loaded.find(c => c.id === savedActiveId)) {
      setActiveId(savedActiveId);
    }
  }, []);

  // Save conversations when they change
  useEffect(() => {
    if (conversations.length > 0) {
      saveConversations(conversations);
    }
  }, [conversations]);

  // Save active ID
  useEffect(() => {
    if (activeId) saveActiveId(activeId);
  }, [activeId]);

  // Auto scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversations, streamingContent]);

  const activeConversation = conversations.find(c => c.id === activeId);
  const messages = activeConversation?.messages || [];

  const handleNewConversation = useCallback(() => {
    const conv = createConversation(selectedModel);
    setConversations(prev => [conv, ...prev]);
    setActiveId(conv.id);
    setStreamingContent('');
  }, [selectedModel]);

  const handleSelectConversation = useCallback((id: string) => {
    setActiveId(id);
    setStreamingContent('');
  }, []);

  const handleDeleteConversation = useCallback((id: string) => {
    setConversations(prev => {
      const filtered = prev.filter(c => c.id !== id);
      saveConversations(filtered);
      return filtered;
    });
    if (activeId === id) {
      const remaining = conversations.filter(c => c.id !== id);
      setActiveId(remaining.length > 0 ? remaining[0].id : null);
      setStreamingContent('');
    }
  }, [activeId, conversations]);

  const handleSend = useCallback(async (content: string) => {
    if (isStreaming) return;

    let currentActiveId = activeId;
    let conv = conversations.find(c => c.id === currentActiveId);

    // Create new conversation if none active
    if (!conv) {
      conv = createConversation(selectedModel);
      currentActiveId = conv.id;
      setConversations(prev => [conv!, ...prev]);
      setActiveId(currentActiveId);
    }

    const userMessage = createMessage('user', content);
    const updatedMessages = [...conv.messages, userMessage];
    const title = conv.messages.length === 0 ? generateTitle(content) : conv.title;

    setConversations(prev =>
      prev.map(c =>
        c.id === currentActiveId
          ? { ...c, messages: updatedMessages, title, updatedAt: Date.now() }
          : c
      )
    );

    // Start streaming
    setIsStreaming(true);
    setStreamingContent('');
    abortRef.current = false;

    let fullContent = '';

    try {
      const stream = streamAIResponse(content);
      for await (const chunk of stream) {
        if (abortRef.current) break;
        fullContent += chunk;
        setStreamingContent(fullContent);
      }
    } catch (e) {
      console.error('Streaming error:', e);
    }

    // Add assistant message
    if (fullContent) {
      const assistantMessage = createMessage('assistant', fullContent);
      setConversations(prev =>
        prev.map(c =>
          c.id === currentActiveId
            ? {
                ...c,
                messages: [...updatedMessages, assistantMessage],
                updatedAt: Date.now(),
              }
            : c
        )
      );
    }

    setIsStreaming(false);
    setStreamingContent('');
  }, [activeId, conversations, isStreaming, selectedModel]);

  const handleStop = useCallback(() => {
    abortRef.current = true;
  }, []);

  const handleSelectSuggestion = useCallback((prompt: string) => {
    handleSend(prompt);
  }, [handleSend]);

  return (
    <div className="h-screen flex overflow-hidden gradient-bg">
      {/* Sidebar */}
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={handleSelectConversation}
        onNew={handleNewConversation}
        onDelete={handleDeleteConversation}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
      />

      {/* Main chat area */}
      <main className="flex-1 flex flex-col min-w-0">
        {activeConversation ? (
          <>
            <ChatHeader
              title={activeConversation.title}
              model={activeConversation.model}
              onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
              sidebarOpen={sidebarOpen}
              messageCount={messages.length}
            />

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-4 py-6">
              <div className="max-w-3xl mx-auto">
                {messages.map((msg, index) => (
                  <MessageBubble
                    key={msg.id}
                    message={msg}
                    isStreaming={isStreaming && index === messages.length - 1 && msg.role === 'assistant'}
                  />
                ))}

                {/* Streaming content */}
                {isStreaming && streamingContent && (
                  <MessageBubble
                    message={{
                      id: 'streaming',
                      role: 'assistant',
                      content: streamingContent,
                      timestamp: Date.now(),
                    }}
                    isStreaming={true}
                  />
                )}

                {/* Typing indicator */}
                {isStreaming && !streamingContent && <TypingIndicator />}

                <div ref={messagesEndRef} />
              </div>
            </div>

            <ChatInput
              onSend={handleSend}
              onStop={handleStop}
              isStreaming={isStreaming}
            />
          </>
        ) : (
          <>
            <ChatHeader
              title="AI Chat"
              model={selectedModel}
              onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
              sidebarOpen={sidebarOpen}
              messageCount={0}
            />
            <WelcomeScreen onSelectSuggestion={handleSelectSuggestion} />
            <ChatInput
              onSend={handleSend}
              onStop={handleStop}
              isStreaming={isStreaming}
            />
          </>
        )}
      </main>
    </div>
  );
}
