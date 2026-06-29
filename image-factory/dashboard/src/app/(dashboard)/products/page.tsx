"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Package, Search, ExternalLink, CheckCircle2, XCircle,
  Clock, AlertTriangle, SkipForward, Image, Grid3X3, List,
  ImageIcon, Download, LayoutList, Ban, Loader2,
} from "lucide-react";
import { formatDate, formatFileSize } from "@/lib/utils";
import Link from "next/link";
import { toast } from "@/hooks/use-toast";

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

export default function ProductsPage() {
  const [tab, setTab] = useState<"products" | "assets">("products");

  // Product list state
  const [productSearch, setProductSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  // Asset gallery state
  const [view, setView] = useState<"grid" | "list">("grid");
  const [assetSearch, setAssetSearch] = useState("");
  const [projectFilter, setProjectFilter] = useState("all");
  const [assetPage, setAssetPage] = useState(1);
  const ASSET_PAGE_SIZE = 50;
  const queryClient = useQueryClient();

  const { data: productData, isLoading: productsLoading } = useQuery({
    queryKey: ["content-products", productSearch, statusFilter],
    queryFn: () => api.getContentProducts({ search: productSearch || undefined, status: statusFilter || undefined }),
    refetchInterval: tab === "products" ? 10000 : undefined,
  });

  const { data: stats } = useQuery({
    queryKey: ["content-stats", statusFilter, productSearch],
    queryFn: () => api.getContentStats({ status: statusFilter || undefined, search: productSearch || undefined }),
    refetchInterval: tab === "products" ? 15000 : undefined,
  });

  const { data: projectsData } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.listProjects({ limit: 100 }),
  });

  const { data: assetsData, isLoading: assetsLoading } = useQuery({
    queryKey: ["assets", assetSearch, projectFilter, assetPage],
    queryFn: () =>
      api.listAssets({
        search: assetSearch || undefined,
        project_id: projectFilter !== "all" ? projectFilter : undefined,
        limit: ASSET_PAGE_SIZE,
        offset: (assetPage - 1) * ASSET_PAGE_SIZE,
      }),
    enabled: tab === "assets",
  });

  const banMutation = useMutation({
    mutationFn: (assetId: string) => api.banImageHash(assetId, assetId, ""),
    onSuccess: () => {
      toast({ title: "Image banned", description: "This image hash will be rejected in future scrapes." });
      queryClient.invalidateQueries({ queryKey: ["assets"] });
    },
    onError: (err: any) => {
      toast({ title: "Ban failed", description: err.message, variant: "destructive" });
    },
  });

  const products = productData?.products ?? [];
  const total = productData?.total ?? 0;
  const assets = assetsData?.assets || [];
  const assetTotal = assetsData?.total ?? 0;
  const assetTotalPages = Math.ceil(assetTotal / ASSET_PAGE_SIZE);
  const projects = projectsData?.projects || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Products</h1>
          <p className="text-muted-foreground">Browse products, their images, and AI-generated content</p>
        </div>
        <div className="flex items-center gap-2 rounded-lg border p-1">
          <Button
            variant={tab === "products" ? "default" : "ghost"}
            size="sm"
            onClick={() => setTab("products")}
          >
            <LayoutList className="h-4 w-4 mr-1" />
            Products
          </Button>
          <Button
            variant={tab === "assets" ? "default" : "ghost"}
            size="sm"
            onClick={() => setTab("assets")}
          >
            <ImageIcon className="h-4 w-4 mr-1" />
            Assets
          </Button>
        </div>
      </div>

      {tab === "products" ? (
        <>
          {/* Stats */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            <StatBadge label="Total" value={stats?.total ?? 0} color="bg-primary/10 text-primary" />
            <StatBadge label="Pending" value={(stats?.pending ?? 0) + (stats?.scraping ?? 0)} color="bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300" />
            <StatBadge label="Scraped" value={stats?.scraped ?? 0} color="bg-indigo-100 text-indigo-700 dark:bg-indigo-900 dark:text-indigo-300" />
            <StatBadge label="Completed" value={stats?.completed ?? 0} color="bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300" />
            <StatBadge label="Failed" value={stats?.failed ?? 0} color="bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300" />
          </div>

          {/* Filters */}
          <div className="flex items-center gap-3">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search products..."
                value={productSearch}
                onChange={(e) => setProductSearch(e.target.value)}
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
              {productsLoading ? (
                <div className="p-4 space-y-3">
                  {[1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-16 w-full" />
                  ))}
                </div>
              ) : products.length === 0 ? (
                <div className="p-8 text-center text-sm text-muted-foreground">
                  No products found. Upload a product file to get started.
                </div>
              ) : (
                <div className="divide-y">
                  {products.map((product: any) => {
                    const StatusIcon = statusIcons[product.status] || Clock;
                    return (
                      <Link
                        key={product.id}
                        href={`/products/${product.id}`}
                        className="flex items-center gap-4 px-4 py-3 hover:bg-muted/50 transition-colors"
                      >
                        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 shrink-0">
                          <Package className="h-4 w-4 text-primary" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium truncate">
                            {product.display_title || product.product_name || product.url?.split("/").pop()?.replace(/-/g, " ") || "Unknown Product"}
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
        </>
      ) : (
        <>
          {/* Filters */}
          <div className="flex gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search assets..."
                className="pl-9"
                value={assetSearch}
                onChange={(e) => { setAssetSearch(e.target.value); setAssetPage(1); }}
              />
            </div>
            <Select value={projectFilter} onValueChange={(v) => { setProjectFilter(v); setAssetPage(1); }}>
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

          {assetsLoading ? (
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
            <>
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
                        <button
                          onClick={() => banMutation.mutate(asset.id)}
                          disabled={banMutation.isPending}
                          className="absolute top-1 right-1 h-6 w-6 rounded-full bg-red-600/80 hover:bg-red-600 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                          title="Ban this image (reject hash so it won't be scraped again)"
                        >
                          {banMutation.isPending ? <Loader2 className="h-3 w-3 text-white animate-spin" /> : <Ban className="h-3 w-3 text-white" />}
                        </button>
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
              {assetTotalPages > 1 && (
                <div className="flex items-center justify-between pt-2">
                  <p className="text-sm text-muted-foreground">{assetTotal} total images</p>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" disabled={assetPage <= 1} onClick={() => setAssetPage(assetPage - 1)}>Previous</Button>
                    <span className="text-sm text-muted-foreground">Page {assetPage} of {assetTotalPages}</span>
                    <Button variant="outline" size="sm" disabled={assetPage >= assetTotalPages} onClick={() => setAssetPage(assetPage + 1)}>Next</Button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              <div className="space-y-2">
                {assets.map((asset: any) => (
                  <Card key={asset.id} className="group">
                    <CardContent className="p-4 flex items-center gap-4">
                      <div className="h-16 w-16 rounded bg-muted overflow-hidden shrink-0 relative">
                        <img src={`/api/v1/assets/${asset.id}/file`} alt="" className="h-full w-full object-cover" />
                        <button
                          onClick={() => banMutation.mutate(asset.id)}
                          disabled={banMutation.isPending}
                          className="absolute top-0.5 right-0.5 h-5 w-5 rounded-full bg-red-600/80 hover:bg-red-600 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                          title="Ban this image"
                        >
                          <Ban className="h-2.5 w-2.5 text-white" />
                        </button>
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
              {assetTotalPages > 1 && (
                <div className="flex items-center justify-between pt-2">
                  <p className="text-sm text-muted-foreground">{assetTotal} total images</p>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" disabled={assetPage <= 1} onClick={() => setAssetPage(assetPage - 1)}>Previous</Button>
                    <span className="text-sm text-muted-foreground">Page {assetPage} of {assetTotalPages}</span>
                    <Button variant="outline" size="sm" disabled={assetPage >= assetTotalPages} onClick={() => setAssetPage(assetPage + 1)}>Next</Button>
                  </div>
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
