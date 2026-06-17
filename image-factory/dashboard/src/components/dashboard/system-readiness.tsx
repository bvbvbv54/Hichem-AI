"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Activity, CheckCircle2, XCircle, AlertTriangle, Server, Cpu, Inbox, Database, HardDrive, ShieldCheck
} from "lucide-react";

export function SystemReadinessPanel() {
  const { data: readiness, isLoading: isLoadingReadiness } = useQuery({
    queryKey: ["system-readiness"],
    queryFn: () => api.getSystemReadiness(),
    refetchInterval: 15000,
  });

  const { data: captchaData } = useQuery({
    queryKey: ["captcha-intel"],
    queryFn: () => api.getCaptchaIntelligence().catch(() => null),
    refetchInterval: 30000,
  });

  const components = readiness?.components || {};

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
              Real-time platform stability, integrations, and CAPTCHA intelligence.
            </CardDescription>
          </div>
          {captchaData && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
              {captchaData.total_captchas_today} CAPTCHAs today
            </div>
          )}
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

        {captchaData && captchaData.top_blocking_marketplaces && captchaData.top_blocking_marketplaces.length > 0 && (
          <div className="border-t border-muted-foreground/10 pt-4">
            <div className="p-4 rounded-xl border border-muted-foreground/10 bg-muted/10">
              <h4 className="text-xs font-semibold text-muted-foreground mb-2">Top Blocking Marketplaces (7d)</h4>
              <div className="space-y-1.5">
                {captchaData.top_blocking_marketplaces.map((m: any) => (
                  <div key={m.domain} className="flex items-center justify-between text-xs">
                    <span className="font-medium">{m.domain}</span>
                    <Badge className="text-[10px] bg-rose-500/10 text-rose-500 border-rose-500/20">
                      {m.captcha_count} CAPTCHAs
                    </Badge>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}