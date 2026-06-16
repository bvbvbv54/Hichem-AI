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
import { toast } from "@/hooks/use-toast";
import { Key, Cloud, RefreshCw, Trash2, Eye, EyeOff, CheckCircle2, XCircle } from "lucide-react";

function DriveCredentialsSection() {
  const [jsonInput, setJsonInput] = useState("");
  const [showJson, setShowJson] = useState(false);
  const [testStatus, setTestStatus] = useState<"idle" | "testing" | "ok" | "fail">("idle");
  const queryClient = useQueryClient();

  const { data: creds, isLoading: credsLoading, refetch: refetchCreds } = useQuery({
    queryKey: ["drive-credentials"],
    queryFn: () => api.getDriveCredentials(),
  });

  const saveMutation = useMutation({
    mutationFn: () => api.saveDriveCredentials(jsonInput),
    onSuccess: (data) => {
      toast({ title: "Credentials saved", description: `Connected as ${data.client_email}` });
      setJsonInput("");
      refetchCreds();
      queryClient.invalidateQueries({ queryKey: ["drive-status"] });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to save", description: err.message, variant: "destructive" });
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: () => api.disconnectDrive(),
    onSuccess: () => {
      toast({ title: "Credentials removed" });
      refetchCreds();
      queryClient.invalidateQueries({ queryKey: ["drive-status"] });
    },
  });

  const testMutation = useMutation({
    mutationFn: () => api.testDriveConnection(),
    onSuccess: () => {
      setTestStatus("ok");
      setTimeout(() => setTestStatus("idle"), 3000);
    },
    onError: (err: Error) => {
      setTestStatus("fail");
      toast({ title: "Connection failed", description: err.message, variant: "destructive" });
      setTimeout(() => setTestStatus("idle"), 5000);
    },
  });

  if (credsLoading) return <Skeleton className="h-24 w-full" />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium">Service Account</p>
            <Badge variant={creds?.configured ? "default" : "secondary"}>
              {creds?.configured ? "Configured" : "Not configured"}
            </Badge>
          </div>
          {creds?.client_email && (
            <p className="text-xs text-muted-foreground font-mono">{creds.client_email}</p>
          )}
        </div>
        <div className="flex gap-2">
          {creds?.configured && (
            <>
              <Button variant="outline" size="sm" onClick={() => testMutation.mutate()} disabled={testMutation.isPending}>
                {testStatus === "ok" ? <CheckCircle2 className="h-4 w-4 mr-1 text-green-500" /> :
                 testStatus === "fail" ? <XCircle className="h-4 w-4 mr-1 text-red-500" /> :
                 <RefreshCw className="h-4 w-4 mr-1" />}
                Test
              </Button>
              <Button variant="outline" size="sm" onClick={() => disconnectMutation.mutate()}>
                <Trash2 className="h-4 w-4 mr-1" /> Remove
              </Button>
            </>
          )}
        </div>
      </div>

      {!creds?.configured && (
        <div className="space-y-3">
          <Label>Service Account JSON</Label>
          <div className="flex gap-2 items-start">
            <Button
              variant="outline"
              size="sm"
              onClick={() => window.open("https://console.cloud.google.com/iam-admin/serviceaccounts", "_blank")}
            >
              <Key className="h-4 w-4 mr-1" /> Get my Key
            </Button>
            <span className="text-xs text-muted-foreground pt-1">
              Create a service account, then create a new JSON key and paste it below.
            </span>
          </div>
          <div className="relative">
            <textarea
              className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
              placeholder='Paste the JSON key here'
              value={jsonInput}
              onChange={(e) => setJsonInput(e.target.value)}
            />
          </div>
          <Button
            onClick={() => saveMutation.mutate()}
            disabled={!jsonInput.trim() || saveMutation.isPending}
          >
            Save Credentials
          </Button>
        </div>
      )}
    </div>
  );
}

export default function SettingsPage() {
  const [nanoBananaKey, setNanoBananaKey] = useState("");
  const [geminiKey, setGeminiKey] = useState("");
  const [savedNanoKey, setSavedNanoKey] = useState("");
  const [savedGeminiKey, setSavedGeminiKey] = useState("");
  const [showNanoKey, setShowNanoKey] = useState(false);
  const [showGeminiKey, setShowGeminiKey] = useState(false);

  const queryClient = useQueryClient();

  useEffect(() => {
    const savedNano = localStorage.getItem("nano_banana_key") || "";
    const savedGemini = localStorage.getItem("gemini_api_key") || "";
    setSavedNanoKey(savedNano);
    setSavedGeminiKey(savedGemini);
    setNanoBananaKey(savedNano);
    setGeminiKey(savedGemini);
  }, []);

  const saveKeysToLocal = () => {
    if (nanoBananaKey.trim()) {
      localStorage.setItem("nano_banana_key", nanoBananaKey.trim());
    }
    if (geminiKey.trim()) {
      localStorage.setItem("gemini_api_key", geminiKey.trim());
    }
    setSavedNanoKey(nanoBananaKey.trim());
    setSavedGeminiKey(geminiKey.trim());
    toast({ title: "API keys saved locally" });
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast({ title: "Copied to clipboard" });
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">Configure API keys and integrations</p>
      </div>

      {/* API Keys - Nano Banana & Gemini */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Key className="h-5 w-5" />
            AI Provider Keys
          </CardTitle>
          <CardDescription>Configure your AI provider API keys for image generation and text processing</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Nano Banana API Key</Label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Input
                  type={showNanoKey ? "text" : "password"}
                  placeholder="Enter your Nano Banana API key"
                  value={nanoBananaKey}
                  onChange={(e) => setNanoBananaKey(e.target.value)}
                />
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7"
                  onClick={() => setShowNanoKey(!showNanoKey)}
                >
                  {showNanoKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
            </div>
            {savedNanoKey && (
              <p className="text-xs text-muted-foreground">
                Key saved: {savedNanoKey.slice(0, 8)}...{savedNanoKey.slice(-4)}
              </p>
            )}
          </div>

          <Separator />

          <div className="space-y-2">
            <Label>Gemini API Key</Label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Input
                  type={showGeminiKey ? "text" : "password"}
                  placeholder="Enter your Google Gemini API key"
                  value={geminiKey}
                  onChange={(e) => setGeminiKey(e.target.value)}
                />
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7"
                  onClick={() => setShowGeminiKey(!showGeminiKey)}
                >
                  {showGeminiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
            </div>
            {savedGeminiKey && (
              <p className="text-xs text-muted-foreground">
                Key saved: {savedGeminiKey.slice(0, 8)}...{savedGeminiKey.slice(-4)}
              </p>
            )}
          </div>

          <Button onClick={saveKeysToLocal} disabled={!nanoBananaKey.trim() && !geminiKey.trim()}>
            Save Keys
          </Button>
        </CardContent>
      </Card>

      {/* Google Drive Sync */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cloud className="h-5 w-5" />
            Google Drive Sync
          </CardTitle>
          <CardDescription>Configure Google Drive integration using a service account</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <DriveCredentialsSection />
        </CardContent>
      </Card>
    </div>
  );
}
