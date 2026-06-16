import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDuration } from "@/lib/utils";
import type { QueueInfo } from "@/types";

interface Props {
  queue: QueueInfo | null;
}

export function QueuePanel({ queue }: Props) {
  if (!queue) {
    return (
      <Card>
        <CardHeader><CardTitle className="text-lg">Queue</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-6 w-full" />
          ))}
        </CardContent>
      </Card>
    );
  }

  const totalJobs = queue.active_jobs + queue.waiting_jobs + queue.failed_jobs;
  const progress = totalJobs > 0 ? ((queue.active_jobs + queue.waiting_jobs) / totalJobs) * 100 : 100;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse-dot" />
          Queue
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-2xl font-bold">{queue.current_length}</div>
            <p className="text-xs text-muted-foreground">Total in queue</p>
          </div>
          <div>
            <div className="text-2xl font-bold">{queue.workers_active}</div>
            <p className="text-xs text-muted-foreground">Active workers</p>
          </div>
        </div>

        <Progress value={progress} className="h-2" />

        <div className="grid grid-cols-3 gap-2 text-center text-sm">
          <div>
            <span className="font-semibold text-blue-500">{queue.active_jobs}</span>
            <p className="text-xs text-muted-foreground">Active</p>
          </div>
          <div>
            <span className="font-semibold text-yellow-500">{queue.waiting_jobs}</span>
            <p className="text-xs text-muted-foreground">Waiting</p>
          </div>
          <div>
            <span className="font-semibold text-destructive">{queue.failed_jobs}</span>
            <p className="text-xs text-muted-foreground">Failed</p>
          </div>
        </div>

        <div className="rounded-lg bg-muted p-3 space-y-1">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Est. completion</span>
            <span className="font-medium">{formatDuration(queue.estimated_completion_minutes * 60)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Est. wait time</span>
            <span className="font-medium">{formatDuration(queue.estimated_wait_minutes * 60)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Retry jobs</span>
            <span className="font-medium">{queue.retry_jobs}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
