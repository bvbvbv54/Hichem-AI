"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Grid3X3, List, Search, ImageIcon, Download } from "lucide-react";
import { formatDate, formatFileSize } from "@/lib/utils";

export default function AssetsPage() {
  const [view, setView] = useState<"grid" | "list">("grid");
  const [search, setSearch] = useState("");
  const [projectFilter, setProjectFilter] = useState("all");

  const { data: projectsData } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.listProjects({ limit: 100 }),
  });

  const { data, isLoading } = useQuery({
    queryKey: ["assets", search, projectFilter],
    queryFn: () =>
      api.listAssets({
        search: search || undefined,
        project_id: projectFilter !== "all" ? projectFilter : undefined,
        limit: 100,
      }),
  });

  const assets = data?.assets || [];
  const projects = projectsData?.projects || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Asset Library</h1>
          <p className="text-muted-foreground">Browse all generated images</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant={view === "grid" ? "default" : "outline"}
            size="icon"
            onClick={() => setView("grid")}
          >
            <Grid3X3 className="h-4 w-4" />
          </Button>
          <Button
            variant={view === "list" ? "default" : "outline"}
            size="icon"
            onClick={() => setView("list")}
          >
            <List className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search assets..."
            className="pl-9"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select value={projectFilter} onValueChange={setProjectFilter}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="All projects" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All projects</SelectItem>
            {projects.map((p: any) => (
              <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        view === "grid" ? (
          <div className="grid gap-4 grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Card key={i}><CardContent className="p-4"><Skeleton className="aspect-square w-full" /><Skeleton className="h-4 w-3/4 mt-2" /></CardContent></Card>
            ))}
          </div>
        ) : (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Card key={i}><CardContent className="p-4 flex gap-4"><Skeleton className="h-16 w-16" /><Skeleton className="h-4 w-48" /></CardContent></Card>
            ))}
          </div>
        )
      ) : assets.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <ImageIcon className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-lg font-medium">No assets yet</p>
            <p className="text-sm text-muted-foreground">Generated images will appear here</p>
          </CardContent>
        </Card>
      ) : view === "grid" ? (
        <div className="grid gap-4 grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
          {assets.map((asset: any) => (
            <Card key={asset.id} className="group overflow-hidden">
              <CardContent className="p-0">
                <div className="aspect-square bg-muted relative overflow-hidden">
                  <img
                    src={`/api/v1/assets/${asset.id}/file`}
                    alt={asset.filename}
                    className="h-full w-full object-cover transition-transform group-hover:scale-105"
                  />
                </div>
                <div className="p-3 space-y-1">
                  <p className="text-sm font-medium truncate">{asset.filename}</p>
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>{formatFileSize(asset.file_size)}</span>
                    <span>{formatDate(asset.created_at)}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {assets.map((asset: any) => (
            <Card key={asset.id}>
              <CardContent className="p-4 flex items-center gap-4">
                <div className="h-16 w-16 rounded bg-muted overflow-hidden shrink-0">
                  <img src={`/api/v1/assets/${asset.id}/file`} alt="" className="h-full w-full object-cover" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{asset.filename}</p>
                  <p className="text-sm text-muted-foreground">{formatDate(asset.created_at)}</p>
                </div>
                <div className="text-sm text-muted-foreground">{formatFileSize(asset.file_size)}</div>
                <Button variant="outline" size="sm"><Download className="h-3 w-3" /></Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
