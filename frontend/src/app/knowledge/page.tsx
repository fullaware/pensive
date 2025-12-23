"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Plus,
  Search,
  Edit,
  Trash2,
  BookOpen,
  Filter,
  X,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useRequireAuth } from "@/lib/auth";
import api, { KnowledgeItem } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import { cn } from "@/lib/utils";

export default function KnowledgePage() {
  const { isAuthenticated, isLoading } = useRequireAuth();
  const router = useRouter();

  const [knowledgeItems, setKnowledgeItems] = useState<KnowledgeItem[]>([]);
  const [domains, setDomains] = useState<string[]>([]);
  const [selectedDomain, setSelectedDomain] = useState<string | undefined>(undefined);
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoadingItems, setIsLoadingItems] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingItem, setEditingItem] = useState<KnowledgeItem | null>(null);
  const [total, setTotal] = useState(0);

  // Form state
  const [formDomain, setFormDomain] = useState("");
  const [formTopic, setFormTopic] = useState("");
  const [formContent, setFormContent] = useState("");
  const [formSubmitting, setFormSubmitting] = useState(false);

  useEffect(() => {
    if (isAuthenticated) {
      loadDomains();
      loadKnowledge();
    }
  }, [isAuthenticated, selectedDomain]);

  const loadDomains = async () => {
    try {
      const data = await api.getKnowledgeDomains();
      setDomains(data.domains);
    } catch (error) {
      console.error("Failed to load domains:", error);
    }
  };

  const loadKnowledge = async () => {
    setIsLoadingItems(true);
    try {
      const data = await api.listKnowledge(selectedDomain, 100, 0);
      setKnowledgeItems(data.items);
      setTotal(data.total);
    } catch (error) {
      console.error("Failed to load knowledge:", error);
    } finally {
      setIsLoadingItems(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      loadKnowledge();
      return;
    }

    setIsSearching(true);
    try {
      const data = await api.searchKnowledge(searchQuery, selectedDomain);
      setKnowledgeItems(data.items);
      setTotal(data.total);
    } catch (error) {
      console.error("Search failed:", error);
    } finally {
      setIsSearching(false);
    }
  };

  const handleAdd = () => {
    setEditingItem(null);
    setFormDomain("");
    setFormTopic("");
    setFormContent("");
    setShowAddModal(true);
  };

  const handleEdit = (item: KnowledgeItem) => {
    setEditingItem(item);
    setFormDomain(item.domain);
    setFormTopic(item.topic);
    setFormContent(item.content);
    setShowAddModal(true);
  };

  const handleDelete = async (item: KnowledgeItem) => {
    if (!confirm(`Delete knowledge item "${item.domain}/${item.topic}"?`)) {
      return;
    }

    try {
      await api.deleteKnowledge(item.domain, item.topic);
      loadKnowledge();
      loadDomains();
    } catch (error) {
      console.error("Failed to delete knowledge:", error);
      alert("Failed to delete knowledge item");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formDomain.trim() || !formTopic.trim() || !formContent.trim()) {
      return;
    }

    setFormSubmitting(true);
    try {
      if (editingItem) {
        await api.updateKnowledge(formDomain.trim(), formTopic.trim(), {
          content: formContent.trim(),
        });
      } else {
        await api.createKnowledge({
          domain: formDomain.trim().toLowerCase(),
          topic: formTopic.trim().toLowerCase(),
          content: formContent.trim(),
        });
      }
      setShowAddModal(false);
      loadKnowledge();
      loadDomains();
    } catch (error) {
      console.error("Failed to save knowledge:", error);
      alert("Failed to save knowledge item");
    } finally {
      setFormSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen gradient-bg flex items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  // Group items by domain
  const groupedItems = knowledgeItems.reduce((acc, item) => {
    if (!acc[item.domain]) {
      acc[item.domain] = [];
    }
    acc[item.domain].push(item);
    return acc;
  }, {} as Record<string, KnowledgeItem[]>);

  return (
    <div className="min-h-screen gradient-bg">
      {/* Header */}
      <header className="border-b border-border/50 bg-background/80 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" onClick={() => router.push("/settings")}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Settings
            </Button>
            <h1 className="text-xl font-semibold text-foreground flex items-center gap-2">
              <BookOpen className="w-5 h-5" />
              Knowledge Management
            </h1>
          </div>
          <Button onClick={handleAdd}>
            <Plus className="w-4 h-4 mr-2" />
            Add Knowledge
          </Button>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Filters */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle>Filters</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-4">
              <div className="flex-1">
                <form onSubmit={handleSearch} className="flex gap-2">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <Input
                      placeholder="Search knowledge..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-10"
                    />
                  </div>
                  <Button type="submit" disabled={isSearching}>
                    {isSearching ? "Searching..." : "Search"}
                  </Button>
                </form>
              </div>
              <div className="relative">
                <Select
                  value={selectedDomain || "all"}
                  onValueChange={(value) => setSelectedDomain(value === "all" ? undefined : value)}
                >
                  <SelectTrigger className="w-[200px]">
                    <SelectValue placeholder="Filter by domain" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Domains</SelectItem>
                    {domains.map((domain) => (
                      <SelectItem key={domain} value={domain}>
                        {domain}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {selectedDomain && (
                <Button
                  variant="outline"
                  onClick={() => setSelectedDomain(undefined)}
                >
                  <X className="w-4 h-4 mr-2" />
                  Clear Filter
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Knowledge Items */}
        {isLoadingItems ? (
          <div className="text-center py-8 text-muted-foreground">Loading knowledge...</div>
        ) : knowledgeItems.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center">
              <BookOpen className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
              <p className="text-muted-foreground">
                {searchQuery || selectedDomain
                  ? "No knowledge items found matching your filters."
                  : "No knowledge items yet. Add your first knowledge item to get started."}
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-6">
            {Object.entries(groupedItems).map(([domain, items]) => (
              <Card key={domain}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Filter className="w-4 h-4" />
                    {domain}
                    <span className="text-sm font-normal text-muted-foreground">
                      ({items.length} item{items.length !== 1 ? "s" : ""})
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {items.map((item) => (
                      <div
                        key={`${item.domain}/${item.topic}`}
                        className="p-4 rounded-lg bg-secondary/30 border border-border/50"
                      >
                        <div className="flex items-start justify-between gap-4 mb-2">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              <span className="font-semibold text-foreground">
                                {item.topic}
                              </span>
                            </div>
                            <p className="text-sm text-foreground whitespace-pre-wrap">
                              {item.content}
                            </p>
                            <p className="text-xs text-muted-foreground mt-2">
                              Updated {formatDateTime(item.updated_at)}
                            </p>
                          </div>
                          <div className="flex items-center gap-2">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleEdit(item)}
                            >
                              <Edit className="w-4 h-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-destructive hover:text-destructive"
                              onClick={() => handleDelete(item)}
                            >
                              <Trash2 className="w-4 h-4" />
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>

      {/* Add/Edit Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle>
                {editingItem ? "Edit Knowledge" : "Add Knowledge"}
              </CardTitle>
              <CardDescription>
                {editingItem
                  ? "Update the knowledge item"
                  : "Store a new fact, location, or preference"}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Domain</label>
                  <Input
                    value={formDomain}
                    onChange={(e) => setFormDomain(e.target.value)}
                    placeholder="e.g., locations, preferences, facts"
                    required
                    disabled={formSubmitting || !!editingItem}
                  />
                  <p className="text-xs text-muted-foreground">
                    Category for organizing knowledge (e.g., "locations", "preferences")
                  </p>
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium">Topic</label>
                  <Input
                    value={formTopic}
                    onChange={(e) => setFormTopic(e.target.value)}
                    placeholder="e.g., key_location, favorite_color"
                    required
                    disabled={formSubmitting || !!editingItem}
                  />
                  <p className="text-xs text-muted-foreground">
                    Specific topic within the domain
                  </p>
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium">Content</label>
                  <textarea
                    value={formContent}
                    onChange={(e) => setFormContent(e.target.value)}
                    placeholder="The actual knowledge (e.g., 'under the desk')"
                    className="w-full min-h-[100px] rounded-md border border-border bg-input px-3 py-2 text-sm"
                    required
                    disabled={formSubmitting}
                  />
                </div>

                <div className="flex gap-3 pt-4">
                  <Button
                    type="button"
                    variant="outline"
                    className="flex-1"
                    onClick={() => setShowAddModal(false)}
                    disabled={formSubmitting}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" className="flex-1" disabled={formSubmitting}>
                    {formSubmitting ? "Saving..." : editingItem ? "Update" : "Add"}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

