"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Search,
  Database,
  Filter,
  Trash2,
  AlertTriangle,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useRequireAdmin } from "@/lib/auth";
import api, { MemoryItem, MemoryStats } from "@/lib/api";
import { formatDateTime, formatRelativeTime } from "@/lib/utils";
import { cn } from "@/lib/utils";

export default function MemoryBrowserPage() {
  const { isAdmin, isLoading } = useRequireAdmin();
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState("");
  const [allMemories, setAllMemories] = useState<MemoryItem[]>([]);
  const [searchResults, setSearchResults] = useState<MemoryItem[]>([]);
  const [isLoadingMemories, setIsLoadingMemories] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [memoryTypes, setMemoryTypes] = useState<
    { value: string; name: string; description: string }[]
  >([]);
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [showSearch, setShowSearch] = useState(false);
  const [showPurgeModal, setShowPurgeModal] = useState(false);
  const [purgeSettings, setPurgeSettings] = useState({
    older_than_days: 30,
    importance_below: 0.3,
    dry_run: true,
  });
  const [purgeResult, setPurgeResult] = useState<{
    deleted_count: number;
    dry_run: boolean;
  } | null>(null);

  useEffect(() => {
    if (isAdmin) {
      loadStats();
      loadMemoryTypes();
      loadAllMemories();
    }
  }, [isAdmin]);

  useEffect(() => {
    if (isAdmin) {
      loadAllMemories();
    }
  }, [selectedTypes, isAdmin]);

  const loadStats = async () => {
    try {
      const data = await api.getMemoryStats();
      setStats(data);
    } catch (error) {
      console.error("Failed to load stats:", error);
    }
  };

  const loadMemoryTypes = async () => {
    try {
      const data = await api.getMemoryTypes();
      setMemoryTypes(data.types);
    } catch (error) {
      console.error("Failed to load memory types:", error);
    }
  };

  const loadAllMemories = async () => {
    setIsLoadingMemories(true);
    try {
      const data = await api.listMemories(
        selectedTypes.length > 0 ? selectedTypes : undefined,
        500, // Load up to 500 memories
        0
      );
      setAllMemories(data.results);
      setSearchResults([]); // Clear search results when loading all
    } catch (error) {
      console.error("Failed to load memories:", error);
    } finally {
      setIsLoadingMemories(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    setIsSearching(true);
    try {
      const data = await api.searchMemories(
        searchQuery,
        selectedTypes.length > 0 ? selectedTypes : undefined
      );
      setSearchResults(data.results);
    } catch (error) {
      console.error("Search failed:", error);
    } finally {
      setIsSearching(false);
    }
  };

  const handlePurge = async () => {
    try {
      const result = await api.purgeMemories(
        purgeSettings.older_than_days,
        purgeSettings.importance_below,
        purgeSettings.dry_run
      );
      setPurgeResult(result);
      if (!purgeSettings.dry_run) {
        loadStats();
      }
    } catch (error) {
      console.error("Purge failed:", error);
    }
  };

  const toggleTypeFilter = (type: string) => {
    setSelectedTypes((prev) => {
      const newTypes = prev.includes(type) 
        ? prev.filter((t) => t !== type) 
        : [...prev, type];
      return newTypes;
    });
  };

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
              Memory Browser
            </h1>
          </div>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => setShowPurgeModal(true)}
          >
            <Trash2 className="w-4 h-4 mr-2" />
            Purge Old Memories
          </Button>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Stats Cards */}
        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
            <Card>
              <CardContent className="pt-6">
                <div className="text-2xl font-bold">
                  {stats.total_memories.toLocaleString()}
                </div>
                <p className="text-sm text-muted-foreground">Total Memories</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-2xl font-bold">
                  {stats.avg_importance.toFixed(2)}
                </div>
                <p className="text-sm text-muted-foreground">Avg Importance</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-2xl font-bold">
                  {stats.oldest_memory
                    ? formatRelativeTime(stats.oldest_memory)
                    : "N/A"}
                </div>
                <p className="text-sm text-muted-foreground">Oldest Memory</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <div className="text-2xl font-bold">
                  {stats.newest_memory
                    ? formatRelativeTime(stats.newest_memory)
                    : "N/A"}
                </div>
                <p className="text-sm text-muted-foreground">Newest Memory</p>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Recommendations */}
        {stats?.storage_recommendations && stats.storage_recommendations.length > 0 && (
          <Card className="mb-8 border-blue-500/50">
            <CardHeader>
              <CardTitle className="text-sm flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-blue-500" />
                Recommendations
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-1">
                {stats.storage_recommendations.map((rec, i) => (
                  <li key={i} className="text-sm text-muted-foreground">
                    • {rec}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}

        {/* Filters and Search */}
        <Card className="mb-8">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Memory Browser</CardTitle>
                <CardDescription>
                  {showSearch 
                    ? "Search through all stored memories by content"
                    : "Browse all memories with type filtering"}
                </CardDescription>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setShowSearch(!showSearch);
                  if (!showSearch) {
                    setSearchQuery("");
                    setSearchResults([]);
                  }
                }}
              >
                {showSearch ? (
                  <>
                    <Filter className="w-4 h-4 mr-2" />
                    Browse
                  </>
                ) : (
                  <>
                    <Search className="w-4 h-4 mr-2" />
                    Search
                  </>
                )}
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {/* Type Filters */}
            <div className="mb-4">
              <label className="text-sm font-medium mb-2 block">Filter by Type:</label>
              <div className="flex flex-wrap gap-2">
                {memoryTypes.map((type) => (
                  <button
                    key={type.value}
                    onClick={() => toggleTypeFilter(type.value)}
                    className={cn(
                      "px-3 py-1 rounded-full text-xs font-medium transition-colors",
                      selectedTypes.includes(type.value)
                        ? "bg-primary text-primary-foreground"
                        : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
                    )}
                  >
                    {type.name}
                  </button>
                ))}
                {selectedTypes.length > 0 && (
                  <button
                    onClick={() => setSelectedTypes([])}
                    className="px-3 py-1 rounded-full text-xs font-medium bg-destructive/10 text-destructive hover:bg-destructive/20"
                  >
                    Clear Filters
                  </button>
                )}
              </div>
            </div>

            {/* Search Form (only shown when search mode) */}
            {showSearch && (
              <form onSubmit={handleSearch} className="flex gap-2">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    placeholder="Search memories..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-10"
                  />
                </div>
                <Button type="submit" disabled={isSearching}>
                  {isSearching ? "Searching..." : "Search"}
                </Button>
              </form>
            )}
          </CardContent>
        </Card>

        {/* All Memories or Search Results */}
        {showSearch && searchResults.length > 0 ? (
          <Card>
            <CardHeader>
              <CardTitle>Search Results ({searchResults.length})</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {searchResults.map((memory) => (
                <div
                  key={memory.id}
                  className="p-4 rounded-lg bg-secondary/30 border border-border/50"
                >
                  <div className="flex items-start justify-between gap-4 mb-2">
                    <span
                      className={cn(
                        "px-2 py-0.5 rounded text-xs font-medium",
                        "bg-primary/10 text-primary"
                      )}
                    >
                      {memory.memory_type}
                    </span>
                    <div className="text-xs text-muted-foreground">
                      Importance: {memory.importance.toFixed(2)}
                    </div>
                  </div>
                  <p className="text-sm text-foreground mb-2 whitespace-pre-wrap">
                    {memory.content}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatDateTime(memory.timestamp)}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        ) : !showSearch && (
          <Card>
            <CardHeader>
              <CardTitle>
                All Memories 
                {selectedTypes.length > 0 && ` (Filtered: ${selectedTypes.length} type${selectedTypes.length > 1 ? 's' : ''})`}
                {allMemories.length > 0 && ` (${allMemories.length})`}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {isLoadingMemories ? (
                <div className="text-center py-8 text-muted-foreground">
                  Loading memories...
                </div>
              ) : allMemories.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  {selectedTypes.length > 0 
                    ? "No memories found matching the selected filters."
                    : "No memories found."}
                </div>
              ) : (
                <div className="space-y-4">
                  {allMemories.map((memory) => (
                    <div
                      key={memory.id}
                      className="p-4 rounded-lg bg-secondary/30 border border-border/50"
                    >
                      <div className="flex items-start justify-between gap-4 mb-2">
                        <span
                          className={cn(
                            "px-2 py-0.5 rounded text-xs font-medium",
                            "bg-primary/10 text-primary"
                          )}
                        >
                          {memory.memory_type}
                        </span>
                        <div className="text-xs text-muted-foreground">
                          Importance: {memory.importance.toFixed(2)}
                        </div>
                      </div>
                      <p className="text-sm text-foreground mb-2 whitespace-pre-wrap">
                        {memory.content}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {formatDateTime(memory.timestamp)}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </main>

      {/* Purge Modal */}
      {showPurgeModal && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-destructive" />
                Purge Old Memories
              </CardTitle>
              <CardDescription>
                Remove old, low-importance memories to free up space
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">
                  Older than (days)
                </label>
                <Input
                  type="number"
                  value={purgeSettings.older_than_days}
                  onChange={(e) =>
                    setPurgeSettings({
                      ...purgeSettings,
                      older_than_days: parseInt(e.target.value) || 30,
                    })
                  }
                  min={1}
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">
                  Importance below
                </label>
                <Input
                  type="number"
                  step="0.1"
                  value={purgeSettings.importance_below}
                  onChange={(e) =>
                    setPurgeSettings({
                      ...purgeSettings,
                      importance_below: parseFloat(e.target.value) || 0.3,
                    })
                  }
                  min={0}
                  max={1}
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="dry_run"
                  checked={purgeSettings.dry_run}
                  onChange={(e) =>
                    setPurgeSettings({
                      ...purgeSettings,
                      dry_run: e.target.checked,
                    })
                  }
                  className="rounded border-border"
                />
                <label htmlFor="dry_run" className="text-sm">
                  Dry run (preview only, don&apos;t delete)
                </label>
              </div>

              {purgeResult && (
                <div
                  className={cn(
                    "p-3 rounded-lg text-sm",
                    purgeResult.dry_run
                      ? "bg-blue-500/10 text-blue-500"
                      : "bg-blue-400/10 text-blue-400"
                  )}
                >
                  {purgeResult.dry_run
                    ? `Would delete ${purgeResult.deleted_count} memories`
                    : `Deleted ${purgeResult.deleted_count} memories`}
                </div>
              )}

              <div className="flex gap-3 pt-4">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => {
                    setShowPurgeModal(false);
                    setPurgeResult(null);
                  }}
                >
                  Cancel
                </Button>
                <Button
                  variant={purgeSettings.dry_run ? "default" : "destructive"}
                  className="flex-1"
                  onClick={handlePurge}
                >
                  {purgeSettings.dry_run ? "Preview" : "Purge"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}


