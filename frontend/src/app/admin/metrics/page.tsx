"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Activity, Users, MessageSquare, Zap } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useRequireAdmin } from "@/lib/auth";
import api from "@/lib/api";
import { cn } from "@/lib/utils";

interface MetricDataPoint {
  timestamp: string;
  messages_count: number;
  tokens_generated: number;
  avg_response_time_ms: number;
  unique_users: number;
}

export default function MetricsPage() {
  const { isAdmin, isLoading } = useRequireAdmin();
  const router = useRouter();
  const [period, setPeriod] = useState<"day" | "week" | "month">("week");
  const [realtimeMetrics, setRealtimeMetrics] = useState<{
    tokens_per_second: number;
    total_tokens_generated: number;
    active_users: number;
    requests_today: number;
  } | null>(null);
  const [historyData, setHistoryData] = useState<MetricDataPoint[]>([]);
  const [isLoadingMetrics, setIsLoadingMetrics] = useState(true);

  useEffect(() => {
    if (isAdmin) {
      loadMetrics();
    }
  }, [isAdmin, period]);

  const loadMetrics = async () => {
    setIsLoadingMetrics(true);
    try {
      const [realtime, history] = await Promise.all([
        api.getRealtimeMetrics(),
        api.getMetricsHistory(period),
      ]);
      setRealtimeMetrics(realtime);
      setHistoryData(history.data_points);
    } catch (error) {
      console.error("Failed to load metrics:", error);
    } finally {
      setIsLoadingMetrics(false);
    }
  };

  // Calculate totals from history
  const totalMessages = historyData.reduce((sum, d) => sum + d.messages_count, 0);
  const totalTokens = historyData.reduce((sum, d) => sum + d.tokens_generated, 0);
  const avgResponseTime =
    historyData.length > 0
      ? historyData.reduce((sum, d) => sum + d.avg_response_time_ms, 0) /
        historyData.filter((d) => d.avg_response_time_ms > 0).length || 0
      : 0;

  // Find max values for chart scaling
  const maxMessages = Math.max(...historyData.map((d) => d.messages_count), 1);
  const maxTokens = Math.max(...historyData.map((d) => d.tokens_generated), 1);

  if (isLoading) {
    return (
      <div className="min-h-screen gradient-bg flex items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    );
  }

  if (!isAdmin) return null;

  return (
    <div className="min-h-screen gradient-bg">
      {/* Header */}
      <header className="border-b border-border/50 bg-background/80 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" onClick={() => router.push("/admin")}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back
            </Button>
            <h1 className="text-xl font-semibold text-foreground">
              Usage Metrics
            </h1>
          </div>

          {/* Period Selector */}
          <div className="flex items-center gap-1 bg-secondary rounded-lg p-1">
            {(["day", "week", "month"] as const).map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={cn(
                  "px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
                  period === p
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Real-time Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Current TPS
              </CardTitle>
              <Zap className="w-4 h-4 text-primary" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {realtimeMetrics?.tokens_per_second.toFixed(1) || "0.0"}
              </div>
              <p className="text-xs text-muted-foreground">tokens/second</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Requests Today
              </CardTitle>
              <MessageSquare className="w-4 h-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {realtimeMetrics?.requests_today || 0}
              </div>
              <p className="text-xs text-muted-foreground">messages</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Active Users
              </CardTitle>
              <Users className="w-4 h-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {realtimeMetrics?.active_users || 0}
              </div>
              <p className="text-xs text-muted-foreground">currently online</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Total Tokens
              </CardTitle>
              <Activity className="w-4 h-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {(realtimeMetrics?.total_tokens_generated || 0).toLocaleString()}
              </div>
              <p className="text-xs text-muted-foreground">generated today</p>
            </CardContent>
          </Card>
        </div>

        {/* Period Summary */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle>
              {period === "day" ? "24 Hour" : period === "week" ? "7 Day" : "30 Day"} Summary
            </CardTitle>
            <CardDescription>
              Aggregate statistics for the selected period
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-8">
              <div>
                <p className="text-3xl font-bold">{totalMessages.toLocaleString()}</p>
                <p className="text-sm text-muted-foreground">Total Messages</p>
              </div>
              <div>
                <p className="text-3xl font-bold">{totalTokens.toLocaleString()}</p>
                <p className="text-sm text-muted-foreground">Total Tokens</p>
              </div>
              <div>
                <p className="text-3xl font-bold">
                  {avgResponseTime > 0 ? `${(avgResponseTime / 1000).toFixed(2)}s` : "N/A"}
                </p>
                <p className="text-sm text-muted-foreground">Avg Response Time</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Simple Bar Chart */}
        <Card>
          <CardHeader>
            <CardTitle>Activity Over Time</CardTitle>
            <CardDescription>Messages per time interval</CardDescription>
          </CardHeader>
          <CardContent>
            {historyData.length > 0 ? (
              <div className="space-y-6">
                {/* Messages Chart */}
                <div>
                  <p className="text-sm font-medium mb-3">Messages</p>
                  <div className="flex items-end gap-1 h-32">
                    {historyData.map((point, i) => (
                      <div
                        key={i}
                        className="flex-1 bg-primary/20 hover:bg-primary/40 transition-colors rounded-t"
                        style={{
                          height: `${(point.messages_count / maxMessages) * 100}%`,
                          minHeight: point.messages_count > 0 ? "4px" : "0",
                        }}
                        title={`${point.messages_count} messages`}
                      />
                    ))}
                  </div>
                </div>

                {/* Tokens Chart */}
                <div>
                  <p className="text-sm font-medium mb-3">Tokens Generated</p>
                  <div className="flex items-end gap-1 h-32">
                    {historyData.map((point, i) => (
                      <div
                        key={i}
                        className="flex-1 bg-blue-500/20 hover:bg-blue-500/40 transition-colors rounded-t"
                        style={{
                          height: `${(point.tokens_generated / maxTokens) * 100}%`,
                          minHeight: point.tokens_generated > 0 ? "4px" : "0",
                        }}
                        title={`${point.tokens_generated.toLocaleString()} tokens`}
                      />
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="h-32 flex items-center justify-center text-muted-foreground">
                {isLoadingMetrics ? "Loading..." : "No data available for this period"}
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}


