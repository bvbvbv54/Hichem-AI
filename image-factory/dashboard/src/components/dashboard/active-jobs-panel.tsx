"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { Loader2, CheckCircle2, XCircle, Clock, ChevronDown, ChevronUp } from "lucide-react";
import type { ActiveJob } from "@/types";

const stageOrder = ["pending", "extracting", "translating", "repositioning", "generating_images", "delivering", "completed"];

function jobStageIndex(status: string): number {
  const idx = stageOrder.indexOf(status);
  return idx >= 0 ? idx : -1;
}

function stageLabel(status: string): string {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusIcon(status: string) {
  if (status === "completed") return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
  if (status === "failed") return <XCircle className="h-4 w-4 text-rose-500" />;
  return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
}

function StatusBadge({ status }: { status: string }) {
  const variant: Record<string, string> = {
    completed: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
    failed: "bg-rose-500/10 text-rose-500 border-rose-500/20",
    pending: "bg-muted text-muted-foreground border-muted-foreground/20",
  };
  return (
    <Badge className={cn(variant[status] || "bg-blue-500/10 text-blue-500 border-blue-500/20", "text-[10px] px-1.5 py-0")}>
      {stageLabel(status)}
    </Badge>
  );
}

function JobRow({ job }: { job: ActiveJob }) {
  const [expanded, setExpanded] = useState(false);
  const stageIdx = jobStageIndex(job.status);
  const totalStages = stageOrder.length - 1;
  const pct = stageIdx >= 0 ? Math.round((stageIdx / totalStages) * 100) : 0;

  return (
    <div className="border border-muted-foreground/10 rounded-lg p-3 hover:bg-muted/20 transition-colors">
      <div className="flex items-center justify-between gap-2 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <div className="flex items-center gap-2 min-w-0 flex-1">
          {statusIcon(job.status)}
          <span className="text-xs font-semibold truncate">{job.project_name || job.id.slice(0, 8)}</span>
          <StatusBadge status={job.status} />
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[10px] text-muted-foreground">{job.num_images} img</span>
          {expanded ? <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />}
        </div>
      </div>
      {expanded && (
        <div className="mt-3 space-y-2 text-xs text-muted-foreground">
          <div className="flex justify-between">
            <span>ID</span>
            <span className="font-mono text-foreground/80">{job.id}</span>
          </div>
          <div className="flex justify-between">
            <span>Type</span>
            <span className="font-medium">{job.type}</span>
          </div>
          <div className="flex justify-between">
            <span>Progress</span>
            <span className="font-medium">{pct}%</span>
          </div>
          <Progress value={pct} className="h-1" />
          {job.prompt && (
            <p className="text-[10px] truncate mt-1">Prompt: {job.prompt}</p>
          )}
          {job.error_message && (
            <p className="text-[10px] text-rose-400 truncate">Error: {job.error_message}</p>
          )}
          <div className="flex items-center gap-1 text-[10px]">
            <Clock className="h-3 w-3" />
            {new Date(job.created_at).toLocaleString()}
          </div>
        </div>
      )}
    </div>
  );
}

export function ActiveJobsPanel() {
  const { data: jobs, isLoading } = useQuery({
    queryKey: ["active-jobs"],
    queryFn: () => api.getActiveJobs(),
    refetchInterval: 5000,
  });

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
          Active Jobs
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-12 w-full rounded-lg" />)}
          </div>
        ) : jobs && jobs.length > 0 ? (
          <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
            {jobs.map((job) => <JobRow key={job.id} job={job} />)}
          </div>
        ) : (
          <div className="text-center text-xs text-muted-foreground py-6">No active jobs</div>
        )}
      </CardContent>
    </Card>
  );
}
