"use client";

import { useState } from "react";
import { User, Bot, ChevronDown, ChevronUp, Copy, Check } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { ChatMessage } from "@/lib/api";
import { cn, formatRelativeTime } from "@/lib/utils";
import { ThinkingCollapsible } from "./ThinkingCollapsible";

interface MessageBubbleProps {
  message: ChatMessage;
  isStreaming?: boolean;
}

export function MessageBubble({ message, isStreaming = false }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const [copiedCode, setCopiedCode] = useState<string | null>(null);

  const copyToClipboard = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedCode(code);
      setTimeout(() => setCopiedCode(null), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  return (
    <div
      className={cn(
        "message-appear flex gap-4",
        isUser ? "flex-row-reverse" : "flex-row"
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-secondary text-secondary-foreground"
        )}
      >
        {isUser ? (
          <User className="w-4 h-4" />
        ) : (
          <Bot className="w-4 h-4" />
        )}
      </div>

      {/* Content */}
      <div
        className={cn(
          "flex-1 max-w-[85%] space-y-2",
          isUser ? "text-right" : "text-left"
        )}
      >
        {/* Thinking section for assistant */}
        {!isUser && message.thinking && (
          <ThinkingCollapsible content={message.thinking} />
        )}

        {/* Message content */}
        <div
          className={cn(
            "inline-block rounded-2xl px-4 py-2.5",
            isUser
              ? "bg-primary text-primary-foreground rounded-tr-sm"
              : "bg-secondary text-secondary-foreground rounded-tl-sm",
            isStreaming && !isUser && "streaming-cursor"
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className="prose prose-sm max-w-none">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({ node, className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className || "");
                    const codeString = String(children).replace(/\n$/, "");
                    const isInline = !match && !codeString.includes("\n");

                    if (isInline) {
                      return (
                        <code
                          className="bg-background/50 px-1.5 py-0.5 rounded text-sm"
                          {...props}
                        >
                          {children}
                        </code>
                      );
                    }

                    return (
                      <div className="relative group my-3">
                        <div className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={() => copyToClipboard(codeString)}
                            className="p-1.5 rounded bg-background/80 hover:bg-background text-foreground/70 hover:text-foreground"
                          >
                            {copiedCode === codeString ? (
                              <Check className="w-4 h-4 text-blue-500" />
                            ) : (
                              <Copy className="w-4 h-4" />
                            )}
                          </button>
                        </div>
                        <SyntaxHighlighter
                          style={oneDark}
                          language={match?.[1] || "text"}
                          PreTag="div"
                          className="rounded-lg !my-0 text-sm"
                          customStyle={{
                            margin: 0,
                            padding: "1rem",
                            background: "hsl(var(--background))",
                          }}
                        >
                          {codeString}
                        </SyntaxHighlighter>
                      </div>
                    );
                  },
                  p({ children }) {
                    return <p className="mb-2 last:mb-0">{children}</p>;
                  },
                  ul({ children }) {
                    return <ul className="list-disc pl-4 mb-2">{children}</ul>;
                  },
                  ol({ children }) {
                    return <ol className="list-decimal pl-4 mb-2">{children}</ol>;
                  },
                  li({ children }) {
                    return <li className="mb-1">{children}</li>;
                  },
                  a({ href, children }) {
                    return (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary hover:underline"
                      >
                        {children}
                      </a>
                    );
                  },
                  blockquote({ children }) {
                    return (
                      <blockquote className="border-l-2 border-primary/50 pl-3 italic text-muted-foreground my-2">
                        {children}
                      </blockquote>
                    );
                  },
                  table({ children }) {
                    return (
                      <div className="overflow-x-auto my-4">
                        <table className="min-w-full border-collapse border border-border rounded-lg">
                          {children}
                        </table>
                      </div>
                    );
                  },
                  thead({ children }) {
                    return (
                      <thead className="bg-secondary/50">
                        {children}
                      </thead>
                    );
                  },
                  tbody({ children }) {
                    return (
                      <tbody className="divide-y divide-border">
                        {children}
                      </tbody>
                    );
                  },
                  tr({ children }) {
                    return (
                      <tr className="border-b border-border hover:bg-secondary/30 transition-colors">
                        {children}
                      </tr>
                    );
                  },
                  th({ children }) {
                    return (
                      <th className="border border-border px-4 py-2 text-left font-semibold text-foreground">
                        {children}
                      </th>
                    );
                  },
                  td({ children }) {
                    return (
                      <td className="border border-border px-4 py-2 text-foreground">
                        {children}
                      </td>
                    );
                  },
                  h1({ children }) {
                    return (
                      <h1 className="text-2xl font-bold text-foreground mt-4 mb-2 first:mt-0">
                        {children}
                      </h1>
                    );
                  },
                  h2({ children }) {
                    return (
                      <h2 className="text-xl font-semibold text-foreground mt-3 mb-2 first:mt-0">
                        {children}
                      </h2>
                    );
                  },
                  h3({ children }) {
                    return (
                      <h3 className="text-lg font-semibold text-foreground mt-3 mb-2 first:mt-0">
                        {children}
                      </h3>
                    );
                  },
                  h4({ children }) {
                    return (
                      <h4 className="text-base font-semibold text-foreground mt-2 mb-1 first:mt-0">
                        {children}
                      </h4>
                    );
                  },
                  hr() {
                    return (
                      <hr className="my-4 border-border" />
                    );
                  },
                  strong({ children }) {
                    return (
                      <strong className="font-semibold text-foreground">
                        {children}
                      </strong>
                    );
                  },
                  em({ children }) {
                    return (
                      <em className="italic text-foreground">
                        {children}
                      </em>
                    );
                  },
                }}
              >
                {message.content || (isStreaming ? "" : "...")}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {/* Timestamp */}
        <p className="text-xs text-muted-foreground">
          {formatRelativeTime(message.timestamp)}
        </p>
      </div>
    </div>
  );
}


