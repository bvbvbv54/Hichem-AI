"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  Package, Image, Loader2, CheckCircle2, XCircle, Timer, TrendingUp, HardDrive, ShieldAlert, Zap,
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

  const { data: captchaData } = useQuery({
    queryKey: ["captcha-intel"],
    queryFn: () => api.getCaptchaIntelligence().catch(() => null),
    refetchInterval: 30000,
  });

  const { data: scrapflyUsage } = useQuery({
    queryKey: ["scrapfly-usage"],
    queryFn: () => api.getScrapflyUsage().catch(() => null),
    refetchInterval: 30000,
  });

  const { data: aiLimiter } = useQuery({
    queryKey: ["ai-limiter"],
    queryFn: () => api.getAiLimiter().catch(() => null),
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
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <StatCard icon={Package} label="Total Products" value={total} />
        <StatCard icon={Image} label="Images Generated" value={totalImages} />
        <StatCard icon={TrendingUp} label="AI Credits" value={stats?.ai_credits_used ?? 0} />
        <StatCard icon={Timer} label="Avg Time" value={stats?.avg_processing_time_seconds ? `${Math.round(stats.avg_processing_time_seconds / 60)}m` : "\u2014"} />
        <StatCard icon={ShieldAlert} label="CAPTCHAs Today" value={captchaData?.total_captchas_today ?? 0} />
      </div>

      {/* Queue + Batch + CAPTCHA + Admin */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
              Queue / Batch
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

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <ShieldAlert className="h-3.5 w-3.5 text-amber-500" />
              CAPTCHA Intelligence
            </CardTitle>
          </CardHeader>
          <CardContent>
            {captchaData && captchaData.top_blocking_marketplaces ? (
              <div className="space-y-2">
                {captchaData.top_blocking_marketplaces.slice(0, 5).map((m: any) => (
                  <div key={m.domain} className="flex items-center justify-between text-xs">
                    <span className="font-medium truncate">{m.domain.replace(".com", "")}</span>
                    <Badge className="text-[10px] bg-rose-500/10 text-rose-500 border-rose-500/20 shrink-0">
                      {m.captcha_count}
                    </Badge>
                  </div>
                ))}
                {captchaData.top_blocking_marketplaces.length === 0 && (
                  <p className="text-xs text-muted-foreground">No CAPTCHA events recorded yet</p>
                )}
                <div className="flex justify-between text-[10px] text-muted-foreground pt-1 border-t border-muted-foreground/10">
                  <span>Total today: {captchaData.total_captchas_today}</span>
                  <span>7d window</span>
                </div>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">No CAPTCHA data available</p>
            )}
          </CardContent>
        </Card>

        <AdminControlsPanel />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <ActiveJobsPanel />

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <HardDrive className="h-3.5 w-3.5" />
              AI Limiter
            </CardTitle>
          </CardHeader>
          <CardContent>
            {aiLimiter ? (
              <>
                <div className="flex items-baseline gap-1">
                  <span className="text-2xl font-bold">${aiLimiter.usage_dollars}</span>
                  <span className="text-xs text-muted-foreground">of $${aiLimiter.monthly_budget_dollars}</span>
                </div>
                <div className="w-full bg-muted rounded-full h-2 mt-2">
                  <div className={`h-2 rounded-full transition-all ${
                    aiLimiter.usage_percent > 80 ? "bg-rose-500" :
                    aiLimiter.usage_percent > 50 ? "bg-amber-500" : "bg-emerald-500"
                  }`} style={{width: `${Math.min(aiLimiter.usage_percent, 100)}%`}} />
                </div>
                <div className="flex justify-between text-xs text-muted-foreground mt-1">
                  <span>${aiLimiter.remaining_dollars} left</span>
                  <span>{aiLimiter.usage_percent}% used</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {aiLimiter.total_images_this_month} images &middot; ${aiLimiter.cost_per_image_dollars}/img
                </p>
                {aiLimiter.low_credits && (
                  <p className="text-xs text-amber-500 font-medium mt-1">Low budget remaining</p>
                )}
                {aiLimiter.critical_credits && (
                  <p className="text-xs text-rose-500 font-medium mt-1">Critically low - generation may stop</p>
                )}
              </>
            ) : (
              <p className="text-xs text-muted-foreground">Budget data unavailable</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Zap className="h-3.5 w-3.5 text-amber-500" />
              ScrapFly Remaining
            </CardTitle>
          </CardHeader>
          <CardContent>
            {scrapflyUsage ? (
              <>
                <div className="flex items-baseline gap-1">
                  <span className="text-2xl font-bold">{scrapflyUsage.scrapes_remaining_actual ?? "?"}</span>
                  <span className="text-xs text-muted-foreground">scrapes left</span>
                </div>
                <div className="flex items-baseline gap-1">
                  <span className="text-lg font-semibold">{scrapflyUsage.remaining_credits ?? 0}</span>
                  <span className="text-xs text-muted-foreground">credits remain</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {scrapflyUsage.key_count ?? 0} key{(scrapflyUsage.key_count ?? 0) !== 1 ? "s" : ""} &middot; ~{scrapflyUsage.cost_per_product ?? 9} pts/product
                </p>
                {!scrapflyUsage.has_usage_data && (
                  <p className="text-xs text-muted-foreground mt-1">No requests yet - run a scrape to see usage</p>
                )}
                <div className="mt-1">
                  {(scrapflyUsage.per_key_summary || []).map((k: any) => (
                    <div key={k.key} className="flex justify-between text-[10px] text-muted-foreground">
                      <span className="font-mono truncate max-w-[140px]">{k.key}</span>
                      <span>{k.status === "tracked" ? `${k.remaining} left` : "N/A (untracked)"}</span>
                    </div>
                  ))}
                </div>
                {scrapflyUsage.scrapes_remaining_actual > 0 && scrapflyUsage.scrapes_remaining_actual < 10 && (
                  <p className="text-xs text-amber-500 font-medium mt-1">Low credits remaining</p>
                )}
                {scrapflyUsage.has_usage_data && scrapflyUsage.scrapes_remaining_actual === 0 && (
                  <p className="text-xs text-rose-500 font-medium mt-1">No credits left - add more keys</p>
                )}
              </>
            ) : (
              <p className="text-xs text-muted-foreground">Usage data unavailable</p>
            )}
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
