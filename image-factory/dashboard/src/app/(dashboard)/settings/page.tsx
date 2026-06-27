"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/hooks/use-toast";
import { Key, Cloud, RefreshCw, Trash2, Eye, EyeOff, CheckCircle2, XCircle, Save, DollarSign, Image, FolderOpen, Zap } from "lucide-react";

function DriveCredentialsSection() {
  const [jsonInput, setJsonInput] = useState("");
  const [testStatus, setTestStatus] = useState<"idle" | "testing" | "ok" | "fail">("idle");
  const [dirName, setDirName] = useState("");
  const [savingDir, setSavingDir] = useState(false);
  const queryClient = useQueryClient();

  const { data: creds, isLoading: credsLoading, refetch: refetchCreds } = useQuery({
    queryKey: ["drive-credentials"],
    queryFn: () => api.getDriveCredentials(),
  });

  const { data: driveConfig } = useQuery({
    queryKey: ["drive-config"],
    queryFn: () => api.getDriveConfig(),
    enabled: !!creds?.configured,
  });

  useEffect(() => {
    if (driveConfig?.root_folder) {
      setDirName(driveConfig.root_folder);
    }
  }, [driveConfig]);

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
      setTestStatus("idle");
      refetchCreds();
      queryClient.invalidateQueries({ queryKey: ["drive-status"] });
    },
  });

  const testMutation = useMutation({
    mutationFn: () => api.testDriveConnection(),
    onSuccess: () => {
      setTestStatus("ok");
    },
    onError: (err: Error) => {
      setTestStatus("fail");
      toast({ title: "Connection failed", description: err.message, variant: "destructive" });
      setTimeout(() => setTestStatus("idle"), 5000);
    },
  });

  const saveDirMutation = useMutation({
    mutationFn: (name: string) => api.updateDriveConfig({ root_folder: name }),
    onSuccess: () => {
      toast({ title: "Directory name saved" });
      queryClient.invalidateQueries({ queryKey: ["drive-config"] });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to save directory", description: err.message, variant: "destructive" });
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
          {testStatus === "ok" && (
            <p className="text-xs text-green-600 font-medium flex items-center gap-1">
              <CheckCircle2 className="h-3 w-3" /> Connected
            </p>
          )}
          {testStatus === "fail" && (
            <p className="text-xs text-red-500 font-medium flex items-center gap-1">
              <XCircle className="h-3 w-3" /> Connection failed
            </p>
          )}
        </div>
        <div className="flex gap-2">
          {creds?.configured && (
            <>
              <Button variant="outline" size="sm" onClick={() => testMutation.mutate()} disabled={testMutation.isPending}>
                {testMutation.isPending ? <RefreshCw className="h-4 w-4 mr-1 animate-spin" /> :
                 testStatus === "ok" ? <CheckCircle2 className="h-4 w-4 mr-1 text-green-500" /> :
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

      {testStatus === "ok" && (
        <div className="space-y-3 rounded-lg border border-green-500/30 bg-green-500/5 p-4">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-green-500" />
            <span className="text-sm font-medium text-green-600">Connected successfully</span>
          </div>
          <div className="space-y-2">
            <Label>Directory Name</Label>
            <p className="text-xs text-muted-foreground">Images will be saved under this directory on Google Drive: <span className="font-mono">{dirName || "ImageFactory Outputs"}/{`{product-name}`}/scraped/</span></p>
            <div className="flex gap-2">
              <Input
                placeholder="My Image Factory"
                value={dirName}
                onChange={(e) => setDirName(e.target.value)}
                className="flex-1"
              />
              <Button
                onClick={() => saveDirMutation.mutate(dirName)}
                disabled={!dirName.trim() || saveDirMutation.isPending}
                size="sm"
              >
                <Save className="h-4 w-4 mr-1" /> Save
              </Button>
            </div>
          </div>
        </div>
      )}

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
              placeholder="Paste the JSON key here"
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

function MonthlyBudgetSection() {
  const [budgetDollars, setBudgetDollars] = useState("");
  const [savingBudget, setSavingBudget] = useState(false);
  const queryClient = useQueryClient();

  const { data: budgetData, isLoading } = useQuery({
    queryKey: ["monthly-budget"],
    queryFn: () => authFetch("/api/v1/admin/budget").then(r => r.json()),
  });

  useEffect(() => {
    if (budgetData?.monthly_budget_dollars) {
      setBudgetDollars(budgetData.monthly_budget_dollars.toString());
    }
  }, [budgetData]);

  const saveBudget = async () => {
    const cents = Math.round(parseFloat(budgetDollars || "0") * 100);
    if (cents < 0 || isNaN(cents)) return;
    setSavingBudget(true);
    try {
      const res = await authFetch("/api/v1/admin/budget", {
        method: "PUT",
        body: JSON.stringify({ monthly_budget_cents: cents }),
      });
      if (!res.ok) throw new Error(await res.text());
      toast({ title: "Budget updated", description: `Monthly budget set to $${(cents / 100).toFixed(2)}` });
      queryClient.invalidateQueries({ queryKey: ["monthly-budget"] });
      queryClient.invalidateQueries({ queryKey: ["ai-limiter"] });
    } catch (err: any) {
      toast({ title: "Failed to update budget", description: err.message, variant: "destructive" });
    } finally {
      setSavingBudget(false);
    }
  };

  if (isLoading) return <Skeleton className="h-16 w-full" />;

  return (
    <div className="space-y-3">
      <div className="flex items-end gap-3">
        <div className="flex-1">
          <Label>Monthly Budget (USD)</Label>
          <div className="relative mt-1">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
            <Input
              type="number"
              min="0"
              step="1"
              className="pl-7"
              placeholder="100.00"
              value={budgetDollars}
              onChange={(e) => setBudgetDollars(e.target.value)}
            />
          </div>
        </div>
        <Button onClick={saveBudget} disabled={!budgetDollars || savingBudget}>
          <Save className="h-4 w-4 mr-1" /> Save Budget
        </Button>
      </div>
      {budgetData?.source && (
        <p className="text-xs text-muted-foreground">Source: {budgetData.source === "database" ? "Saved in database (changeable here)" : "From environment config"}</p>
      )}
    </div>
  );
}

function Img2imgSection() {
  const [selectedModel, setSelectedModel] = useState("google/imagen-4");
  const [saving, setSaving] = useState(false);

  const { data: img2imgData, isLoading } = useQuery({
    queryKey: ["img2img-config"],
    queryFn: () => api.getImg2imgSettings(),
  });

  useEffect(() => {
    if (img2imgData?.img2img_model?.value) {
      setSelectedModel(img2imgData.img2img_model.value);
    }
  }, [img2imgData]);

  const save = async () => {
    setSaving(true);
    try {
      await api.updateImg2imgSettings(selectedModel);
      toast({ title: "Image-to-image model updated" });
    } catch (err: any) {
      toast({ title: "Failed to update", description: err.message, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  if (isLoading) return <Skeleton className="h-16 w-full" />;

  const availableModels = img2imgData?.available_models || [];

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3">
        <div className="flex-1">
          <Label>Image-to-Image Model</Label>
          <Select value={selectedModel} onValueChange={setSelectedModel}>
            <SelectTrigger className="mt-1">
              <SelectValue placeholder="Select a model" />
            </SelectTrigger>
            <SelectContent>
              {availableModels.map((m: any) => (
                <SelectItem key={m.id} value={m.id}>{m.name} ({m.provider})</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button onClick={save} disabled={saving}>
          <Save className="h-4 w-4 mr-1" /> Save Model
        </Button>
      </div>
      {img2imgData?.img2img_model?.source && (
        <p className="text-xs text-muted-foreground">Source: {img2imgData.img2img_model.source}</p>
      )}
    </div>
  );
}

function StorageSection() {
  const [enabled, setEnabled] = useState(true);
  const [toggling, setToggling] = useState(false);

  const { data: storageData, isLoading } = useQuery({
    queryKey: ["storage-config"],
    queryFn: () => api.getStorageSettings(),
  });

  useEffect(() => {
    if (storageData) {
      setEnabled(storageData.storage_enabled?.value !== false);
    }
  }, [storageData]);

  const toggleEnabled = async () => {
    setToggling(true);
    try {
      const res = await authFetch("/api/v1/admin/settings/storage/toggle", {
        method: "PUT",
        body: JSON.stringify({ enabled: !enabled }),
      });
      if (!res.ok) throw new Error(await res.text());
      setEnabled(!enabled);
      toast({ title: `Storage ${!enabled ? "enabled" : "disabled"}` });
    } catch (err: any) {
      toast({ title: "Failed to toggle storage", description: err.message, variant: "destructive" });
    } finally {
      setToggling(false);
    }
  };

  if (isLoading) return <Skeleton className="h-16 w-full" />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <Label>Enable Storage</Label>
          <p className="text-xs text-muted-foreground">Toggle file output on/off</p>
        </div>
        <Switch checked={enabled} onCheckedChange={toggleEnabled} disabled={toggling} />
      </div>
      <p className="text-xs text-muted-foreground">
        Products saved locally in default output directory. Directory name can be configured via Google Drive Sync.
      </p>
    </div>
  );
}

function ScrapflyKeysSection() {
  const [newKey, setNewKey] = useState("");
  const [keys, setKeys] = useState<any[]>([]);
  const [adding, setAdding] = useState(false);
  const queryClient = useQueryClient();

  const { data: keysData, isLoading: keysLoading } = useQuery({
    queryKey: ["scrapfly-keys"],
    queryFn: () => fetchKeys(),
    refetchInterval: 30000,
  });

  useEffect(() => {
    if (keysData?.keys) setKeys(keysData.keys);
  }, [keysData]);

  const fetchKeys = async () => {
    const res = await authFetch("/api/v1/admin/scrapfly/keys");
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  };

  const addKey = async () => {
    if (!newKey.trim()) return;
    setAdding(true);
    try {
      const res = await authFetch("/api/v1/admin/scrapfly/keys", {
        method: "POST",
        body: JSON.stringify({ key: newKey.trim() }),
      });
      if (!res.ok) throw new Error(await res.text());
      setNewKey("");
      toast({ title: "ScrapFly key added" });
      queryClient.invalidateQueries({ queryKey: ["scrapfly-keys"] });
      queryClient.invalidateQueries({ queryKey: ["scrapfly-usage"] });
    } catch (err: any) {
      toast({ title: "Failed to add key", description: err.message, variant: "destructive" });
    } finally {
      setAdding(false);
    }
  };

  const removeKey = async (key: string) => {
    try {
      const res = await authFetch("/api/v1/admin/scrapfly/keys", {
        method: "DELETE",
        body: JSON.stringify({ key }),
      });
      if (!res.ok) throw new Error(await res.text());
      toast({ title: "ScrapFly key removed" });
      queryClient.invalidateQueries({ queryKey: ["scrapfly-keys"] });
      queryClient.invalidateQueries({ queryKey: ["scrapfly-usage"] });
    } catch (err: any) {
      toast({ title: "Failed to remove key", description: err.message, variant: "destructive" });
    }
  };

  if (keysLoading) return <Skeleton className="h-20 w-full" />;

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        {keys.map((k: any) => (
          <div key={k.key_preview} className="flex items-center justify-between rounded-lg border p-2.5">
            <div className="flex items-center gap-2">
              <code className="text-xs font-mono text-muted-foreground">{k.key_preview}</code>
              <Badge className="text-[10px] bg-muted text-muted-foreground">{k.used} used</Badge>
            </div>
            <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => removeKey(k.full_key || k.key_preview)}>
              <Trash2 className="h-3.5 w-3.5 text-destructive" />
            </Button>
          </div>
        ))}
        {keys.length === 0 && (
          <p className="text-xs text-muted-foreground">No ScrapFly API keys configured. Add one below.</p>
        )}
      </div>
      <div className="flex gap-2">
        <Input
          placeholder="scp-live-xxxx..."
          value={newKey}
          onChange={(e) => setNewKey(e.target.value)}
          className="font-mono text-xs"
        />
        <Button onClick={addKey} disabled={!newKey.trim() || adding} size="sm">
          Add Key
        </Button>
      </div>
    </div>
  );
}

function ScrapflyUsageSection() {
  const { data: usage, isLoading } = useQuery({
    queryKey: ["scrapfly-usage"],
    queryFn: () => api.getScrapflyUsage(),
    refetchInterval: 30000,
  });

  if (isLoading) return <Skeleton className="h-20 w-full" />;

  const total = usage?.total_cost ?? 0;
  const remaining = usage?.remaining_credits ?? 0;
  const budget = usage?.monthly_budget ?? 3000;
  const pct = budget > 0 ? Math.round((total / budget) * 100) : 0;
  const keyCount = usage?.key_count ?? 0;
  const scrapesBudget = usage?.scrapes_remaining_budget ?? 0;
  const avgCost = usage?.avg_cost_per_request ?? 9;
  const costPerProduct = usage?.cost_per_product ?? 9;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-center">
        <div className="rounded-lg border p-3">
          <p className="text-2xl font-bold">{total}</p>
          <p className="text-xs text-muted-foreground">Credits used</p>
        </div>
        <div className="rounded-lg border p-3">
          <p className="text-2xl font-bold">{remaining}</p>
          <p className="text-xs text-muted-foreground">Credits remaining</p>
        </div>
        <div className="rounded-lg border p-3">
          <p className="text-2xl font-bold">{scrapesBudget}</p>
          <p className="text-xs text-muted-foreground">Scrapes left (budget)</p>
        </div>
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground border-t border-muted-foreground/10 pt-2">
        <span>Avg cost: {avgCost} pts/request</span>
        <span>Cost per product: {costPerProduct} pts</span>
        <span>{keyCount} key{keyCount !== 1 ? "s" : ""}</span>
        <span>Used {pct}% of {budget} budget</span>
      </div>
      {pct > 80 && <p className="text-xs text-red-500 font-medium">Warning: over 80% of monthly Scrapfly budget consumed</p>}
      {total === 0 && <p className="text-xs text-muted-foreground">No Scrapfly requests yet this month.</p>}
    </div>
  );
}

async function getAuthToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  const stored = localStorage.getItem("auth_session");
  if (!stored) return null;
  try {
    const parsed = JSON.parse(stored);
    return parsed?.state?.token ?? parsed?.token ?? null;
  } catch {
    return null;
  }
}

async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = await getAuthToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return fetch(url, { ...options, headers });
}

export default function SettingsPage() {
  const [googleKey, setGoogleKey] = useState("");
  const [savedGoogleKey, setSavedGoogleKey] = useState(false);
  const [showGoogleKey, setShowGoogleKey] = useState(false);
  const [savingGoogle, setSavingGoogle] = useState(false);
  const [googleKeyError, setGoogleKeyError] = useState("");

  const queryClient = useQueryClient();

  const { data: providerKeys, isLoading: keysLoading } = useQuery({
    queryKey: ["provider-keys"],
    queryFn: () => api.getProviderKeys(),
  });

  useEffect(() => {
    if (providerKeys?.google_api_key?.configured) {
      setSavedGoogleKey(true);
    }
  }, [providerKeys]);

  const validateGoogleKey = (key: string): string => {
    if (!key.trim()) return "Key is required";
    if (!key.trim().startsWith("AIza")) return "Google API keys must start with 'AIza'";
    if (key.trim().length < 20) return "Key seems too short";
    return "";
  };

  const saveGoogleKey = async () => {
    const error = validateGoogleKey(googleKey);
    if (error) {
      setGoogleKeyError(error);
      return;
    }
    setGoogleKeyError("");
    setSavingGoogle(true);
    try {
      const result = await authFetch("/api/v1/admin/provider-keys/google", {
        method: "PUT",
        body: JSON.stringify({ key: googleKey.trim() }),
      });
      if (!result.ok) {
        const text = await result.text();
        throw new Error(text);
      }
      setSavedGoogleKey(true);
      setGoogleKey("");
      toast({ title: "Google AI API key saved" });
      queryClient.invalidateQueries({ queryKey: ["provider-keys"] });
    } catch (err: any) {
      toast({ title: "Failed to save key", description: err.message, variant: "destructive" });
    } finally {
      setSavingGoogle(false);
    }
  };



  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">Configure API keys and integrations</p>
      </div>

      {/* AI Provider Keys */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Key className="h-5 w-5" />
            AI Provider Keys
          </CardTitle>
          <CardDescription>Configure API keys for AI providers. Keys are stored securely on the server.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Google AI API Key (shared for Gemini + Nano Banana) */}
          <div className="space-y-2">
            <Label>Google AI API Key</Label>
            <p className="text-xs text-muted-foreground">Shared key for Gemini and Nano Banana image generation. Get one from <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">Google AI Studio</a>.</p>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Input
                  type={showGoogleKey ? "text" : "password"}
                  placeholder={savedGoogleKey ? "Key is configured on server" : "Enter your Google AI API key (starts with AIza...)"}
                  value={googleKey}
                  onChange={(e) => {
                    setGoogleKey(e.target.value);
                    if (googleKeyError) setGoogleKeyError("");
                  }}
                  className={googleKeyError ? "border-red-500" : ""}
                />
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7"
                  onClick={() => setShowGoogleKey(!showGoogleKey)}
                >
                  {showGoogleKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
              <Button onClick={saveGoogleKey} disabled={!googleKey.trim() || savingGoogle}>
                <Save className="h-4 w-4 mr-1" /> Save
              </Button>
            </div>
            {googleKeyError && <p className="text-xs text-red-500">{googleKeyError}</p>}
            {savedGoogleKey && !googleKey.trim() && (
              <p className="text-xs text-green-600 font-medium">Key is configured on server</p>
            )}
          </div>

          <Separator />

        </CardContent>
      </Card>

      {/* Image-to-Image Model Selection */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Image className="h-5 w-5" />
            Image-to-Image Model Selection
          </CardTitle>
          <CardDescription>Choose which AI model to use for image-to-image generation.</CardDescription>
        </CardHeader>
        <CardContent>
          <Img2imgSection />
        </CardContent>
      </Card>

      {/* Monthly Budget */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <DollarSign className="h-5 w-5" />
            Monthly Budget
          </CardTitle>
          <CardDescription>Set your monthly spending limit. Balance shown on the dashboard is budget minus actual usage.</CardDescription>
        </CardHeader>
        <CardContent>
          <MonthlyBudgetSection />
        </CardContent>
      </Card>

      {/* Storage Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FolderOpen className="h-5 w-5" />
            Storage Configuration
          </CardTitle>
          <CardDescription>Manage file output settings. Output directory is only configurable with Google Drive.</CardDescription>
        </CardHeader>
        <CardContent>
          <StorageSection />
        </CardContent>
      </Card>

      {/* Scrapfly Credits */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Zap className="h-5 w-5" />
            Scrapfly Credits
          </CardTitle>
          <CardDescription>Scrapfly API credit consumption for CAPTCHA bypass. ~6 credits per product (datacenter + JS render). Resets monthly.</CardDescription>
        </CardHeader>
        <CardContent>
          <ScrapflyUsageSection />
        </CardContent>
      </Card>

      {/* Scrapfly API Keys */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Key className="h-5 w-5" />
            Scrapfly API Keys
          </CardTitle>
          <CardDescription>Manage ScrapFly API keys for scraping and CAPTCHA bypass. Add multiple keys for pooled usage.</CardDescription>
        </CardHeader>
        <CardContent>
          <ScrapflyKeysSection />
        </CardContent>
      </Card>

      {/* Google Drive Sync */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cloud className="h-5 w-5" />
            Google Drive Sync
          </CardTitle>
          <CardDescription>Configure Google Drive integration using a service account. Directory name and output folder can be configured here.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <DriveCredentialsSection />
        </CardContent>
      </Card>
    </div>
  );
}