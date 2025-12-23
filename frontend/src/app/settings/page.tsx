"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Lock, ArrowLeft, Settings as SettingsIcon, Sparkles, BookOpen } from "lucide-react";
import { useRequireAuth, useAuth } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import api from "@/lib/api";

export default function SettingsPage() {
  const { isLoading } = useRequireAuth();
  const { user } = useAuth();
  const router = useRouter();

  // Password change state
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // AI Preferences state
  const [systemPrompt, setSystemPrompt] = useState("");
  const [temperature, setTemperature] = useState(0.7);
  const [assistantName, setAssistantName] = useState("");
  const [preferencesSubmitting, setPreferencesSubmitting] = useState(false);
  const [preferencesError, setPreferencesError] = useState<string | null>(null);
  const [preferencesSuccess, setPreferencesSuccess] = useState<string | null>(null);

  // Load user preferences
  useEffect(() => {
    if (user) {
      setSystemPrompt(user.system_prompt || "");
      setTemperature(user.temperature ?? 0.7);
      setAssistantName(user.assistant_name || "");
    }
  }, [user]);

  if (isLoading) {
    return (
      <div className="min-h-screen gradient-bg flex items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!newPassword || newPassword.length < 8) {
      setError("New password must be at least 8 characters long.");
      return;
    }

    if (newPassword !== confirmPassword) {
      setError("New password and confirmation do not match.");
      return;
    }

    setSubmitting(true);
    try {
      const result = await api.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      if (result.success) {
        setSuccess("Password updated successfully.");
        setCurrentPassword("");
        setNewPassword("");
        setConfirmPassword("");
      } else {
        setError(result.message || "Failed to update password.");
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to update password."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleUpdatePreferences = async (e: React.FormEvent) => {
    e.preventDefault();
    setPreferencesError(null);
    setPreferencesSuccess(null);
    setPreferencesSubmitting(true);

    try {
      const updatedUser = await api.updatePreferences({
        system_prompt: systemPrompt.trim() || undefined,
        temperature: temperature,
        assistant_name: assistantName.trim() || undefined,
      });
      
      setPreferencesSuccess("Preferences updated successfully!");
      // Update local state
      setSystemPrompt(updatedUser.system_prompt || "");
      setTemperature(updatedUser.temperature);
      setAssistantName(updatedUser.assistant_name || "");
    } catch (err) {
      setPreferencesError(
        err instanceof Error ? err.message : "Failed to update preferences"
      );
    } finally {
      setPreferencesSubmitting(false);
    }
  };

  const handleResetSystemPrompt = () => {
    setSystemPrompt("");
    setPreferencesError(null);
    setPreferencesSuccess(null);
  };

  return (
    <div className="min-h-screen gradient-bg">
      {/* Header */}
      <header className="border-b border-border/50 bg-background/80 backdrop-blur-sm">
        <div className="max-w-3xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => router.push("/")}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to chat
            </Button>
            <h1 className="text-xl font-semibold text-foreground">
              Account Settings
            </h1>
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8 space-y-8">
        {/* AI Assistant Preferences */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="w-5 h-5" />
              AI Assistant Preferences
            </CardTitle>
            <CardDescription>
              Customize your AI assistant's behavior, personality, and name
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleUpdatePreferences} className="space-y-6">
              {preferencesError && (
                <div className="p-3 rounded-lg bg-destructive/10 text-destructive text-sm">
                  {preferencesError}
                </div>
              )}
              {preferencesSuccess && (
                <div className="p-3 rounded-lg bg-blue-500/10 text-blue-500 text-sm">
                  {preferencesSuccess}
                </div>
              )}

              <div className="space-y-2">
                <label className="text-sm font-medium" htmlFor="assistant-name">
                  Assistant Name
                </label>
                <Input
                  id="assistant-name"
                  value={assistantName}
                  onChange={(e) => setAssistantName(e.target.value)}
                  placeholder="Pensive (default)"
                  disabled={preferencesSubmitting}
                />
                <p className="text-xs text-muted-foreground">
                  What you'd like to call your AI assistant
                </p>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium" htmlFor="temperature">
                  Temperature: {temperature.toFixed(1)}
                </label>
                <input
                  id="temperature"
                  type="range"
                  min="0"
                  max="2"
                  step="0.1"
                  value={temperature}
                  onChange={(e) => setTemperature(parseFloat(e.target.value))}
                  className="w-full"
                  disabled={preferencesSubmitting}
                />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>Deterministic (0.0)</span>
                  <span>Balanced (1.0)</span>
                  <span>Creative (2.0)</span>
                </div>
                <p className="text-xs text-muted-foreground">
                  Controls creativity vs consistency. Lower = more consistent, Higher = more creative
                </p>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium" htmlFor="system-prompt">
                    Custom System Prompt
                  </label>
                  <span className="text-xs text-muted-foreground">
                    {systemPrompt.length}/5000
                  </span>
                </div>
                <textarea
                  id="system-prompt"
                  value={systemPrompt}
                  onChange={(e) => setSystemPrompt(e.target.value)}
                  placeholder="Leave empty to use default system prompt..."
                  className="w-full min-h-[200px] rounded-md border border-border bg-input px-3 py-2 text-sm font-mono"
                  maxLength={5000}
                  disabled={preferencesSubmitting}
                />
                <div className="flex items-center justify-between">
                  <p className="text-xs text-muted-foreground">
                    Customize how your AI assistant behaves and responds
                  </p>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={handleResetSystemPrompt}
                    disabled={preferencesSubmitting || !systemPrompt}
                  >
                    Reset to Default
                  </Button>
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <Button
                  type="submit"
                  disabled={preferencesSubmitting}
                >
                  {preferencesSubmitting ? "Saving..." : "Save Preferences"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        {/* Change Password */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Lock className="w-5 h-5" />
              Change Password
            </CardTitle>
          </CardHeader>
          <CardContent>

          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="p-3 rounded-lg bg-destructive/10 text-destructive text-sm">
                {error}
              </div>
            )}
            {success && (
              <div className="p-3 rounded-lg bg-green-500/10 text-green-500 text-sm">
                {success}
              </div>
            )}

            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="currentPassword">
                Current password
              </label>
              <Input
                id="currentPassword"
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                placeholder="Enter current password"
                required
                disabled={submitting}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="newPassword">
                New password
              </label>
              <Input
                id="newPassword"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="At least 8 characters"
                required
                disabled={submitting}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="confirmPassword">
                Confirm new password
              </label>
              <Input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Re-enter new password"
                required
                disabled={submitting}
              />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => router.push("/")}
                disabled={submitting}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={submitting}>
                {submitting ? "Updating..." : "Update Password"}
              </Button>
            </div>
          </form>
          </CardContent>
        </Card>

        {/* Knowledge Management Link */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BookOpen className="w-5 h-5" />
              Knowledge Management
            </CardTitle>
            <CardDescription>
              Manage your stored knowledge items (facts, locations, preferences)
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              variant="outline"
              onClick={() => router.push("/knowledge")}
              className="w-full"
            >
              <BookOpen className="w-4 h-4 mr-2" />
              Manage Knowledge
            </Button>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}


