"use client";

import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, MessageSquare, Calendar, Clock } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useRequireAdmin } from "@/lib/auth";
import api from "@/lib/api";
import { formatDateTime, formatRelativeTime } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface SessionMessage {
  id: string;
  role: string;
  content: string;
  timestamp: string;
}

interface Session {
  id: string;
  user_id: string;
  username: string;
  started_at: string;
  ended_at: string | null;
  message_count: number;
  messages: SessionMessage[];
}

function SessionsContent() {
  const { isAdmin, isLoading } = useRequireAdmin();
  const router = useRouter();
  const searchParams = useSearchParams();
  const userId = searchParams.get("user_id");
  const username = searchParams.get("username") || "User";

  const [sessions, setSessions] = useState<Session[]>([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [expandedSessions, setExpandedSessions] = useState<Set<string>>(
    new Set()
  );
  const [days, setDays] = useState(30);

  useEffect(() => {
    if (isAdmin && userId) {
      loadSessions();
    }
  }, [isAdmin, userId, days]);

  const loadSessions = async () => {
    if (!userId) return;
    setIsLoadingSessions(true);
    try {
      const data = await api.getUserSessions(userId, days);
      setSessions(data);
    } catch (error) {
      console.error("Failed to load sessions:", error);
    } finally {
      setIsLoadingSessions(false);
    }
  };

  const toggleSession = (sessionId: string) => {
    setExpandedSessions((prev) => {
      const next = new Set(prev);
      if (next.has(sessionId)) {
        next.delete(sessionId);
      } else {
        next.add(sessionId);
      }
      return next;
    });
  };

  if (isLoading || isLoadingSessions) {
    return (
      <div className="min-h-screen gradient-bg flex items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    );
  }

  if (!isAdmin) return null;

  if (!userId) {
    return (
      <div className="min-h-screen gradient-bg">
        <header className="border-b border-border/50 bg-background/80 backdrop-blur-sm">
          <div className="max-w-6xl mx-auto px-4 h-14 flex items-center">
            <Button variant="ghost" size="sm" onClick={() => router.push("/admin/users")}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Users
            </Button>
          </div>
        </header>
        <main className="max-w-6xl mx-auto px-4 py-8">
          <Card>
            <CardContent className="pt-6">
              <p className="text-muted-foreground">
                No user selected. Please select a user from the Users page.
              </p>
            </CardContent>
          </Card>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen gradient-bg">
      {/* Header */}
      <header className="border-b border-border/50 bg-background/80 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" onClick={() => router.push("/admin/users")}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Users
            </Button>
            <h1 className="text-xl font-semibold text-foreground">
              Sessions — {username}
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-sm text-muted-foreground">Last</label>
            <div className="relative">
              <Select onValueChange={(v) => setDays(Number(v))} value={String(days)}>
                <SelectTrigger className="w-[140px] h-8">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="7">7 days</SelectItem>
                  <SelectItem value="30">30 days</SelectItem>
                  <SelectItem value="90">90 days</SelectItem>
                  <SelectItem value="365">1 year</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        {sessions.length === 0 ? (
          <Card>
            <CardContent className="pt-6">
              <p className="text-center text-muted-foreground">
                No sessions found for this user in the selected time period.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {sessions.map((session) => {
              const isExpanded = expandedSessions.has(session.id);
              return (
                <Card key={session.id}>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2">
                          <Calendar className="w-4 h-4 text-muted-foreground" />
                          <span className="text-sm font-medium">
                            {formatDateTime(session.started_at)}
                          </span>
                        </div>
                        {session.ended_at && (
                          <div className="flex items-center gap-2">
                            <Clock className="w-4 h-4 text-muted-foreground" />
                            <span className="text-sm text-muted-foreground">
                              Ended: {formatDateTime(session.ended_at)}
                            </span>
                          </div>
                        )}
                        <div className="flex items-center gap-2">
                          <MessageSquare className="w-4 h-4 text-muted-foreground" />
                          <span className="text-sm text-muted-foreground">
                            {session.message_count} messages
                          </span>
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => toggleSession(session.id)}
                      >
                        {isExpanded ? "Collapse" : "Expand"}
                      </Button>
                    </div>
                  </CardHeader>
                  {isExpanded && (
                    <CardContent>
                      <div className="space-y-3 pt-4 border-t border-border/50">
                        {session.messages.length === 0 ? (
                          <p className="text-sm text-muted-foreground">
                            No messages in this session.
                          </p>
                        ) : (
                          session.messages.map((msg) => (
                            <div
                              key={msg.id}
                              className={cn(
                                "p-3 rounded-lg",
                                msg.role === "user"
                                  ? "bg-primary/10 text-primary-foreground ml-8"
                                  : "bg-secondary/30 text-secondary-foreground mr-8"
                              )}
                            >
                              <div className="flex items-start justify-between mb-1">
                                <span className="text-xs font-medium">
                                  {msg.role === "user" ? "User" : "Assistant"}
                                </span>
                                <span className="text-xs text-muted-foreground">
                                  {formatDateTime(msg.timestamp)}
                                </span>
                              </div>
                              <p className="text-sm whitespace-pre-wrap">
                                {msg.content}
                              </p>
                            </div>
                          ))
                        )}
                      </div>
                    </CardContent>
                  )}
                </Card>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}

export default function SessionsPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen gradient-bg flex items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    }>
      <SessionsContent />
    </Suspense>
  );
}

