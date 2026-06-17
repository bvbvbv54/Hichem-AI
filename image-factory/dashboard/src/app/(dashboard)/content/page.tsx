"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Package, Search, ExternalLink, CheckCircle2, XCircle,
  Clock, AlertTriangle, SkipForward, Image,
} from "lucide-react";
import Link from "next/link";

const statusColors: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  scraping: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  scraped: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200",
  generating: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
  completed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200",
  failed: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  skipped: "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200",
  error: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

const statusIcons: Record<string, any> = {
  pending: Clock,
  scraping: Package,
  scraped: Image,
  generating: Image,
  completed: CheckCircle2,
  failed: XCircle,
  skipped: SkipForward,
  error: AlertTriangle,
};

export default function ContentPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["content-products", search, statusFilter],
    queryFn: () => api.getContentProducts({ search: search || undefined, status: statusFilter || undefined }),
    refetchInterval: 10000,
  });

  const { data: stats } = useQuery({
    queryKey: ["content-stats"],
    queryFn: () => api.getContentStats(),
    refetchInterval: 15000,
  });

  const products = data?.products ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Content</h1>
          <p className="text-sm text-muted-foreground">Tracked products with scraped and AI-generated images</p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatBadge label="Total" value={stats?.total ?? 0} color="bg-primary/10 text-primary" />
        <StatBadge label="Scraped" value={stats?.scraped ?? 0} color="bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300" />
        <StatBadge label="Completed (AI)" value={stats?.completed ?? 0} color="bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300" />
        <StatBadge label="Failed" value={stats?.failed ?? 0} color="bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300" />
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search products..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <select
          className="h-10 rounded-md border border-input bg-background px-3 py-2 text-sm"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All Status</option>
          <option value="pending">Pending</option>
          <option value="scraping">Scraping</option>
          <option value="scraped">Scraped</option>
          <option value="generating">Generating</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="skipped">Skipped</option>
        </select>
      </div>

      {/* Products Table */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">
            Products ({total})
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-4 space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : products.length === 0 ? (
            <div className="p-8 text-center text-sm text-muted-foreground">
              No products found. Upload a product file in Projects to get started.
            </div>
          ) : (
            <div className="divide-y">
              {products.map((product: any) => {
                const StatusIcon = statusIcons[product.status] || Clock;
                return (
                  <Link
                    key={product.id}
                    href={`/content/${product.id}`}
                    className="flex items-center gap-4 px-4 py-3 hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 shrink-0">
                      <Package className="h-4 w-4 text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate">
                        {product.product_name || product.url.split("/").pop()?.replace(/-/g, " ") || "Unknown Product"}
                      </div>
                      <div className="text-xs text-muted-foreground truncate">
                        {product.url}
                      </div>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span title="Scraped images">
                        <Image className="h-3 w-3 inline mr-1" />
                        {product.scraped_image_count}
                      </span>
                      <span title="Generated images">
                        <Image className="h-3 w-3 inline mr-1 text-primary" />
                        {product.generated_image_count}
                      </span>
                    </div>
                    <Badge variant="outline" className={statusColors[product.status] || ""}>
                      <StatusIcon className="h-3 w-3 mr-1 inline" />
                      {product.status}
                    </Badge>
                    <ExternalLink className="h-4 w-4 text-muted-foreground shrink-0" />
                  </Link>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatBadge({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className={`text-2xl font-bold ${color.split(" ")[1]}`}>{value}</div>
        <div className="text-xs text-muted-foreground">{label}</div>
      </CardContent>
    </Card>
  );
}
