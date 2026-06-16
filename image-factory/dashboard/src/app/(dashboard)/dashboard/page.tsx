"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  Package, Image, Loader2, CheckCircle2, XCircle, Timer, TrendingUp, HardDrive,
} from "lucide-react";
import { SystemReadinessPanel } from "@/components/dashboard/system-readiness";
import { ActiveJobsPanel } from "@/components/dashboard/active-jobs-panel";
import { AdminControlsPanel } from "@/components/dashboard/admin-controls-panel";
import { useSSE, useSSEEvent, subscribe } from "@/hooks/use-sse";

const REFETCH_INTERVAL = 3000;

function EtaCounter({ seconds }: { seconds: number }) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return <span className="font-mono text-xs">{m}m {s}s</span>;
}

export default function DashboardPage() {
  useSSE();

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () => api.getDashboardStats(),
    refetchInterval: REFETCH_INTERVAL,
  });

  const { data: queue } = useQuery({
    queryKey: ["queue-info"],
    queryFn: () => api.getQueueInfo(),
    refetchInterval: REFETCH_INTERVAL,
  });

  const { data: systemStatus } = useQuery({
    queryKey: ["system-status"],
    queryFn: () => api.getSystemStatus(),
    refetchInterval: 15000,
  });

  const total = stats?.total_products ?? 0;
  const completed = stats?.products_completed ?? 0;
  const failed = stats?.products_failed ?? 0;
  const processing = stats?.products_processing ?? 0;
  const inQueue = stats?.products_in_queue ?? 0;
  const totalImages = stats?.total_images ?? 0;
  const doneRate = total > 0 ? Math.round(((completed + failed) / total) * 100) : 0;

  const isLoading = statsLoading;

  const allHealthy = systemStatus && Object.values(systemStatus).every((v) => v === "healthy");
  const degradedCount = systemStatus ? Object.entries(systemStatus).filter(([k, v]) => k !== "api" && v !== "healthy").length : 0;

  if (isLoading) return <Skeleton className="h-96 w-full rounded-xl" />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Real-time overview</p>
        </div>
        <div className="flex items-center gap-2">
          {allHealthy ? (
            <Badge variant="outline" className="gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              All Systems Go
            </Badge>
          ) : degradedCount > 0 ? (
            <Badge variant="outline" className="gap-1.5 border-amber-500/30">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse" />
              {degradedCount} degraded
            </Badge>
          ) : (
            <Badge variant="outline" className="gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-success animate-pulse" />
              Live
            </Badge>
          )}
        </div>
      </div>

      {/* Big progress ring */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center gap-8">
            <div className="relative h-28 w-28 shrink-0">
              <svg className="h-full w-full -rotate-90" viewBox="0 0 100 100">
                <circle cx="50" cy="50" r="42" fill="none" stroke="hsl(var(--muted))" strokeWidth="8" />
                <circle cx="50" cy="50" r="42" fill="none" stroke="hsl(var(--primary))" strokeWidth="8"
                  strokeDasharray={`${doneRate * 2.64} 264`} strokeLinecap="round"
                  className="transition-all duration-500" />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-2xl font-bold">{doneRate}%</span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm flex-1">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-primary" />
                <span className="text-muted-foreground">Completed</span>
                <span className="font-semibold ml-auto">{completed}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-blue-500" />
                <span className="text-muted-foreground">Processing</span>
                <span className="font-semibold ml-auto">{processing}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-yellow-500" />
                <span className="text-muted-foreground">In Queue</span>
                <span className="font-semibold ml-auto">{inQueue}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-destructive" />
                <span className="text-muted-foreground">Failed</span>
                <span className="font-semibold ml-auto">{failed}</span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Stat cards row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard icon={Package} label="Total Products" value={total} />
        <StatCard icon={Image} label="Images Generated" value={totalImages} />
        <StatCard icon={TrendingUp} label="AI Credits" value={stats?.ai_credits_used ?? 0} />
        <StatCard icon={Timer} label="Avg Time" value={stats?.avg_processing_time_seconds ? `${Math.round(stats.avg_processing_time_seconds / 60)}m` : "\u2014"} />
      </div>

      {/* Queue + Storage + Active Jobs + Admin Controls */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
              Queue
            </CardTitle>
          </CardHeader>
          <CardContent>
            {queue ? (
              <div className="space-y-3">
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div>
                    <div className="text-xl font-bold text-blue-500">{queue.active_jobs}</div>
                    <div className="text-xs text-muted-foreground">Active</div>
                  </div>
                  <div>
                    <div className="text-xl font-bold text-yellow-500">{queue.waiting_jobs}</div>
                    <div className="text-xs text-muted-foreground">Waiting</div>
                  </div>
                  <div>
                    <div className="text-xl font-bold text-destructive">{queue.failed_jobs}</div>
                    <div className="text-xs text-muted-foreground">Failed</div>
                  </div>
                </div>
                <Progress value={queue.active_jobs + queue.waiting_jobs > 0 ? ((queue.active_jobs) / (queue.active_jobs + queue.waiting_jobs + queue.failed_jobs)) * 100 : 0} className="h-1.5" />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>{queue.workers_active} workers active</span>
                  <span>Est. {queue.estimated_completion_minutes}m</span>
                </div>
              </div>
            ) : (
              <Skeleton className="h-20 w-full" />
            )}
          </CardContent>
        </Card>

        <AdminControlsPanel />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ActiveJobsPanel />

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <HardDrive className="h-3.5 w-3.5" />
              Nano Banana Credits
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-xl font-bold">${(stats?.estimated_cost ? (stats.estimated_cost / 100).toFixed(2) : "0.00")}</div>
            <p className="text-xs text-muted-foreground">
              Balance: ${(stats?.nano_banana_balance ? (stats.nano_banana_balance / 100).toFixed(2) : "0.00")} &middot; ${(stats?.nano_banana_cost_per_image || 1).toFixed(2)}/img
            </p>
          </CardContent>
        </Card>
      </div>

      <SystemReadinessPanel />
    </div>
  );
}

function StatCard({ icon: Icon, label, value }: { icon: any; label: string; value: string | number }) {
  return (
    <Card>
      <CardContent className="p-4 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
          <Icon className="h-5 w-5 text-primary" />
        </div>
        <div>
          <div className="text-lg font-bold">{value}</div>
          <div className="text-xs text-muted-foreground">{label}</div>
        </div>
      </CardContent>
    </Card>
  );
}
