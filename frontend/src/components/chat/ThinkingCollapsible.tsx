"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Brain } from "lucide-react";
import { cn } from "@/lib/utils";

interface ThinkingCollapsibleProps {
  content: string;
  defaultOpen?: boolean;
}

export function ThinkingCollapsible({
  content,
  defaultOpen = false,
}: ThinkingCollapsibleProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  if (!content) return null;

  return (
    <div className="rounded-lg border border-border/50 bg-muted/30 overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "w-full flex items-center justify-between px-3 py-2",
          "text-sm text-muted-foreground hover:text-foreground",
          "hover:bg-muted/50 transition-colors"
        )}
      >
        <span className="flex items-center gap-2">
          <Brain className="w-4 h-4" />
          <span>Thinking...</span>
        </span>
        {isOpen ? (
          <ChevronUp className="w-4 h-4" />
        ) : (
          <ChevronDown className="w-4 h-4" />
        )}
      </button>

      {isOpen && (
        <div className="px-3 py-2 border-t border-border/50">
          <div className="text-sm text-muted-foreground whitespace-pre-wrap font-mono">
            {content}
          </div>
        </div>
      )}
    </div>
  );
}


