"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore, useAuthHydrated, useNotificationsStore } from "@/lib/store";
import { Sidebar } from "@/components/shared/sidebar";
import { Navbar } from "@/components/shared/navbar";
import { useUIStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { useSSE, useSSEEvent } from "@/hooks/use-sse";
import { useQueryClient } from "@tanstack/react-query";
import { ErrorBoundary } from "@/components/error-boundary";

function DashboardContent({ children }: { children: React.ReactNode }) {
  const { sidebarOpen } = useUIStore();
  const queryClient = useQueryClient();

  // Initialize SSE connection (non-blocking)
  useSSE();

  const invalidateAll = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
    queryClient.invalidateQueries({ queryKey: ["system-status"] });
    queryClient.invalidateQueries({ queryKey: ["queue-info"] });
    queryClient.invalidateQueries({ queryKey: ["projects"] });
    queryClient.invalidateQueries({ queryKey: ["project"] });
    queryClient.invalidateQueries({ queryKey: ["project-products"] });
    queryClient.invalidateQueries({ queryKey: ["assets"] });
    queryClient.invalidateQueries({ queryKey: ["admin-stats"] });
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
    queryClient.invalidateQueries({ queryKey: ["active-jobs"] });
    queryClient.invalidateQueries({ queryKey: ["content-stats"] });
    queryClient.invalidateQueries({ queryKey: ["content-products"] });
    queryClient.invalidateQueries({ queryKey: ["product-detail"] });
    queryClient.invalidateQueries({ queryKey: ["scrapfly-usage"] });
    queryClient.invalidateQueries({ queryKey: ["ai-limiter"] });
    queryClient.invalidateQueries({ queryKey: ["captcha-intel"] });
    queryClient.invalidateQueries({ queryKey: ["drive-credentials"] });
    queryClient.invalidateQueries({ queryKey: ["drive-config"] });
    queryClient.invalidateQueries({ queryKey: ["monthly-budget"] });
    queryClient.invalidateQueries({ queryKey: ["provider-keys"] });
    queryClient.invalidateQueries({ queryKey: ["img2img-config"] });
    queryClient.invalidateQueries({ queryKey: ["storage-config"] });
    queryClient.invalidateQueries({ queryKey: ["scrapfly-keys"] });
  }, [queryClient]);

  useSSEEvent("job_stage_changed", invalidateAll);
  useSSEEvent("job_completed", invalidateAll);
  useSSEEvent("job_failed", invalidateAll);
  useSSEEvent("batch_progress", invalidateAll);
  useSSEEvent("acquisition_alert", invalidateAll);
  useSSEEvent("system_alert", invalidateAll);
  useSSEEvent("drive_saved", (data) => {
    invalidateAll();
    const ns = useNotificationsStore.getState();
    const productName = data.product_name || data.data?.product_name || "Product";
    const fileCount = data.file_count || data.data?.file_count || 0;
    ns.addNotification({
      id: `drive-${Date.now()}`,
      type: "drive_saved",
      title: "Drive: Images Saved",
      message: `${fileCount} image${fileCount !== 1 ? "s" : ""} for '${productName}' uploaded to Google Drive`,
      read: false,
      created_at: new Date().toISOString(),
    });
  });

  useSSEEvent("notification", (data) => {
    const ns = useNotificationsStore.getState();
    ns.addNotification(data.notification);
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
  });

  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <div
        className={cn(
          "transition-all duration-300",
          sidebarOpen ? "ml-60" : "ml-16"
        )}
      >
        <Navbar />
        <main className="p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const hydrated = useAuthHydrated();
  const { token } = useAuthStore();
  const router = useRouter();
  const [hydrationTimeout, setHydrationTimeout] = useState(false);

  useEffect(() => {
    if (hydrated && !token) {
      router.push("/login");
    }
  }, [hydrated, token, router]);

  // Prevent infinite loading state by timing out hydration check
  useEffect(() => {
    const timeout = setTimeout(() => {
      setHydrationTimeout(true);
    }, 5000); // 5 second timeout

    return () => clearTimeout(timeout);
  }, []);

  // After hydration timeout, redirect to login if no token
  useEffect(() => {
    if (hydrationTimeout && !token) {
      router.push("/login");
    }
  }, [hydrationTimeout, token, router]);

  // Show loading state while hydrating (max 5s), then redirect to login if no token
  if (!hydrated && !hydrationTimeout) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <div className="flex flex-col items-center gap-4">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-muted border-t-primary" />
          <p className="text-sm text-muted-foreground">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  if (!token) {
    return null; // will be redirected by useEffect above
  }

  return (
    <ErrorBoundary>
      <DashboardContent>{children}</DashboardContent>
    </ErrorBoundary>
  );
}

