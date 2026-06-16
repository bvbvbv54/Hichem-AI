"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "@/hooks/use-toast";
import { Key, Plus, Copy, Trash2, Eye, EyeOff, User, Bell } from "lucide-react";

export default function SettingsPage() {
  const [showNewKey, setShowNewKey] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: apiKeys, isLoading } = useQuery({
    queryKey: ["api-keys"],
    queryFn: () => api.getApiKeys(),
  });

  const createMutation = useMutation({
    mutationFn: () => api.createApiKey(newKeyName),
    onSuccess: (data) => {
      setCreatedKey(data.key);
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteApiKey(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
      toast({ title: "API key deleted" });
    },
  });

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast({ title: "Copied to clipboard" });
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">Manage your account and API keys</p>
      </div>

      {/* Profile */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <User className="h-5 w-5" />
            Profile
          </CardTitle>
          <CardDescription>Your account information</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Email</Label>
            <Input value="user@example.com" disabled />
          </div>
          <div className="space-y-2">
            <Label>Name</Label>
            <Input value="User" disabled />
          </div>
        </CardContent>
      </Card>

      {/* API Keys */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Key className="h-5 w-5" />
            API Keys
          </CardTitle>
          <CardDescription>Manage API keys for programmatic access</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? (
            <Skeleton className="h-20 w-full" />
          ) : (
            <div className="space-y-2">
              {(apiKeys || []).map((key: any) => (
                <div key={key.id} className="flex items-center justify-between rounded-lg border p-3">
                  <div>
                    <p className="font-medium">{key.name}</p>
                    <p className="text-xs text-muted-foreground font-mono">
                      {key.key?.slice(0, 12)}...
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="ghost" size="icon" onClick={() => copyToClipboard(key.key)}>
                      <Copy className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => deleteMutation.mutate(key.id)}>
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <Separator />

          <Dialog open={showNewKey} onOpenChange={setShowNewKey}>
            <Button
              variant="outline"
              onClick={() => setShowNewKey(true)}
              className="w-full"
            >
              <Plus className="h-4 w-4 mr-2" /> Create API Key
            </Button>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create API Key</DialogTitle>
              </DialogHeader>
              {createdKey ? (
                <div className="space-y-4 pt-4">
                  <p className="text-sm text-muted-foreground">Copy this key now. You won&apos;t be able to see it again.</p>
                  <div className="flex gap-2">
                    <Input value={createdKey} readOnly className="font-mono text-xs" />
                    <Button onClick={() => copyToClipboard(createdKey)}>
                      <Copy className="h-4 w-4" />
                    </Button>
                  </div>
                  <Button onClick={() => { setShowNewKey(false); setCreatedKey(null); setNewKeyName(""); }} className="w-full">
                    Done
                  </Button>
                </div>
              ) : (
                <div className="space-y-4 pt-4">
                  <Input
                    placeholder="Key name (e.g., Production)"
                    value={newKeyName}
                    onChange={(e) => setNewKeyName(e.target.value)}
                  />
                  <Button
                    onClick={() => createMutation.mutate()}
                    disabled={!newKeyName || createMutation.isPending}
                    className="w-full"
                  >
                    Create
                  </Button>
                </div>
              )}
            </DialogContent>
          </Dialog>
        </CardContent>
      </Card>

      {/* Notifications */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bell className="h-5 w-5" />
            Notifications
          </CardTitle>
          <CardDescription>Configure notification preferences</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Email, Discord, Slack, and Telegram integrations coming soon.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
