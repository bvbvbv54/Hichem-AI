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
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/hooks/use-toast";
import { Key, Cloud, RefreshCw, Trash2, Eye, EyeOff, CheckCircle2, XCircle, Save, ExternalLink, DollarSign, Settings2, Sliders, Image, FolderOpen, Zap } from "lucide-react";

function DriveCredentialsSection() {
  const [jsonInput, setJsonInput] = useState("");
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

function MonthlyBudgetSection() {
  const [budgetDollars, setBudgetDollars] = useState("");
  const [savingBudget, setSavingBudget] = useState(false);
  const queryClient = useQueryClient();

  const { data: budgetData, isLoading } = useQuery({
    queryKey: ["monthly-budget"],
    queryFn: () => fetch("/api/v1/admin/budget").then(r => r.json()),
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
      const res = await fetch("/api/v1/admin/budget", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ monthly_budget_cents: cents }),
      });
      if (!res.ok) throw new Error(await res.text());
      toast({ title: "Budget updated", description: `Monthly budget set to $${(cents / 100).toFixed(2)}` });
      queryClient.invalidateQueries({ queryKey: ["monthly-budget"] });
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

function ClaudeConfigSection() {
  const [model, setModel] = useState("claude-sonnet-4-20250514");
  const [maxTokens, setMaxTokens] = useState("4096");
  const [temperature, setTemperature] = useState("0.7");
  const [saving, setSaving] = useState(false);

  const { data: claudeData, isLoading } = useQuery({
    queryKey: ["claude-config"],
    queryFn: () => fetch("/api/v1/admin/settings/claude").then(r => r.json()),
  });

  useEffect(() => {
    if (claudeData) {
      setModel(claudeData.claude_model?.value || "claude-sonnet-4-20250514");
      setMaxTokens(String(claudeData.claude_max_tokens?.value || 4096));
      setTemperature(String(claudeData.claude_temperature?.value || 0.7));
    }
  }, [claudeData]);

  const save = async () => {
    setSaving(true);
    try {
      const res = await fetch("/api/v1/admin/settings/claude", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ claude_model: model, claude_max_tokens: parseInt(maxTokens), claude_temperature: parseFloat(temperature) }),
      });
      if (!res.ok) throw new Error(await res.text());
      toast({ title: "Claude config updated" });
    } catch (err: any) {
      toast({ title: "Failed to update", description: err.message, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  if (isLoading) return <Skeleton className="h-24 w-full" />;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <div>
          <Label>Model</Label>
          <Input value={model} onChange={e => setModel(e.target.value)} className="mt-1 font-mono text-xs" />
        </div>
        <div>
          <Label>Max Tokens</Label>
          <Input type="number" min="1" value={maxTokens} onChange={e => setMaxTokens(e.target.value)} className="mt-1" />
        </div>
        <div>
          <Label>Temperature</Label>
          <Input type="number" min="0" max="1" step="0.1" value={temperature} onChange={e => setTemperature(e.target.value)} className="mt-1" />
        </div>
      </div>
      <Button onClick={save} disabled={saving}><Save className="h-4 w-4 mr-1" /> Save Claude Config</Button>
      {claudeData?.claude_model?.source && (
        <p className="text-xs text-muted-foreground">Source: {claudeData.claude_model.source}</p>
      )}
    </div>
  );
}

function PricingSection() {
  const [costPerImage, setCostPerImage] = useState("1.0");
  const [costPerClaude, setCostPerClaude] = useState("0.03");
  const [saving, setSaving] = useState(false);

  const { data: pricingData, isLoading } = useQuery({
    queryKey: ["pricing-config"],
    queryFn: () => fetch("/api/v1/admin/settings/pricing").then(r => r.json()),
  });

  useEffect(() => {
    if (pricingData) {
      setCostPerImage(String(pricingData.cost_per_image_cents?.value || 1.0));
      setCostPerClaude(String(pricingData.cost_per_claude_call_cents?.value || 0.03));
    }
  }, [pricingData]);

  const save = async () => {
    setSaving(true);
    try {
      const res = await fetch("/api/v1/admin/settings/pricing", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cost_per_image_cents: parseFloat(costPerImage),
          cost_per_claude_call_cents: parseFloat(costPerClaude),
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      toast({ title: "Pricing updated", description: "Cost values saved to database" });
    } catch (err: any) {
      toast({ title: "Failed to update pricing", description: err.message, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  if (isLoading) return <Skeleton className="h-16 w-full" />;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label>Cost per Image (cents)</Label>
          <Input type="number" min="0" step="0.01" value={costPerImage} onChange={e => setCostPerImage(e.target.value)} className="mt-1" />
        </div>
        <div>
          <Label>Cost per Claude Call (cents)</Label>
          <Input type="number" min="0" step="0.001" value={costPerClaude} onChange={e => setCostPerClaude(e.target.value)} className="mt-1" />
        </div>
      </div>
      <Button onClick={save} disabled={saving}><Save className="h-4 w-4 mr-1" /> Save Pricing</Button>
      {pricingData?.cost_per_image_cents?.source && (
        <p className="text-xs text-muted-foreground">Source: {pricingData.cost_per_image_cents.source}</p>
      )}
    </div>
  );
}

function ScrapflyKeysSection() {
  const [newKey, setNewKey] = useState("");
  const [keys, setKeys] = useState<any[]>([]);
  const queryClient = useQueryClient();

  const { data: keysData, isLoading: keysLoading } = useQuery({
    queryKey: ["scrapfly-keys"],
    queryFn: () => fetch("/api/v1/admin/scrapfly/keys").then(r => r.json()),
    refetchInterval: 30000,
  });

  useEffect(() => {
    if (keysData?.keys) setKeys(keysData.keys);
  }, [keysData]);

  const addKey = async () => {
    if (!newKey.trim()) return;
    try {
      const res = await fetch("/api/v1/admin/scrapfly/keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: newKey.trim() }),
      });
      if (!res.ok) throw new Error(await res.text());
      setNewKey("");
      toast({ title: "ScrapFly key added" });
      queryClient.invalidateQueries({ queryKey: ["scrapfly-keys"] });
      queryClient.invalidateQueries({ queryKey: ["scrapfly-usage"] });
    } catch (err: any) {
      toast({ title: "Failed to add key", description: err.message, variant: "destructive" });
    }
  };

  const removeKey = async (key: string) => {
    try {
      const res = await fetch("/api/v1/admin/scrapfly/keys", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
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
            <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => removeKey(k.key_preview)}>
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
        <Button onClick={addKey} disabled={!newKey.trim()} size="sm">
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
  const budgetLeft = usage?.budget_left ?? budget;
  const possible = usage?.products_possible ?? 0;
  const pct = budget > 0 ? Math.round((total / budget) * 100) : 0;
  const keyCount = usage?.key_count ?? 0;
  const scrapesBudget = usage?.scrapes_remaining_budget ?? 0;
  const scrapesActual = usage?.scrapes_remaining_actual ?? 0;
  const avgCost = usage?.avg_cost_per_request ?? 9;
  const costPerProduct = usage?.cost_per_product ?? 9;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
        <div className="rounded-lg border p-3">
          <p className="text-2xl font-bold">{total}</p>
          <p className="text-xs text-muted-foreground">Credits used</p>
        </div>
        <div className="rounded-lg border p-3">
          <p className="text-2xl font-bold">{remaining}</p>
          <p className="text-xs text-muted-foreground">Credits remaining</p>
        </div>
        <div className="rounded-lg border p-3">
          <p className="text-2xl font-bold">{scrapesActual}</p>
          <p className="text-xs text-muted-foreground">Scrapes left (actual)</p>
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

function StorageSection() {
  const [storagePath, setStoragePath] = useState("");
  const [saving, setSaving] = useState(false);

  const { data: storageData, isLoading } = useQuery({
    queryKey: ["storage-config"],
    queryFn: () => api.getStorageSettings(),
  });

  useEffect(() => {
    if (storageData?.storage_local_path?.value) {
      setStoragePath(storageData.storage_local_path.value);
    }
  }, [storageData]);

  const save = async () => {
    if (!storagePath.trim()) return;
    setSaving(true);
    try {
      await api.updateStorageSettings(storagePath.trim());
      toast({ title: "Output directory updated", description: `Storage path set to ${storagePath}` });
    } catch (err: any) {
      toast({ title: "Failed to update", description: err.message, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  if (isLoading) return <Skeleton className="h-16 w-full" />;

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3">
        <div className="flex-1">
          <Label>Output Directory Path</Label>
          <Input
            value={storagePath}
            onChange={e => setStoragePath(e.target.value)}
            className="mt-1 font-mono text-xs"
            placeholder="/app/outputs"
          />
        </div>
        <Button onClick={save} disabled={!storagePath.trim() || saving}>
          <Save className="h-4 w-4 mr-1" /> Save Path
        </Button>
      </div>
      {storageData?.storage_local_path?.source && (
        <p className="text-xs text-muted-foreground">Source: {storageData.storage_local_path.source}</p>
      )}
      <p className="text-xs text-muted-foreground">
        Products will be saved under this directory in sub-folders named after each product.
      </p>
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

export default function SettingsPage() {
  const [nanoBananaKey, setNanoBananaKey] = useState("");
  const [geminiKey, setGeminiKey] = useState("");
  const [claudeKey, setClaudeKey] = useState("");
  const [savedNanoKey, setSavedNanoKey] = useState("");
  const [savedGeminiKey, setSavedGeminiKey] = useState("");
  const [savedClaudeKey, setSavedClaudeKey] = useState("");
  const [showNanoKey, setShowNanoKey] = useState(false);
  const [showGeminiKey, setShowGeminiKey] = useState(false);
  const [showClaudeKey, setShowClaudeKey] = useState(false);
  const [savingNano, setSavingNano] = useState(false);
  const [savingGemini, setSavingGemini] = useState(false);
  const [savingClaude, setSavingClaude] = useState(false);

  const queryClient = useQueryClient();

  const { data: providerKeys, isLoading: keysLoading } = useQuery({
    queryKey: ["provider-keys"],
    queryFn: () => api.getProviderKeys(),
  });

  useEffect(() => {
    if (providerKeys?.nano_banana_api_key?.configured) {
      setSavedNanoKey("configured");
    }
    if (providerKeys?.gemini_api_key?.configured) {
      setSavedGeminiKey("configured");
    }
    if (providerKeys?.claude_api_key?.configured) {
      setSavedClaudeKey("configured");
    }
  }, [providerKeys]);

  const saveNanoKey = async () => {
    if (!nanoBananaKey.trim()) return;
    setSavingNano(true);
    try {
      const result = await fetch("/api/v1/admin/provider-keys/nano-banana", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: nanoBananaKey.trim() }),
      });
      if (!result.ok) throw new Error(await result.text());
      setSavedNanoKey("configured");
      setNanoBananaKey("");
      toast({ title: "Nano Banana API key saved to server" });
      queryClient.invalidateQueries({ queryKey: ["provider-keys"] });
    } catch (err: any) {
      toast({ title: "Failed to save key", description: err.message, variant: "destructive" });
    } finally {
      setSavingNano(false);
    }
  };

  const saveGeminiKey = async () => {
    if (!geminiKey.trim()) return;
    setSavingGemini(true);
    try {
      const result = await fetch("/api/v1/admin/provider-keys/gemini", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: geminiKey.trim() }),
      });
      if (!result.ok) throw new Error(await result.text());
      setSavedGeminiKey("configured");
      setGeminiKey("");
      toast({ title: "Gemini API key saved to server" });
      queryClient.invalidateQueries({ queryKey: ["provider-keys"] });
    } catch (err: any) {
      toast({ title: "Failed to save key", description: err.message, variant: "destructive" });
    } finally {
      setSavingGemini(false);
    }
  };

  const saveClaudeKey = async () => {
    if (!claudeKey.trim()) return;
    setSavingClaude(true);
    try {
      const result = await fetch("/api/v1/admin/provider-keys/claude", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: claudeKey.trim() }),
      });
      if (!result.ok) throw new Error(await result.text());
      setSavedClaudeKey("configured");
      setClaudeKey("");
      toast({ title: "Claude API key saved to server" });
      queryClient.invalidateQueries({ queryKey: ["provider-keys"] });
    } catch (err: any) {
      toast({ title: "Failed to save key", description: err.message, variant: "destructive" });
    } finally {
      setSavingClaude(false);
    }
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
          <CardDescription>Configure your AI provider API keys for image generation and text processing. Keys are stored securely on the server.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Nano Banana API Key</Label>
            <div className="flex items-center gap-1 mb-1">
              <a
                href="https://aistudio.google.com/app/apikey"
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-primary hover:underline flex items-center gap-1"
              >
                <ExternalLink className="h-3 w-3" /> Get your Nano Banana / Gemini API key
              </a>
            </div>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Input
                  type={showNanoKey ? "text" : "password"}
                  placeholder={savedNanoKey === "configured" ? "Key is configured on server" : "Enter your Nano Banana API key"}
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
              <Button onClick={saveNanoKey} disabled={!nanoBananaKey.trim() || savingNano}>
                <Save className="h-4 w-4 mr-1" /> Save
              </Button>
            </div>
            {savedNanoKey === "configured" && (
              <p className="text-xs text-green-600 font-medium">Key is configured on server</p>
            )}
          </div>

          <Separator />

          <div className="space-y-2">
            <Label>Gemini API Key</Label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Input
                  type={showGeminiKey ? "text" : "password"}
                  placeholder={savedGeminiKey === "configured" ? "Key is configured on server" : "Enter your Google Gemini API key"}
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
              <Button onClick={saveGeminiKey} disabled={!geminiKey.trim() || savingGemini}>
                <Save className="h-4 w-4 mr-1" /> Save
              </Button>
            </div>
            {savedGeminiKey === "configured" && (
              <p className="text-xs text-green-600 font-medium">Key is configured on server</p>
            )}
          </div>

          <Separator />

          <div className="space-y-2">
            <Label>Claude API Key</Label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Input
                  type={showClaudeKey ? "text" : "password"}
                  placeholder={savedClaudeKey === "configured" ? "Key is configured on server" : "Enter your Claude API key"}
                  value={claudeKey}
                  onChange={(e) => setClaudeKey(e.target.value)}
                />
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7"
                  onClick={() => setShowClaudeKey(!showClaudeKey)}
                >
                  {showClaudeKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
              <Button onClick={saveClaudeKey} disabled={!claudeKey.trim() || savingClaude}>
                <Save className="h-4 w-4 mr-1" /> Save
              </Button>
            </div>
            {savedClaudeKey === "configured" && (
              <p className="text-xs text-green-600 font-medium">Key is configured on server</p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Claude Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings2 className="h-5 w-5" />
            Claude Model Configuration
          </CardTitle>
          <CardDescription>Configure which Claude model to use, max tokens, and temperature. These override defaults.</CardDescription>
        </CardHeader>
        <CardContent>
          <ClaudeConfigSection />
        </CardContent>
      </Card>

      {/* Pricing */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sliders className="h-5 w-5" />
            Pricing Configuration
          </CardTitle>
          <CardDescription>Set the cost per image generation and per Claude API call. Used for credit calculations.</CardDescription>
        </CardHeader>
        <CardContent>
          <PricingSection />
        </CardContent>
      </Card>

      {/* Image-to-Image Model Selection */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Image className="h-5 w-5" />
            Image-to-Image Model Selection
          </CardTitle>
          <CardDescription>Choose which AI model to use for image-to-image generation. Configure API keys above for the selected provider.</CardDescription>
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
          <CardDescription>Set your monthly spending limit in cents. Balance shown on the dashboard is budget minus actual usage.</CardDescription>
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
          <CardDescription>Set the root output directory for scraped products and images. Each product gets its own sub-folder.</CardDescription>
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
          <CardDescription>Scraply API credit consumption for CAPTCHA bypass. 3 accounts pooled, ~6 credits per product (datacenter + JS render). Resets monthly.</CardDescription>
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
          <CardDescription>Configure Google Drive integration using a service account</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <DriveCredentialsSection />
        </CardContent>
      </Card>
    </div>
  );
}
