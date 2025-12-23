"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Plus,
  Search,
  MoreVertical,
  Shield,
  User as UserIcon,
  Trash2,
  Edit,
  Key,
  Eye,
  BookOpen,
  Settings,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useRequireAdmin } from "@/lib/auth";
import api, { User } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import { cn } from "@/lib/utils";

export default function UsersPage() {
  const { isAdmin, isLoading } = useRequireAdmin();
  const router = useRouter();
  const [users, setUsers] = useState<User[]>([]);
  const [isLoadingUsers, setIsLoadingUsers] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const [passwordValue, setPasswordValue] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSubmitting, setPasswordSubmitting] = useState(false);
  
  // Permissions modal state
  const [showPermissionsModal, setShowPermissionsModal] = useState(false);
  const [permissionsUser, setPermissionsUser] = useState<User | null>(null);
  const [permissions, setPermissions] = useState<Record<string, boolean>>({});
  const [permissionsSubmitting, setPermissionsSubmitting] = useState(false);

  // New user form state
  const [newUser, setNewUser] = useState({
    username: "",
    password: "",
    display_name: "",
    role: "user",
  });
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  useEffect(() => {
    loadUsers();
  }, [isAdmin]);

  const loadUsers = async () => {
    if (!isAdmin) return;
    try {
      const data = await api.listUsers(false); // Include inactive
      setUsers(data);
    } catch (error) {
      console.error("Failed to load users:", error);
    } finally {
      setIsLoadingUsers(false);
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsCreating(true);
    setCreateError("");

    try {
      await api.createUser(newUser);
      setShowCreateModal(false);
      setNewUser({ username: "", password: "", display_name: "", role: "user" });
      loadUsers();
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : "Failed to create user");
    } finally {
      setIsCreating(false);
    }
  };

  const handleToggleActive = async (user: User) => {
    try {
      await api.updateUser(user.id, { is_active: !user.is_active });
      loadUsers();
    } catch (error) {
      console.error("Failed to toggle user status:", error);
    }
  };

  const handleDeleteUser = async (user: User) => {
    if (!confirm(`Are you sure you want to delete ${user.display_name}?`)) return;
    try {
      await api.deleteUser(user.id, true);
      loadUsers();
    } catch (error) {
      console.error("Failed to delete user:", error);
    }
  };

  const openPermissionsModal = (user: User) => {
    setPermissionsUser(user);
    // Initialize permissions from user's current permissions
    setPermissions(user.tool_permissions || {});
    setShowPermissionsModal(true);
  };

  const handleSavePermissions = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!permissionsUser) return;

    setPermissionsSubmitting(true);
    try {
      await api.updateUser(permissionsUser.id, {
        tool_permissions: permissions,
      });
      setShowPermissionsModal(false);
      setPermissionsUser(null);
      loadUsers(); // Reload to get updated permissions
    } catch (error) {
      console.error("Failed to update permissions:", error);
      alert("Failed to update permissions");
    } finally {
      setPermissionsSubmitting(false);
    }
  };

  const togglePermission = (key: string) => {
    setPermissions((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const openPasswordModal = (user: User) => {
    setSelectedUser(user);
    setPasswordValue("");
    setPasswordConfirm("");
    setPasswordError(null);
    setShowPasswordModal(true);
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedUser) return;

    setPasswordError(null);

    if (!passwordValue || passwordValue.length < 8) {
      setPasswordError("New password must be at least 8 characters long.");
      return;
    }

    if (passwordValue !== passwordConfirm) {
      setPasswordError("New password and confirmation do not match.");
      return;
    }

    setPasswordSubmitting(true);
    try {
      await api.changePassword({
        user_id: selectedUser.id,
        new_password: passwordValue,
      });
      setShowPasswordModal(false);
      setSelectedUser(null);
    } catch (err) {
      setPasswordError(
        err instanceof Error ? err.message : "Failed to change password"
      );
    } finally {
      setPasswordSubmitting(false);
    }
  };

  const filteredUsers = users.filter(
    (user) =>
      user.username.toLowerCase().includes(searchQuery.toLowerCase()) ||
      user.display_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (isLoading || isLoadingUsers) {
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
              User Management
            </h1>
          </div>
          <Button onClick={() => setShowCreateModal(true)}>
            <Plus className="w-4 h-4 mr-2" />
            Add User
          </Button>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Search */}
        <div className="relative mb-6">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search users..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>

        {/* Users Table */}
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                      User
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                      Role
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                      Status
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                      Last Login
                    </th>
                    <th className="text-right p-4 text-sm font-medium text-muted-foreground">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUsers.map((user) => (
                    <tr
                      key={user.id}
                      className="border-b border-border/50 hover:bg-secondary/30"
                    >
                      <td className="p-4">
                        <div className="flex items-center gap-3">
                          <div
                            className={cn(
                              "w-8 h-8 rounded-full flex items-center justify-center",
                              user.role === "admin"
                                ? "bg-primary/20 text-primary"
                                : "bg-secondary text-secondary-foreground"
                            )}
                          >
                            {user.role === "admin" ? (
                              <Shield className="w-4 h-4" />
                            ) : (
                              <UserIcon className="w-4 h-4" />
                            )}
                          </div>
                          <div>
                            <p className="font-medium text-foreground">
                              {user.display_name}
                            </p>
                            <p className="text-sm text-muted-foreground">
                              @{user.username}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="p-4">
                        <span
                          className={cn(
                            "inline-flex items-center px-2 py-1 rounded-full text-xs font-medium",
                            user.role === "admin"
                              ? "bg-primary/10 text-primary"
                              : "bg-secondary text-secondary-foreground"
                          )}
                        >
                          {user.role}
                        </span>
                      </td>
                      <td className="p-4">
                        <span
                          className={cn(
                            "inline-flex items-center px-2 py-1 rounded-full text-xs font-medium",
                            user.is_active
                              ? "bg-blue-500/10 text-blue-500"
                              : "bg-destructive/10 text-destructive"
                          )}
                        >
                          {user.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td className="p-4 text-sm text-muted-foreground">
                        {user.last_login ? formatDateTime(user.last_login) : "Never"}
                      </td>
                      <td className="p-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              router.push(
                                `/admin/sessions?user_id=${user.id}&username=${encodeURIComponent(
                                  user.display_name
                                )}`
                              )
                            }
                            title="View Sessions"
                          >
                            <Eye className="w-4 h-4 mr-2" />
                            Sessions
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              router.push(
                                `/admin/memory?user_id=${user.id}&username=${encodeURIComponent(
                                  user.display_name
                                )}`
                              )
                            }
                            title="View Memories"
                          >
                            <BookOpen className="w-4 h-4 mr-2" />
                            Memories
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Manage permissions"
                            onClick={() => openPermissionsModal(user)}
                          >
                            <Settings className="w-4 h-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Change password"
                            onClick={() => openPasswordModal(user)}
                          >
                            <Key className="w-4 h-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleToggleActive(user)}
                          >
                            {user.is_active ? "Deactivate" : "Activate"}
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="text-destructive hover:text-destructive"
                            onClick={() => handleDeleteUser(user)}
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </main>

      {/* Create User Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle>Create New User</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleCreateUser} className="space-y-4">
                {createError && (
                  <div className="p-3 rounded-lg bg-destructive/10 text-destructive text-sm">
                    {createError}
                  </div>
                )}

                <div className="space-y-2">
                  <label className="text-sm font-medium">Username</label>
                  <Input
                    value={newUser.username}
                    onChange={(e) =>
                      setNewUser({ ...newUser, username: e.target.value })
                    }
                    placeholder="johndoe"
                    required
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium">Display Name</label>
                  <Input
                    value={newUser.display_name}
                    onChange={(e) =>
                      setNewUser({ ...newUser, display_name: e.target.value })
                    }
                    placeholder="John Doe"
                    required
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium">Password</label>
                  <Input
                    type="password"
                    value={newUser.password}
                    onChange={(e) =>
                      setNewUser({ ...newUser, password: e.target.value })
                    }
                    placeholder="••••••••"
                    required
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium">Role</label>
                  <select
                    value={newUser.role}
                    onChange={(e) =>
                      setNewUser({ ...newUser, role: e.target.value })
                    }
                    className="w-full h-10 rounded-md border border-border bg-input px-3 py-2 text-sm"
                  >
                    <option value="user">User</option>
                    <option value="admin">Admin</option>
                  </select>
                </div>

                <div className="flex gap-3 pt-4">
                  <Button
                    type="button"
                    variant="outline"
                    className="flex-1"
                    onClick={() => setShowCreateModal(false)}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" className="flex-1" disabled={isCreating}>
                    {isCreating ? "Creating..." : "Create User"}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Change Password Modal */}
      {showPasswordModal && selectedUser && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Key className="w-4 h-4" />
                Change Password — {selectedUser.display_name}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleChangePassword} className="space-y-4">
                {passwordError && (
                  <div className="p-3 rounded-lg bg-destructive/10 text-destructive text-sm">
                    {passwordError}
                  </div>
                )}

                <div className="space-y-2">
                  <label className="text-sm font-medium">New password</label>
                  <Input
                    type="password"
                    value={passwordValue}
                    onChange={(e) => setPasswordValue(e.target.value)}
                    placeholder="At least 8 characters"
                    required
                    disabled={passwordSubmitting}
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-medium">
                    Confirm new password
                  </label>
                  <Input
                    type="password"
                    value={passwordConfirm}
                    onChange={(e) => setPasswordConfirm(e.target.value)}
                    placeholder="Re-enter new password"
                    required
                    disabled={passwordSubmitting}
                  />
                </div>

                <div className="flex gap-3 pt-4">
                  <Button
                    type="button"
                    variant="outline"
                    className="flex-1"
                    onClick={() => {
                      setShowPasswordModal(false);
                      setSelectedUser(null);
                    }}
                    disabled={passwordSubmitting}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    className="flex-1"
                    disabled={passwordSubmitting}
                  >
                    {passwordSubmitting ? "Updating..." : "Update Password"}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Permissions Modal */}
      {showPermissionsModal && permissionsUser && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <Card className="w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Settings className="w-5 h-5" />
                Manage Permissions — {permissionsUser.display_name}
              </CardTitle>
              <CardDescription>
                Control which tools and features this user can access
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSavePermissions} className="space-y-6">
                {/* Core Tools */}
                <div>
                  <h3 className="text-sm font-semibold mb-3 text-foreground">Core Tools</h3>
                  <div className="space-y-2">
                    <label className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-secondary/30 cursor-pointer">
                      <div>
                        <span className="font-medium">Retrieve Context</span>
                        <p className="text-xs text-muted-foreground">Get recent conversation history</p>
                      </div>
                      <input
                        type="checkbox"
                        checked={permissions.retrieve_context ?? true}
                        onChange={() => togglePermission("retrieve_context")}
                        className="rounded border-border"
                      />
                    </label>
                    <label className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-secondary/30 cursor-pointer">
                      <div>
                        <span className="font-medium">Search Conversations</span>
                        <p className="text-xs text-muted-foreground">Search through past conversations</p>
                      </div>
                      <input
                        type="checkbox"
                        checked={permissions.search_conversations ?? true}
                        onChange={() => togglePermission("search_conversations")}
                        className="rounded border-border"
                      />
                    </label>
                    <label className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-secondary/30 cursor-pointer">
                      <div>
                        <span className="font-medium">Weather</span>
                        <p className="text-xs text-muted-foreground">Get weather information</p>
                      </div>
                      <input
                        type="checkbox"
                        checked={permissions.get_weather ?? true}
                        onChange={() => togglePermission("get_weather")}
                        className="rounded border-border"
                      />
                    </label>
                  </div>
                </div>

                {/* Memory Management */}
                <div>
                  <h3 className="text-sm font-semibold mb-3 text-foreground">Memory Management</h3>
                  <div className="space-y-2">
                    <label className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-secondary/30 cursor-pointer">
                      <div>
                        <span className="font-medium">Mark Important</span>
                        <p className="text-xs text-muted-foreground">Mark messages as important</p>
                      </div>
                      <input
                        type="checkbox"
                        checked={permissions.mark_important ?? true}
                        onChange={() => togglePermission("mark_important")}
                        className="rounded border-border"
                      />
                    </label>
                    <label className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-secondary/30 cursor-pointer">
                      <div>
                        <span className="font-medium">Remember This</span>
                        <p className="text-xs text-muted-foreground">Store important context</p>
                      </div>
                      <input
                        type="checkbox"
                        checked={permissions.remember_this ?? true}
                        onChange={() => togglePermission("remember_this")}
                        className="rounded border-border"
                      />
                    </label>
                    <label className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-secondary/30 cursor-pointer">
                      <div>
                        <span className="font-medium">Search by Entity</span>
                        <p className="text-xs text-muted-foreground">Search conversations by entity</p>
                      </div>
                      <input
                        type="checkbox"
                        checked={permissions.search_by_entity ?? true}
                        onChange={() => togglePermission("search_by_entity")}
                        className="rounded border-border"
                      />
                    </label>
                    <label className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-secondary/30 cursor-pointer">
                      <div>
                        <span className="font-medium">Memory Stats</span>
                        <p className="text-xs text-muted-foreground">View memory statistics</p>
                      </div>
                      <input
                        type="checkbox"
                        checked={permissions.get_memory_stats ?? false}
                        onChange={() => togglePermission("get_memory_stats")}
                        className="rounded border-border"
                      />
                    </label>
                  </div>
                </div>

                {/* Advanced Tools */}
                <div>
                  <h3 className="text-sm font-semibold mb-3 text-foreground">Advanced Tools</h3>
                  <div className="space-y-2">
                    <label className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-secondary/30 cursor-pointer">
                      <div>
                        <span className="font-medium">Web Search</span>
                        <p className="text-xs text-muted-foreground">Search the web for current information</p>
                      </div>
                      <input
                        type="checkbox"
                        checked={permissions.web_search ?? false}
                        onChange={() => togglePermission("web_search")}
                        className="rounded border-border"
                      />
                    </label>
                    <label className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-secondary/30 cursor-pointer">
                      <div>
                        <span className="font-medium">Research Agent</span>
                        <p className="text-xs text-muted-foreground">Create focused research sub-agents</p>
                      </div>
                      <input
                        type="checkbox"
                        checked={permissions.create_research_agent ?? false}
                        onChange={() => togglePermission("create_research_agent")}
                        className="rounded border-border"
                      />
                    </label>
                    <label className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-secondary/30 cursor-pointer">
                      <div>
                        <span className="font-medium">Summarize Memory</span>
                        <p className="text-xs text-muted-foreground">Summarize old conversations</p>
                      </div>
                      <input
                        type="checkbox"
                        checked={permissions.summarize_memory ?? false}
                        onChange={() => togglePermission("summarize_memory")}
                        className="rounded border-border"
                      />
                    </label>
                    <label className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-destructive/10 cursor-pointer">
                      <div>
                        <span className="font-medium text-destructive">Purge Memory</span>
                        <p className="text-xs text-muted-foreground">Delete old memories (dangerous)</p>
                      </div>
                      <input
                        type="checkbox"
                        checked={permissions.purge_memory ?? false}
                        onChange={() => togglePermission("purge_memory")}
                        className="rounded border-border"
                      />
                    </label>
                  </div>
                </div>

                {/* Calendar Permissions */}
                <div>
                  <h3 className="text-sm font-semibold mb-3 text-foreground">Calendar</h3>
                  <div className="space-y-2">
                    <label className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-secondary/30 cursor-pointer">
                      <div>
                        <span className="font-medium">View Events</span>
                        <p className="text-xs text-muted-foreground">List calendar events</p>
                      </div>
                      <input
                        type="checkbox"
                        checked={permissions.calendar_list_events ?? true}
                        onChange={() => togglePermission("calendar_list_events")}
                        className="rounded border-border"
                      />
                    </label>
                    <label className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-secondary/30 cursor-pointer">
                      <div>
                        <span className="font-medium">Create Events</span>
                        <p className="text-xs text-muted-foreground">Create new calendar events</p>
                      </div>
                      <input
                        type="checkbox"
                        checked={permissions.calendar_create_event ?? true}
                        onChange={() => togglePermission("calendar_create_event")}
                        className="rounded border-border"
                      />
                    </label>
                    <label className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-secondary/30 cursor-pointer">
                      <div>
                        <span className="font-medium">Update Events</span>
                        <p className="text-xs text-muted-foreground">Modify existing events</p>
                      </div>
                      <input
                        type="checkbox"
                        checked={permissions.calendar_update_event ?? false}
                        onChange={() => togglePermission("calendar_update_event")}
                        className="rounded border-border"
                      />
                    </label>
                    <label className="flex items-center justify-between p-3 rounded-lg border border-border hover:bg-destructive/10 cursor-pointer">
                      <div>
                        <span className="font-medium text-destructive">Delete Events</span>
                        <p className="text-xs text-muted-foreground">Delete calendar events (dangerous)</p>
                      </div>
                      <input
                        type="checkbox"
                        checked={permissions.calendar_delete_event ?? false}
                        onChange={() => togglePermission("calendar_delete_event")}
                        className="rounded border-border"
                      />
                    </label>
                  </div>
                </div>

                <div className="flex gap-3 pt-4 border-t border-border">
                  <Button
                    type="button"
                    variant="outline"
                    className="flex-1"
                    onClick={() => {
                      setShowPermissionsModal(false);
                      setPermissionsUser(null);
                    }}
                    disabled={permissionsSubmitting}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" className="flex-1" disabled={permissionsSubmitting}>
                    {permissionsSubmitting ? "Saving..." : "Save Permissions"}
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


