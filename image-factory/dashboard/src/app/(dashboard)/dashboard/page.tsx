"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  Activity, Settings, ShieldAlert, RefreshCw,
  DollarSign, Database, BarChart3,
} from "lucide-react";
import Link from "next/link";

const statusColor: Record<string, string> = {
  healthy: "text-emerald-500",
  degraded: "text-amber-500",
  offline: "text-rose-500",
  working: "text-emerald-500",
  unreachable: "text-rose-500",
  ACTIVE: "text-emerald-500",
  QUOTA_EXHAUSTED: "text-amber-500",
  BANNED: "text-rose-500",
};

function StatCard({ icon, label, value, sub, color }: { icon: any; label: string; value: string | number; sub?: string; color?: string }) {
  return (
    <Card>
      <CardContent className="p-4 flex items-start gap-3">
        <div className="rounded-lg bg-primary/10 p-2 shrink-0 mt-0.5">
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className={cn("text-xl font-bold truncate", color)}>{value}</p>
          {sub && <p className="text-[10px] text-muted-foreground">{sub}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    healthy: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
    degraded: "bg-amber-500/10 text-amber-500 border-amber-500/20",
    offline: "bg-rose-500/10 text-rose-500 border-rose-500/20",
    ACTIVE: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
    QUOTA_EXHAUSTED: "bg-amber-500/10 text-amber-500 border-amber-500/20",
    BANNED: "bg-rose-500/10 text-rose-500 border-rose-500/20",
    UNREACHABLE: "bg-muted text-muted-foreground border-border/50",
  };
  return <Badge className={cn(colors[status] || "bg-muted text-muted-foreground", "text-[10px]")}>{status}</Badge>;
}

interface ScrapflyKey {
  safe_label: string;
  status: string;
  used: number;
  remaining: number | null;
}

export default function DashboardPage() {
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["dash-stats"],
    queryFn: () => api.getAdminStats(),
  });

  const { data: scrapflyKeys } = useQuery({
    queryKey: ["scrapfly-keys-dash"],
    queryFn: () => api.getScrapflyUsage(),
  });

  const { data: queueStatus } = useQuery({
    queryKey: ["queue-status-dash"],
    queryFn: () => api.getQueueStatus(),
  });

  const { data: systemStatus } = useQuery({
    queryKey: ["system-status-dash"],
    queryFn: () => api.getSystemStatus(),
  });

  const { data: aiLimiter } = useQuery({
    queryKey: ["ai-limiter-dash"],
    queryFn: () => api.getAiLimiter(),
  });

  const { data: acquisition } = useQuery({
    queryKey: ["acq-stats-dash"],
    queryFn: () => api.getAcquisitionStats(),
  });

  const refreshAll = async () => {
    setRefreshing(true);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["dash-stats"] }),
      queryClient.invalidateQueries({ queryKey: ["scrapfly-keys-dash"] }),
      queryClient.invalidateQueries({ queryKey: ["queue-status-dash"] }),
      queryClient.invalidateQueries({ queryKey: ["system-status-dash"] }),
      queryClient.invalidateQueries({ queryKey: ["ai-limiter-dash"] }),
      queryClient.invalidateQueries({ queryKey: ["acq-stats-dash"] }),
    ]);
    setRefreshing(false);
  };

  if (statsLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
      </div>
    );
  }

  const keys: ScrapflyKey[] = scrapflyKeys?.keys || scrapflyKeys?.per_key_summary || [];
  const workingKeys = keys.filter((k) => k.status === "ACTIVE" && (k.remaining || 0) > 0).length;
  const exhaustedKeys = keys.filter((k) => k.status === "QUOTA_EXHAUSTED").length;
  const bannedKeys = keys.filter((k) => k.status === "BANNED").length;
  const unreachableKeys = keys.filter((k) => k.status === "UNREACHABLE").length;
  const totalKeys = keys.length;

  const qs = queueStatus || {};
  const infra = systemStatus || stats?.infrastructure || {};
  const svcList = ["api", "worker", "database", "storage"] as const;
  const allHealthy = svcList.every((s) => infra[s] === "healthy");

  const acqTotals = acquisition?.totals || {};
  const aiLimit = aiLimiter || {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">System overview at a glance</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={refreshAll} disabled={refreshing}>
            <RefreshCw className={cn("h-4 w-4 mr-1", refreshing && "animate-spin")} />
            {refreshing ? "Refreshing..." : "Refresh"}
          </Button>
          <Link href="/settings">
            <Button variant="outline" size="sm">
              <Settings className="h-4 w-4 mr-1" /> Settings
            </Button>
          </Link>
          <Link href="/admin">
            <Button variant="outline" size="sm">
              <BarChart3 className="h-4 w-4 mr-1" /> Admin
            </Button>
          </Link>
        </div>
      </div>

      {/* Top Stats Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          icon={<ShieldAlert className="h-4 w-4 text-amber-500" />}
          label="Scrapfly API Keys"
          value={totalKeys > 0 ? `${workingKeys} working` : "No keys configured"}
          color={bannedKeys > 0 ? "text-rose-500" : exhaustedKeys > 0 ? "text-amber-500" : "text-emerald-500"}
          sub={totalKeys > 0 ? `${unreachableKeys} unreachable, ${exhaustedKeys} exhausted, ${bannedKeys} banned` : undefined}
        />
        <StatCard
          icon={<DollarSign className="h-4 w-4 text-emerald-500" />}
          label="AI Credits Used"
          value={`$${aiLimit.usage_dollars?.toFixed(2) || "0.00"}`}
          color="text-emerald-500"
          sub={`of $${aiLimit.monthly_budget_dollars?.toFixed(2) || "0.00"} monthly budget`}
        />
        <StatCard
          icon={<Activity className="h-4 w-4 text-blue-500" />}
          label="Queue"
          value={`${qs.pending || 0} pending / ${qs.processing || 0} active`}
          color="text-blue-500"
          sub={`${qs.failed || 0} failed${qs.dead_letter_count ? ` (${qs.dead_letter_count} dead letter)` : ""}`}
        />
        <StatCard
          icon={<Database className="h-4 w-4 text-violet-500" />}
          label="System"
          value={allHealthy ? "All Healthy" : "Issues Detected"}
          color={allHealthy ? "text-emerald-500" : "text-rose-500"}
          sub={
            svcList
              .filter((s) => infra[s] !== "healthy")
              .map((s) => `${s}: ${infra[s]}`)
              .join(", ") || "All services operational"
          }
        />
      </div>

      {/* Scrapfly Keys Detail + Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <ShieldAlert className="h-4 w-4" />
              Scrapfly API Keys
            </CardTitle>
            <Link href="/settings">
              <Button variant="ghost" size="sm" className="h-7 text-xs gap-1">
                <Settings className="h-3 w-3" /> Manage
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {totalKeys === 0 ? (
              <div className="flex flex-col items-center gap-2 py-4 text-center">
                <ShieldAlert className="h-8 w-8 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">No Scrapfly API keys configured</p>
                <Link href="/settings">
                  <Button size="sm" variant="outline" className="mt-1">
                    <Settings className="h-4 w-4 mr-1" /> Add keys in Settings
                  </Button>
                </Link>
              </div>
            ) : (
              <div className="space-y-2">
                {keys.slice(0, 10).map((k: ScrapflyKey, i: number) => (
                  <div key={i} className="flex items-center justify-between text-xs border-b border-border/30 pb-1.5 last:border-0">
                    <span className="font-mono text-muted-foreground truncate max-w-[120px]">{k.safe_label}</span>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={k.status} />
                      {k.remaining !== null && k.remaining !== undefined && (
                        <span className="text-muted-foreground">{k.remaining} remaining</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Activity className="h-4 w-4" />
              Pipeline Activity
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-lg border p-2">
                <p className="text-lg font-bold text-yellow-500">{acqTotals.pending || 0}</p>
                <p className="text-[10px] text-muted-foreground">Pending</p>
              </div>
              <div className="rounded-lg border p-2">
                <p className="text-lg font-bold text-blue-500">{acqTotals.scraping || 0}</p>
                <p className="text-[10px] text-muted-foreground">Scraping</p>
              </div>
              <div className="rounded-lg border p-2">
                <p className="text-lg font-bold text-emerald-500">{acqTotals.completed || 0}</p>
                <p className="text-[10px] text-muted-foreground">Completed</p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 text-center">
              <div className="rounded-lg border p-2">
                <p className="text-lg font-bold text-indigo-500">{acqTotals.scraped || 0}</p>
                <p className="text-[10px] text-muted-foreground">Scraped</p>
              </div>
              <div className="rounded-lg border p-2">
                <p className="text-lg font-bold text-rose-500">{acqTotals.failed || 0}</p>
                <p className="text-[10px] text-muted-foreground">Failed</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* System Status Row */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Database className="h-4 w-4" />
            Infrastructure
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {svcList.map((s) => (
              <div key={s} className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs">
                <span className={cn(
                  "h-2 w-2 rounded-full",
                  infra[s] === "healthy" ? "bg-emerald-500" : "bg-rose-500"
                )} />
                <span className="font-medium capitalize">{s}</span>
                <StatusBadge status={infra[s] || "unknown"} />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
