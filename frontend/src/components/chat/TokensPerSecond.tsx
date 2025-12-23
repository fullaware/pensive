"use client";

import { Zap } from "lucide-react";
import { cn } from "@/lib/utils";

interface TokensPerSecondProps {
  tps: number;
  isStreaming?: boolean;
}

export function TokensPerSecond({ tps, isStreaming = false }: TokensPerSecondProps) {
  // Color based on speed - using blue tones
  const getColor = () => {
    if (tps >= 50) return "text-blue-400";
    if (tps >= 25) return "text-blue-500";
    if (tps >= 10) return "text-blue-600";
    return "text-muted-foreground";
  };

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-1 rounded-full",
        "bg-secondary/50 text-sm font-medium",
        getColor(),
        isStreaming && "animate-pulse"
      )}
    >
      <Zap className="w-3.5 h-3.5" />
      <span>{tps.toFixed(1)}</span>
      <span className="text-muted-foreground text-xs">tok/s</span>
    </div>
  );
}


