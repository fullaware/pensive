"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Users,
  Database,
  BarChart3,
  ArrowLeft,
  Activity,
  HardDrive,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useAuth, useRequireAdmin } from "@/lib/auth";
import api from "@/lib/api";

interface DashboardStats {
  userCounts: Record<string, number>;
  memoryStats: {
    total_memories: number;
    by_type: Record<string, number>;
    avg_importance: number;
  };
}

export default function AdminDashboard() {
  const { isAdmin, isLoading } = useRequireAdmin();
  const { user } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [isLoadingStats, setIsLoadingStats] = useState(true);

  useEffect(() => {
    const loadStats = async () => {
      try {
        const data = await api.getSystemStats();
        setStats({
          userCounts: data.user_counts,
          memoryStats: data.memory_stats,
        });
      } catch (error) {
        console.error("Failed to load stats:", error);
      } finally {
        setIsLoadingStats(false);
      }
    };

    if (isAdmin) {
      loadStats();
    }
  }, [isAdmin]);

  if (isLoading) {
    return (
      <div className="min-h-screen gradient-bg flex items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    );
  }

  if (!isAdmin) {
    return null;
  }

  return (
    <div className="min-h-screen gradient-bg">
      {/* Header */}
      <header className="border-b border-border/50 bg-background/80 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" onClick={() => router.push("/")}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Chat
            </Button>
            <h1 className="text-xl font-semibold text-foreground">
              Admin Dashboard
            </h1>
          </div>
          <span className="text-sm text-muted-foreground">
            {user?.display_name}
          </span>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Quick Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Total Users
              </CardTitle>
              <Users className="w-4 h-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {isLoadingStats ? "..." : stats?.userCounts.total || 0}
              </div>
              <p className="text-xs text-muted-foreground">
                {stats?.userCounts.admin || 0} admins, {stats?.userCounts.user || 0} users
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Total Memories
              </CardTitle>
              <Database className="w-4 h-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {isLoadingStats ? "..." : stats?.memoryStats.total_memories.toLocaleString() || 0}
              </div>
              <p className="text-xs text-muted-foreground">
                Avg importance: {stats?.memoryStats.avg_importance.toFixed(2) || "0.00"}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Memory Types
              </CardTitle>
              <HardDrive className="w-4 h-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {isLoadingStats
                  ? "..."
                  : Object.keys(stats?.memoryStats.by_type || {}).length}
              </div>
              <p className="text-xs text-muted-foreground">
                Active memory categories
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Navigation Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <Link href="/admin/users">
            <Card className="hover:border-primary/50 transition-colors cursor-pointer h-full">
              <CardHeader>
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center mb-2">
                  <Users className="w-5 h-5 text-primary" />
                </div>
                <CardTitle>User Management</CardTitle>
                <CardDescription>
                  Create, edit, and manage family member accounts and permissions
                </CardDescription>
              </CardHeader>
            </Card>
          </Link>

          <Link href="/admin/memory">
            <Card className="hover:border-primary/50 transition-colors cursor-pointer h-full">
              <CardHeader>
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center mb-2">
                  <Database className="w-5 h-5 text-primary" />
                </div>
                <CardTitle>Memory Browser</CardTitle>
                <CardDescription>
                  Search, view, and manage stored memories and conversations
                </CardDescription>
              </CardHeader>
            </Card>
          </Link>

          <Link href="/admin/metrics">
            <Card className="hover:border-primary/50 transition-colors cursor-pointer h-full">
              <CardHeader>
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center mb-2">
                  <BarChart3 className="w-5 h-5 text-primary" />
                </div>
                <CardTitle>Usage Metrics</CardTitle>
                <CardDescription>
                  View usage statistics, response times, and system performance
                </CardDescription>
              </CardHeader>
            </Card>
          </Link>
        </div>

        {/* Memory Breakdown */}
        {stats?.memoryStats.by_type && Object.keys(stats.memoryStats.by_type).length > 0 && (
          <Card className="mt-8">
            <CardHeader>
              <CardTitle>Memory Distribution</CardTitle>
              <CardDescription>Breakdown by memory type</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {Object.entries(stats.memoryStats.by_type).map(([type, count]) => (
                  <div key={type} className="flex items-center justify-between">
                    <span className="text-sm text-foreground capitalize">
                      {type.replace(/_/g, " ")}
                    </span>
                    <div className="flex items-center gap-3">
                      <div className="w-32 h-2 bg-secondary rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary rounded-full"
                          style={{
                            width: `${(count / stats.memoryStats.total_memories) * 100}%`,
                          }}
                        />
                      </div>
                      <span className="text-sm text-muted-foreground w-16 text-right">
                        {count.toLocaleString()}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}


