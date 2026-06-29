"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useNotificationsStore } from "@/lib/store";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { CheckCheck, Bell, BellOff, CheckCircle2, XCircle, Loader2, ArrowLeft, Cloud, AlertCircle, Sparkles } from "lucide-react";
import { formatDateTime, statusLabel, getProductDetailUrl } from "@/lib/utils";
import Link from "next/link";

const typeIcons: Record<string, any> = {
  upload_completed: CheckCircle2,
  processing_started: Loader2,
  processing_finished: CheckCircle2,
  project_completed: CheckCircle2,
  generation_failed: XCircle,
  delivery_completed: CheckCircle2,
  drive_saved: Cloud,
  scraping_finished: Sparkles,
  scraping_failed: AlertCircle,
};

const typeColors: Record<string, string> = {
  upload_completed: "text-blue-500",
  processing_started: "text-yellow-500",
  processing_finished: "text-success",
  project_completed: "text-success",
  generation_failed: "text-destructive",
  delivery_completed: "text-cyan-500",
  drive_saved: "text-green-500",
  scraping_finished: "text-purple-500",
  scraping_failed: "text-orange-500",
};

export default function NotificationsPage() {
  const queryClient = useQueryClient();
  const { notifications, unreadCount, markRead, markAllRead } = useNotificationsStore();

  const { isLoading } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.getNotifications().then((data) => {
      useNotificationsStore.getState().setNotifications(data.notifications, data.unread_count);
      return data;
    }),
  });

  const markReadMutation = useMutation({
    mutationFn: (id: string) => api.markNotificationRead(id),
    onSuccess: (_, id) => markRead(id),
  });

  const markAllMutation = useMutation({
    mutationFn: () => api.markAllNotificationsRead(),
    onSuccess: () => markAllRead(),
  });

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/dashboard">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Notifications</h1>
            <p className="text-muted-foreground">
              {unreadCount > 0 ? `${unreadCount} unread` : "All caught up"}
            </p>
          </div>
        </div>
        {unreadCount > 0 && (
          <Button variant="outline" onClick={() => markAllMutation.mutate()} disabled={markAllMutation.isPending}>
            <CheckCheck className="h-4 w-4 mr-2" /> Mark all read
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Card key={i}><CardContent className="p-4"><Skeleton className="h-12 w-full" /></CardContent></Card>
          ))}
        </div>
      ) : notifications.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <BellOff className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-lg font-medium">No notifications</p>
            <p className="text-sm text-muted-foreground">Notifications will appear here as your projects progress</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {notifications.map((n) => {
            const Icon = typeIcons[n.type] || Bell;
            return (
              <Card
                key={n.id}
                className={`transition-colors ${!n.read ? "border-primary/50 bg-primary/5" : ""}`}
                onClick={() => { if (!n.read) markReadMutation.mutate(n.id); }}
              >
                <CardContent className="p-4 flex items-start gap-3 cursor-pointer">
                  <Icon className={`h-5 w-5 mt-0.5 shrink-0 ${typeColors[n.type] || "text-muted-foreground"}`} />
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm ${!n.read ? "font-semibold" : ""}`}>{n.title}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{n.message}</p>
                    <p className="text-xs text-muted-foreground/60 mt-1">{formatDateTime(n.created_at)}</p>
                    {n.data?.product_id && (
                      <Link
                        href={getProductDetailUrl(n.data.product_id)}
                        className="text-xs text-primary hover:underline mt-1 inline-block"
                        onClick={(e) => e.stopPropagation()}
                      >
                        View product →
                      </Link>
                    )}
                    {n.data?.batch_id && (
                      <Link
                        href={`/projects/${n.data.batch_id}`}
                        className="text-xs text-primary hover:underline mt-1 ml-2 inline-block"
                        onClick={(e) => e.stopPropagation()}
                      >
                        View project →
                      </Link>
                    )}
                    {n.data?.project_name && (
                      <span className="text-xs text-muted-foreground mt-1 ml-2 inline-block">
                        {n.data.project_name}
                      </span>
                    )}
                  </div>
                  {!n.read && (
                    <span className="h-2 w-2 rounded-full bg-primary shrink-0 mt-2" />
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
