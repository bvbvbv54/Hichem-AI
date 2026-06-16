"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  Activity, CheckCircle2, XCircle, AlertTriangle, Play, Eye, RefreshCw, Coins, Clock, Database, Server, HardDrive, Inbox, Cpu, ShieldCheck
} from "lucide-react";

export function SystemReadinessPanel() {
  const queryClient = useQueryClient();
  const [dryRunData, setDryRunData] = useState<any>(null);
  const [isDryRunOpen, setIsDryRunOpen] = useState(false);

  const { data: readiness, isLoading: isLoadingReadiness } = useQuery({
    queryKey: ["system-readiness"],
    queryFn: () => api.getSystemReadiness(),
    refetchInterval: 5000,
  });

  const smokeTestMutation = useMutation({
    mutationFn: () => api.startSmokeTest(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["system-readiness"] });
    },
  });

  const dryRunMutation = useMutation({
    mutationFn: () => api.runDryRun(),
    onSuccess: (data) => {
      setDryRunData(data);
      setIsDryRunOpen(true);
    },
  });

  const components = readiness?.components || {};
  const latestSmokeTest = readiness?.latest_smoke_test || null;

  const componentLabels: Record<string, { label: string; icon: any }> = {
    api: { label: "Backend API", icon: Server },
    worker: { label: "Worker System", icon: Cpu },
    queue: { label: "Message Queue", icon: Inbox },
    database: { label: "PostgreSQL DB", icon: Database },
    redis: { label: "Redis Cache", icon: Activity },
    storage: { label: "Asset Storage", icon: HardDrive },
    delivery: { label: "Delivery Backends", icon: ShieldCheck },
    ai_provider: { label: "AI Provider Connectivity", icon: Activity },
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "healthy":
        return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
      case "warning":
        return <AlertTriangle className="h-4 w-4 text-amber-500 animate-pulse" />;
      default:
        return <XCircle className="h-4 w-4 text-rose-500 animate-bounce" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "healthy":
        return <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20">Healthy</Badge>;
      case "warning":
        return <Badge className="bg-amber-500/10 text-amber-500 border-amber-500/20">Warning</Badge>;
      default:
        return <Badge className="bg-rose-500/10 text-rose-500 border-rose-500/20">Offline</Badge>;
    }
  };

  return (
    <Card className="border-muted bg-card/60 backdrop-blur-md shadow-lg">
      <CardHeader className="pb-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <CardTitle className="text-xl font-bold tracking-tight flex items-center gap-2">
              <Activity className="h-5 w-5 text-primary" />
              System Readiness & Health
            </CardTitle>
            <CardDescription className="text-muted-foreground">
              Verify end-to-end platform stability, integrations, and worker execution flow.
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => dryRunMutation.mutate()}
              disabled={dryRunMutation.isPending}
              className="gap-1.5 border-muted-foreground/20 hover:bg-muted"
            >
              {dryRunMutation.isPending ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Eye className="h-3.5 w-3.5" />}
              Dry-Run Preview
            </Button>
            <Button
              variant="default"
              size="sm"
              onClick={() => smokeTestMutation.mutate()}
              disabled={smokeTestMutation.isPending}
              className="gap-1.5 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold"
            >
              {smokeTestMutation.isPending ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5 fill-current" />}
              Run Smoke Test
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {isLoadingReadiness ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full rounded-lg" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
            {Object.entries(componentLabels).map(([key, info]) => {
              const status = components[key] || "offline";
              const Icon = info.icon;
              return (
                <div
                  key={key}
                  className="flex items-center justify-between p-3 rounded-xl border border-muted-foreground/10 bg-muted/20 hover:bg-muted/40 transition-colors"
                >
                  <div className="flex items-center gap-2.5">
                    <div className="p-1.5 rounded-lg bg-background/80 border border-muted-foreground/10">
                      <Icon className="h-4 w-4 text-muted-foreground" />
                    </div>
                    <span className="text-xs font-semibold text-foreground/90">{info.label}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {getStatusIcon(status)}
                    {getStatusBadge(status)}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="border-t border-muted-foreground/10 pt-4">
          <div className="p-4 rounded-xl border border-muted-foreground/10 bg-muted/10 flex items-center justify-between">
            <span className="text-xs text-muted-foreground font-medium">Last Smoke Test</span>
            <div className="flex items-center gap-2">
              {latestSmokeTest ? (
                latestSmokeTest.status === "passed" ? (
                  <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20 font-bold px-2.5 py-1">PASSED</Badge>
                ) : (
                  <Badge className="bg-rose-500/10 text-rose-500 border-rose-500/20 font-bold px-2.5 py-1">FAILED</Badge>
                )
              ) : (
                <span className="text-sm font-semibold text-muted-foreground">Never run</span>
              )}
            </div>
          </div>
        </div>
      </CardContent>

      {/* Dry Run Preview Dialog */}
      <Dialog open={isDryRunOpen} onOpenChange={setIsDryRunOpen}>
        <DialogContent className="max-w-xl bg-card border border-muted shadow-2xl rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold flex items-center gap-2">
              <Eye className="h-5 w-5 text-primary" />
              Dry-Run Execution Preview
            </DialogTitle>
          </DialogHeader>
          {dryRunData && (
            <div className="space-y-4 text-sm mt-2">
              <p className="text-xs text-muted-foreground">
                This preview simulates the execution pipeline steps without performing any actual API generation calls or credit deductions.
              </p>
              <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                {dryRunData.steps.map((s: any, idx: number) => (
                  <div key={idx} className="flex justify-between items-start p-2.5 rounded-lg bg-muted/30 border border-muted-foreground/5">
                    <div>
                      <div className="font-bold text-xs capitalize text-foreground/90">{s.step.replace("_", " ")}</div>
                      <div className="text-[11px] text-muted-foreground mt-0.5">{s.action}</div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className="font-semibold text-xs text-primary">{s.estimated_cost_cents > 0 ? `$${(s.estimated_cost_cents / 100).toFixed(2)}` : "Free"}</div>
                      <div className="text-[10px] text-muted-foreground mt-0.5">{s.estimated_duration_s}s</div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="border-t border-muted-foreground/10 pt-3 flex items-center justify-between font-bold text-xs text-foreground/90">
                <span>Total Project Estimated Cost</span>
                <span className="text-primary text-sm">${(dryRunData.total_estimated_cost_cents / 100).toFixed(2)}</span>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button size="sm" variant="outline" onClick={() => setIsDryRunOpen(false)}>Close</Button>
                <Button size="sm" onClick={() => { setIsDryRunOpen(false); smokeTestMutation.mutate(); }}>Run Actual Test</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}
