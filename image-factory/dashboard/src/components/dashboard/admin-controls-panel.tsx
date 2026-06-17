"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  RotateCcw,
} from "lucide-react";

export function AdminControlsPanel() {
  const queryClient = useQueryClient();

  const retryAllMutation = useMutation({
    mutationFn: () => api.retryAllFailed(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["active-jobs"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
    },
  });

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-primary" />
          Admin Controls
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Button variant="outline" size="sm" className="gap-1.5 text-xs h-8 w-full" onClick={() => retryAllMutation.mutate()} disabled={retryAllMutation.isPending}>
          <RotateCcw className="h-3.5 w-3.5" />
          Retry All Failed
        </Button>
      </CardContent>
    </Card>
  );
}
