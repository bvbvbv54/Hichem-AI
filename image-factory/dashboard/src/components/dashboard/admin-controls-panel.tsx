"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  RefreshCw, RotateCcw, Trash2, HardDrive, ExternalLink,
} from "lucide-react";

export function AdminControlsPanel() {
  const queryClient = useQueryClient();
  const [driveUrl, setDriveUrl] = useState<string | null>(null);

  const { data: driveStatus } = useQuery({
    queryKey: ["drive-status"],
    queryFn: () => api.getDriveStatus().catch(() => null),
    retry: false,
  });

  const retryAllMutation = useMutation({
    mutationFn: () => fetch("/api/v1/admin/jobs/retry-all-failed", { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["active-jobs"] }),
  });

  const clearCompletedMutation = useMutation({
    mutationFn: () => fetch("/api/v1/admin/jobs/clear-completed", { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] }),
  });

  const startDriveAuthMutation = useMutation({
    mutationFn: () => api.startDriveAuth(),
    onSuccess: (data) => {
      if (data?.auth_url) window.open(data.auth_url, "_blank", "width=600,height=700");
    },
  });

  const clearNotificationsMutation = useMutation({
    mutationFn: () => api.clearAdminNotifications(),
  });

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-primary" />
          Admin Controls
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-2">
          <Button variant="outline" size="sm" className="gap-1.5 text-xs h-8" onClick={() => retryAllMutation.mutate()} disabled={retryAllMutation.isPending}>
            <RotateCcw className="h-3.5 w-3.5" />
            Retry All Failed
          </Button>
          <Button variant="outline" size="sm" className="gap-1.5 text-xs h-8" onClick={() => clearCompletedMutation.mutate()} disabled={clearCompletedMutation.isPending}>
            <Trash2 className="h-3.5 w-3.5" />
            Clear Completed
          </Button>
          <Button variant="outline" size="sm" className="gap-1.5 text-xs h-8" onClick={() => startDriveAuthMutation.mutate()} disabled={startDriveAuthMutation.isPending}>
            <HardDrive className="h-3.5 w-3.5" />
            {driveStatus?.authenticated ? "Re-auth Drive" : "Auth Drive"}
          </Button>
          <Button variant="outline" size="sm" className="gap-1.5 text-xs h-8" onClick={() => clearNotificationsMutation.mutate()} disabled={clearNotificationsMutation.isPending}>
            <RefreshCw className="h-3.5 w-3.5" />
            Clear Alerts
          </Button>
        </div>
        {driveStatus?.authenticated && (
          <div className="flex items-center justify-between rounded-lg bg-muted/30 p-2">
            <span className="text-xs text-muted-foreground">Drive: Connected</span>
            <Badge className="text-[10px] bg-emerald-500/10 text-emerald-500 border-emerald-500/20">
              {driveStatus.email || "Authenticated"}
            </Badge>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
