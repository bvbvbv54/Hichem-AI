import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn, statusColor } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

interface OverviewCardProps {
  title: string;
  value: string | number;
  icon: LucideIcon;
  description?: string;
  trend?: "up" | "down" | "warning" | "info";
}

export function OverviewCard({ title, value, icon: Icon, description, trend }: OverviewCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        <Icon className={cn("h-4 w-4", trend === "up" && "text-success", trend === "down" && "text-destructive", trend === "warning" && "text-warning", trend === "info" && "text-blue-500")} />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {description && <p className="text-xs text-muted-foreground mt-1">{description}</p>}
      </CardContent>
    </Card>
  );
}
