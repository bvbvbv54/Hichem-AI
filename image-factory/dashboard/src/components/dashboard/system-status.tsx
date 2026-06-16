import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { SystemStatus } from "@/types";
import { cn } from "@/lib/utils";

interface Props {
  status: SystemStatus | null;
}

const services: { key: keyof SystemStatus; label: string }[] = [
  { key: "api", label: "API" },
  { key: "worker", label: "Worker" },
  { key: "queue", label: "Queue" },
  { key: "database", label: "Database" },
  { key: "storage", label: "Storage" },
  { key: "delivery", label: "Delivery" },
];

export function SystemStatusPanel({ status }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-success animate-pulse-dot" />
          System Status
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!status ? (
          <div className="space-y-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {services.map((svc) => {
              const state = status[svc.key];
              return (
                <div key={svc.key} className="flex items-center justify-between rounded-lg border px-3 py-2">
                  <span className="text-sm font-medium">{svc.label}</span>
                  <Badge
                    variant={
                      state === "healthy"
                        ? "success"
                        : state === "warning"
                        ? "warning"
                        : "destructive"
                    }
                  >
                    {state}
                  </Badge>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
