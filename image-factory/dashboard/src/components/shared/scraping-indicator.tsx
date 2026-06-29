"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Loader2, ExternalLink } from "lucide-react";
import Link from "next/link";

export function ScrapingIndicator() {
  const { data } = useQuery({
    queryKey: ["active-scraping-jobs"],
    queryFn: () => api.getActiveScrapingJobs(),
    refetchInterval: 5000,
  });

  const activeProjects = data?.active_projects || [];
  if (activeProjects.length === 0) return null;

  const totalActive = data?.total_active || 0;
  const totalCompleted = activeProjects.reduce((s: number, p: any) => s + (p.completed_count || 0), 0);
  const totalFailed = activeProjects.reduce((s: number, p: any) => s + (p.failed_count || 0), 0);
  const totalProducts = activeProjects.reduce((s: number, p: any) => s + (p.total_products || 0), 0);
  const done = totalCompleted + totalFailed;

  if (totalActive === 0 || totalProducts === 0) return null;
  if (done >= totalProducts) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50">
      {activeProjects.map((p: any) => (
        <Link
          key={p.project_id}
          href={`/projects/${p.project_id}`}
          className="flex items-center gap-3 bg-primary text-primary-foreground rounded-full shadow-lg px-4 py-2.5 hover:bg-primary/90 transition-colors text-sm"
        >
          <Loader2 className="h-4 w-4 animate-spin shrink-0" />
          <span>
            Scraping: {p.completed_count + p.failed_count}/{p.total_products} done
          </span>
          <ExternalLink className="h-3 w-3 shrink-0" />
        </Link>
      ))}
    </div>
  );
}
