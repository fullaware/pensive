"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Settings, LogOut, LayoutDashboard } from "lucide-react";
import { ChatContainer } from "@/components/chat/ChatContainer";
import { Button } from "@/components/ui/button";
import { useAuth, useRequireAuth } from "@/lib/auth";

export default function HomePage() {
  const { isAuthenticated, isLoading } = useRequireAuth();
  const { user, isAdmin, logout } = useAuth();
  const router = useRouter();

  if (isLoading) {
    return (
      <div className="min-h-screen gradient-bg flex items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null; // Will redirect in useRequireAuth
  }

  return (
    <div className="min-h-screen gradient-bg flex flex-col">
      {/* Sticky Header - Always visible */}
      <header className="sticky top-0 z-50 border-b border-border/50 bg-background/95 backdrop-blur-sm">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold text-foreground">
              {user?.assistant_name || "Pensive"}
            </h1>
            <span className="text-sm text-muted-foreground">
              {user?.display_name}
            </span>
            {user?.role === "admin" && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                Admin
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => router.push("/settings")}
            >
              <Settings className="w-4 h-4 mr-2" />
              Settings
            </Button>
            {isAdmin && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => router.push("/admin")}
              >
                <LayoutDashboard className="w-4 h-4 mr-2" />
                Admin
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={logout}>
              <LogOut className="w-4 h-4 mr-2" />
              Logout
            </Button>
          </div>
        </div>
      </header>

      {/* Main Chat Area */}
      <main className="flex-1 overflow-hidden">
        <ChatContainer />
      </main>
    </div>
  );
}


