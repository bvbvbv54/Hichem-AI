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
import { cn } from "@/lib/utils";
import { Key, Cloud, RefreshCw, Trash2, Eye, EyeOff, CheckCircle2, XCircle, Save, DollarSign, Image, FolderOpen, Zap, Ban, ShieldAlert, AlertTriangle, Table2, HardDrive } from "lucide-react";

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

  const { data: pricingData } = useQuery({
    queryKey: ["model-pricing-registry"],
    queryFn: () => api.getModelPricing({ include_hidden: true }),
    staleTime: 60000,
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

  const getModelMeta = (modelId: string) => {
    return pricingData?.models?.find((m: any) => m.model_id === modelId) || null;
  };

  const formatModelLabel = (m: any) => {
    const meta = getModelMeta(m.id);
    if (!meta) return `${m.name} (${m.provider})`;
    const costStr = meta.cost_per_output_image > 0
      ? `~$${meta.cost_per_output_image.toFixed(3)}/image`
      : meta.pricing_model;
    return `${meta.display_name} — ${costStr}`;
  };

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
              {availableModels.map((m: any) => {
                const meta = getModelMeta(m.id);
                const isDeprecated = meta?.deprecated;
                return (
                  <div key={m.id} className="flex items-center gap-2 px-2 py-1">
                    <SelectItem value={m.id} className="flex-1">
                      <span className="flex items-center gap-2">
                        {formatModelLabel(m)}
                        {isDeprecated && <span className="text-amber-500 text-xs">⚠️</span>}
                      </span>
                    </SelectItem>
                  </div>
                );
              })}
            </SelectContent>
          </Select>
          {/* Deprecation warning for selected model */}
          {(() => {
            const meta = getModelMeta(selectedModel);
            if (!meta?.deprecated) return null;
            return (
              <div className="mt-2 rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-950/20 p-3 space-y-1">
                <div className="flex items-center gap-2 text-xs font-medium text-amber-700 dark:text-amber-400">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  Deprecated Model
                </div>
                <p className="text-[11px] text-amber-600 dark:text-amber-500">
                  {meta.deprecation_message || "This model is deprecated."}
                </p>
                {meta.sunset_date && (
                  <p className="text-[11px] text-amber-600 dark:text-amber-500 font-medium">
                    This model will be removed after {meta.sunset_date}.
                  </p>
                )}
              </div>
            );
          })()}
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

function ModelPricingTable() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["model-pricing-table"],
    queryFn: () => api.getModelPricing({ include_hidden: true }),
    staleTime: 30000,
  });

  if (isLoading) return <Skeleton className="h-32 w-full" />;
  if (isError) return <p className="text-sm text-rose-500">Failed to load model pricing data.</p>;

  const models = data?.models || [];

  if (models.length === 0) {
    return <p className="text-sm text-muted-foreground">No models registered in the pricing table.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="pb-2 pr-3 font-medium">Model</th>
            <th className="pb-2 pr-3 font-medium">Tier</th>
            <th className="pb-2 pr-3 font-medium text-right">Output Cost</th>
            <th className="pb-2 pr-3 font-medium text-right">Reference Cost</th>
            <th className="pb-2 pr-3 font-medium">Pricing Model</th>
            <th className="pb-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {models.map((m: any) => {
            const isDeprecated = m.deprecated;
            const isHidden = m.is_hidden;
            let statusLabel = "Active";
            let statusColor = "text-emerald-600 dark:text-emerald-400";
            if (isHidden) {
              statusLabel = "Hidden (post-sunset)";
              statusColor = "text-muted-foreground";
            } else if (isDeprecated) {
              statusLabel = "Deprecated";
              statusColor = "text-amber-600 dark:text-amber-400";
            }
            return (
              <tr key={m.model_id} className={`border-b border-border/40 ${isHidden ? "opacity-40" : ""}`}>
                <td className="py-2 pr-3 font-medium">{m.display_name}</td>
                <td className="py-2 pr-3 text-muted-foreground">{m.model_id}</td>
                <td className="py-2 pr-3 text-right font-mono">
                  {m.cost_per_output_image > 0 ? `$${m.cost_per_output_image.toFixed(4)}` : "—"}
                </td>
                <td className="py-2 pr-3 text-right font-mono">
                  {m.cost_per_reference_image > 0 ? `$${m.cost_per_reference_image.toFixed(4)}` : "—"}
                </td>
                <td className="py-2 pr-3 text-muted-foreground">{m.pricing_model}</td>
                <td className={`py-2 font-medium ${statusColor}`}>
                  <span className="flex items-center gap-1">
                    {isDeprecated && !isHidden && <AlertTriangle className="h-3 w-3" />}
                    {statusLabel}
                  </span>
                  {isDeprecated && m.sunset_date && !isHidden && (
                    <span className="block text-[10px] text-muted-foreground">
                      Sunset: {m.sunset_date}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function CleanupToggleSection() {
  const [cleanupEnabled, setCleanupEnabled] = useState(true);
  const [toggling, setToggling] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    authFetch("/api/v1/admin/settings")
      .then((res) => res.json())
      .then((data) => {
        const val = data?.auto_cleanup_local;
        if (typeof val === "object" && val !== null) {
          setCleanupEnabled(val.value === true);
        } else if (typeof val === "boolean") {
          setCleanupEnabled(val);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const toggle = async () => {
    setToggling(true);
    try {
      const res = await authFetch("/api/v1/admin/settings/cleanup/toggle", {
        method: "PUT",
        body: JSON.stringify({ enabled: !cleanupEnabled }),
      });
      if (!res.ok) throw new Error(await res.text());
      setCleanupEnabled(!cleanupEnabled);
      toast({ title: `Auto-cleanup ${!cleanupEnabled ? "enabled" : "disabled"}` });
    } catch (err: any) {
      toast({ title: "Failed to toggle cleanup", description: err.message, variant: "destructive" });
    } finally {
      setToggling(false);
    }
  };

  if (loading) return <Skeleton className="h-16 w-full" />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <Label>Auto-cleanup local files</Label>
          <p className="text-xs text-muted-foreground">
            When enabled, the periodic task deletes local image files after R2 upload is confirmed via HEAD request.
            When disabled, the task logs what it would have deleted without removing files.
          </p>
        </div>
        <Switch checked={cleanupEnabled} onCheckedChange={toggle} disabled={toggling} />
      </div>
      <p className="text-xs text-muted-foreground">
        {cleanupEnabled
          ? "Cleanup runs every 30 minutes. Files are only deleted after R2 HEAD verification succeeds."
          : "Dry-run mode: the cleanup task will log deletions but not remove any files."}
      </p>
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

  const removeKey = async (keyId: string) => {
    try {
      const res = await authFetch("/api/v1/admin/scrapfly/keys", {
        method: "DELETE",
        body: JSON.stringify({ key_id: keyId }),
      });
      if (!res.ok) throw new Error(await res.text());
      toast({ title: "ScrapFly key removed" });
      queryClient.invalidateQueries({ queryKey: ["scrapfly-keys"] });
      queryClient.invalidateQueries({ queryKey: ["scrapfly-usage"] });
    } catch (err: any) {
      toast({ title: "Failed to remove key", description: err.message, variant: "destructive" });
    }
  };

  const banKey = async (keyId: string) => {
    try {
      const res = await authFetch(`/api/v1/admin/scrapfly/keys/${keyId}/ban`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      toast({ title: "Key banned", description: "This key will no longer count as working" });
      queryClient.invalidateQueries({ queryKey: ["scrapfly-keys"] });
      queryClient.invalidateQueries({ queryKey: ["scrapfly-usage"] });
    } catch (err: any) {
      toast({ title: "Failed to ban key", description: err.message, variant: "destructive" });
    }
  };

  const unbanKey = async (keyId: string) => {
    try {
      const res = await authFetch(`/api/v1/admin/scrapfly/keys/${keyId}/unban`, { method: "POST" });
      if (!res.ok) throw new Error(await res.text());
      toast({ title: "Key unbanned" });
      queryClient.invalidateQueries({ queryKey: ["scrapfly-keys"] });
      queryClient.invalidateQueries({ queryKey: ["scrapfly-usage"] });
    } catch (err: any) {
      toast({ title: "Failed to unban key", description: err.message, variant: "destructive" });
    }
  };

  if (keysLoading) return <Skeleton className="h-20 w-full" />;

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        {keys.map((k: any) => (
          <div key={k.safe_label || k.label || k.key_preview} className="flex items-center justify-between rounded-lg border p-2.5">
            <div className="flex items-center gap-2">
              <code className="text-xs font-mono text-muted-foreground">{k.safe_label || k.label || k.key_preview}</code>
              <Badge className={cn("text-[10px]", k.status === "BANNED" ? "bg-rose-500/10 text-rose-500" : k.status === "QUOTA_EXHAUSTED" ? "bg-amber-500/10 text-amber-500" : k.status === "ACTIVE" ? "bg-emerald-500/10 text-emerald-500" : "bg-muted text-muted-foreground")}>{k.status || "unknown"}</Badge>
              {k.remaining !== undefined && k.remaining !== null && (
                <Badge variant="outline" className="text-[10px] text-muted-foreground">{k.remaining} remaining</Badge>
              )}
              <Badge className="text-[10px] bg-muted text-muted-foreground">{k.used} used</Badge>
            </div>
            <div className="flex items-center gap-1">
              {k.status !== "BANNED" ? (
                <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => banKey(k.safe_label || k.label)} title="Mark as banned">
                  <Ban className="h-3.5 w-3.5 text-muted-foreground" />
                </Button>
              ) : (
                <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => unbanKey(k.safe_label || k.label)} title="Unban key">
                  <ShieldAlert className="h-3.5 w-3.5 text-emerald-500" />
                </Button>
              )}
              <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => removeKey(k.safe_label || k.label)}>
                <Trash2 className="h-3.5 w-3.5 text-destructive" />
              </Button>
            </div>
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
  const [replicateKey, setReplicateKey] = useState("");
  const [savedReplicateKey, setSavedReplicateKey] = useState(false);
  const [showReplicateKey, setShowReplicateKey] = useState(false);
  const [savingReplicate, setSavingReplicate] = useState(false);
  const [replicateKeyError, setReplicateKeyError] = useState("");

  const queryClient = useQueryClient();

  const { data: providerKeys, isLoading: keysLoading } = useQuery({
    queryKey: ["provider-keys"],
    queryFn: () => api.getProviderKeys(),
  });

  useEffect(() => {
    if (providerKeys?.google_api_key?.configured) {
      setSavedGoogleKey(true);
    }
    if (providerKeys?.replicate_api_key?.configured) {
      setSavedReplicateKey(true);
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

  const validateReplicateKey = (key: string): string => {
    if (!key.trim()) return "Key is required";
    if (!key.trim().startsWith("r8_") && !key.trim().startsWith("r8rk_")) return "Replicate API keys must start with 'r8_'";
    if (key.trim().length < 20) return "Key seems too short";
    return "";
  };

  const saveReplicateKey = async () => {
    const error = validateReplicateKey(replicateKey);
    if (error) {
      setReplicateKeyError(error);
      return;
    }
    setReplicateKeyError("");
    setSavingReplicate(true);
    try {
      const result = await authFetch("/api/v1/admin/provider-keys/replicate", {
        method: "PUT",
        body: JSON.stringify({ key: replicateKey.trim() }),
      });
      if (!result.ok) {
        const text = await result.text();
        throw new Error(text);
      }
      setSavedReplicateKey(true);
      setReplicateKey("");
      toast({ title: "Replicate API key saved" });
      queryClient.invalidateQueries({ queryKey: ["provider-keys"] });
    } catch (err: any) {
      toast({ title: "Failed to save key", description: err.message, variant: "destructive" });
    } finally {
      setSavingReplicate(false);
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

          {/* Replicate API Key (for FLUX model access) */}
          <div className="space-y-2">
            <Label>Replicate API Key</Label>
            <p className="text-xs text-muted-foreground">Required for FLUX.1 Schnell and other Replicate-hosted image generation models. Get one from <a href="https://replicate.com/account/api-tokens" target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">Replicate API Tokens</a>.</p>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Input
                  type={showReplicateKey ? "text" : "password"}
                  placeholder={savedReplicateKey ? "Key is configured on server" : "Enter your Replicate API key (starts with r8_...)"}
                  value={replicateKey}
                  onChange={(e) => {
                    setReplicateKey(e.target.value);
                    if (replicateKeyError) setReplicateKeyError("");
                  }}
                  className={replicateKeyError ? "border-red-500" : ""}
                />
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute right-1 top-1/2 -translate-y-1/2 h-7 w-7"
                  onClick={() => setShowReplicateKey(!showReplicateKey)}
                >
                  {showReplicateKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
              <Button onClick={saveReplicateKey} disabled={!replicateKey.trim() || savingReplicate}>
                <Save className="h-4 w-4 mr-1" /> Save
              </Button>
            </div>
            {replicateKeyError && <p className="text-xs text-red-500">{replicateKeyError}</p>}
            {savedReplicateKey && !replicateKey.trim() && (
              <p className="text-xs text-green-600 font-medium">Key is configured on server</p>
            )}
          </div>

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

      {/* Model Pricing Table */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Table2 className="h-5 w-5" />
            Model Pricing Registry
          </CardTitle>
          <CardDescription>System-managed pricing and lifecycle metadata for all image generation models. Sourced from the model_pricing database table.</CardDescription>
        </CardHeader>
        <CardContent>
          <ModelPricingTable />
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

      {/* Local File Cleanup */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <HardDrive className="h-5 w-5" />
            Local File Cleanup
          </CardTitle>
          <CardDescription>Automatically delete local image files after they are confirmed uploaded to R2. Files are only removed after HEAD verification confirms the remote copy is accessible.</CardDescription>
        </CardHeader>
        <CardContent>
          <CleanupToggleSection />
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