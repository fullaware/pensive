"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MessageBubble } from "./MessageBubble";
import { TokensPerSecond } from "./TokensPerSecond";
import api, { ChatMessage, ChatEvent } from "@/lib/api";
import { cn } from "@/lib/utils";

interface StreamingState {
  content: string;
  thinking: string;
  tokensPerSecond: number;
  isStreaming: boolean;
}

export function ChatContainer() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [streaming, setStreaming] = useState<StreamingState>({
    content: "",
    thinking: "",
    tokensPerSecond: 0,
    isStreaming: false,
  });
  const [finalStats, setFinalStats] = useState<{
    totalTokens: number;
    durationMs: number;
    avgTps: number;
  } | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, streaming.content, scrollToBottom]);

  // Auto-focus input after message is sent
  useEffect(() => {
    if (!isLoading && inputRef.current) {
      // Small delay to ensure DOM is ready
      setTimeout(() => {
        inputRef.current?.focus();
      }, 100);
    }
  }, [isLoading]);

  // Load chat history on mount and focus input
  useEffect(() => {
    const loadHistory = async () => {
      try {
        const response = await api.getChatHistory();
        setMessages(response.messages);
      } catch (error) {
        console.error("Failed to load chat history:", error);
      }
    };
    loadHistory();
    
    // Focus input on mount
    setTimeout(() => {
      inputRef.current?.focus();
    }, 200);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: "user",
      content: input.trim(),
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);
    
    // Refocus input immediately after clearing
    setTimeout(() => {
      inputRef.current?.focus();
    }, 10);
    setFinalStats(null);
    setStreaming({
      content: "",
      thinking: "",
      tokensPerSecond: 0,
      isStreaming: true,
    });

    try {
      for await (const event of api.streamChat(userMessage.content)) {
        handleStreamEvent(event);
      }
    } catch (error) {
      console.error("Chat error:", error);
      setStreaming((prev) => ({
        ...prev,
        content: `Error: ${error instanceof Error ? error.message : "Unknown error"}`,
        isStreaming: false,
      }));
    } finally {
      // Finalize the message
      setStreaming((prev) => {
        if (prev.content) {
          const assistantMessage: ChatMessage = {
            id: `msg-${Date.now()}`,
            role: "assistant",
            content: prev.content,
            timestamp: new Date().toISOString(),
            thinking: prev.thinking || undefined,
          };
          setMessages((msgs) => [...msgs, assistantMessage]);
        }
        return {
          content: "",
          thinking: "",
          tokensPerSecond: 0,
          isStreaming: false,
        };
      });
      setIsLoading(false);
      
      // Refocus input after message is sent
      setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
    }
  };

  const handleStreamEvent = (event: ChatEvent) => {
    switch (event.type) {
      case "thinking":
        setStreaming((prev) => ({
          ...prev,
          thinking: prev.thinking + (event.content || ""),
        }));
        break;
      case "token":
        setStreaming((prev) => ({
          ...prev,
          content: prev.content + (event.content || ""),
          tokensPerSecond: event.tokens_per_second || prev.tokensPerSecond,
        }));
        break;
      case "done":
        setFinalStats({
          totalTokens: event.total_tokens || 0,
          durationMs: event.duration_ms || 0,
          avgTps: event.avg_tps || 0,
        });
        break;
      case "error":
        setStreaming((prev) => ({
          ...prev,
          content: `Error: ${event.message || "Unknown error"}`,
          isStreaming: false,
        }));
        break;
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto space-y-6">
          {messages.length === 0 && !streaming.isStreaming && (
            <div className="text-center py-20">
              <h2 className="text-2xl font-semibold text-foreground mb-2">
                Welcome to Pensive
              </h2>
              <p className="text-muted-foreground">
                Your AI assistant with infinite memory. Start a conversation below.
              </p>
            </div>
          )}

          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}

          {/* Streaming message */}
          {streaming.isStreaming && (
            <MessageBubble
              message={{
                id: "streaming",
                role: "assistant",
                content: streaming.content,
                timestamp: new Date().toISOString(),
                thinking: streaming.thinking || undefined,
              }}
              isStreaming
            />
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area */}
      <div className="border-t border-border bg-background/80 backdrop-blur-sm p-4">
        <div className="max-w-3xl mx-auto">
          {/* Stats Bar */}
          {(streaming.isStreaming || finalStats) && (
            <div className="mb-3 flex items-center justify-center gap-4 text-sm">
              <TokensPerSecond
                tps={streaming.isStreaming ? streaming.tokensPerSecond : (finalStats?.avgTps || 0)}
                isStreaming={streaming.isStreaming}
              />
              {finalStats && !streaming.isStreaming && (
                <span className="text-muted-foreground">
                  {finalStats.totalTokens} tokens in {(finalStats.durationMs / 1000).toFixed(1)}s
                </span>
              )}
            </div>
          )}

          <form onSubmit={handleSubmit} className="relative">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message Pensive..."
              disabled={isLoading}
              rows={1}
              className={cn(
                "w-full resize-none rounded-xl border border-border bg-secondary/50 px-4 py-3 pr-12",
                "text-foreground placeholder:text-muted-foreground",
                "focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background",
                "disabled:cursor-not-allowed disabled:opacity-50",
                "min-h-[52px] max-h-[200px]"
              )}
              style={{
                height: "auto",
                minHeight: "52px",
              }}
              onInput={(e) => {
                const target = e.target as HTMLTextAreaElement;
                target.style.height = "auto";
                target.style.height = `${Math.min(target.scrollHeight, 200)}px`;
              }}
            />
            <Button
              type="submit"
              size="icon"
              disabled={!input.trim() || isLoading}
              className="absolute right-2 bottom-2 h-8 w-8 rounded-lg"
            >
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </form>

          <p className="text-xs text-muted-foreground text-center mt-2">
            Pensive remembers your conversations. Press Enter to send, Shift+Enter for new line.
          </p>
        </div>
      </div>
    </div>
  );
}


