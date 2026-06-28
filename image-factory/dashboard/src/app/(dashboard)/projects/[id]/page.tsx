"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowLeft, ExternalLink, Image, FileText, Clock, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { formatDate, formatDateTime, statusLabel, statusColor } from "@/lib/utils";

export default function ProjectDetailPage() {
  const params = useParams();
  const projectId = params.id as string;

  const { data: project, isLoading } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(projectId),
  });

  const { data: productsData } = useQuery({
    queryKey: ["project-products", projectId],
    queryFn: () => api.getProjectProducts(projectId, { limit: 200 }),
  });

  const queryClient = useQueryClient();

  const retryMutation = useMutation({
    mutationFn: (productId: string) => api.retryContentProduct(productId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-products", projectId] });
    },
  });

  if (isLoading) return <ProjectSkeleton />;
  if (!project) return <div>Project not found</div>;

  const products = productsData?.products || [];
  const completed = products.filter((p: any) => p.status === "completed").length;
  const failed = products.filter((p: any) => p.status === "failed").length;
  const processing = products.filter((p: any) => p.status === "generating_images" || p.status === "extracting" || p.status === "translating" || p.status === "repositioning" || p.status === "delivering").length;
  const waiting = products.filter((p: any) => p.status === "waiting").length;
  const progress = products.length > 0 ? ((completed + failed) / products.length) * 100 : 0;

  const statusIcon = (s: string) => {
    if (s === "completed") return <CheckCircle2 className="h-4 w-4 text-success" />;
    if (s === "failed") return <XCircle className="h-4 w-4 text-destructive" />;
    if (s === "waiting") return <Clock className="h-4 w-4 text-muted-foreground" />;
    return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/projects">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight">{project.name}</h1>
            <Badge variant={project.status === "completed" ? "success" : project.status === "failed" ? "destructive" : "secondary"}>
              {statusLabel(project.status)}
            </Badge>
          </div>
          {project.description && <p className="text-muted-foreground">{project.description}</p>}
        </div>
      </div>

      {/* Progress Summary */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Total</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold">{products.length}</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Completed</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold text-success">{completed}</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Failed</CardTitle></CardHeader>
          <CardContent><div className="text-2xl font-bold text-destructive">{failed}</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Progress</CardTitle></CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{Math.round(progress)}%</div>
            <Progress value={progress} className="mt-2" />
          </CardContent>
        </Card>
      </div>

      {/* Products List */}
      <Tabs defaultValue="all">
        <TabsList>
          <TabsTrigger value="all">All ({products.length})</TabsTrigger>
          <TabsTrigger value="completed">Completed ({completed})</TabsTrigger>
          <TabsTrigger value="processing">Processing ({processing})</TabsTrigger>
          <TabsTrigger value="failed">Failed ({failed})</TabsTrigger>
        </TabsList>

        <TabsContent value="all" className="mt-4">
          <div className="space-y-2">
            {products.length === 0 ? (
              <Card><CardContent className="py-12 text-center text-muted-foreground">No products yet. Upload a spreadsheet to get started.</CardContent></Card>
            ) : (
              products.map((product: any) => (
                <Card key={product.id}>
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between gap-4">
                      {statusIcon(product.status)}
                      <div className="min-w-0 flex-1">
                        <p className="font-medium truncate">{product.generated_title || product.url || "No URL"}</p>
                        <div className="flex items-center gap-3 mt-1">
                          <Badge variant="outline" className="text-xs">
                            {statusLabel(product.status)}
                          </Badge>
                          <span className="text-xs text-muted-foreground">{formatDateTime(product.created_at)}</span>
                          {product.scraped_image_count > 0 && (
                            <span className="text-xs text-muted-foreground">{product.scraped_image_count} images</span>
                          )}
                        </div>
                      </div>
                       <Link href={`/products/${product.id}`}>
                        <Button variant="outline" size="sm">View</Button>
                      </Link>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </TabsContent>

        <TabsContent value="completed">
          <div className="space-y-2">
            {products.filter((p: any) => p.status === "completed").map((product: any) => (
              <Card key={product.id}>
                <CardContent className="p-4">
                  <div className="flex items-start gap-3">
                    <CheckCircle2 className="h-5 w-5 text-success mt-0.5" />
                    <div>
                      <p className="font-medium">{product.generated_title || product.url}</p>
                      <p className="text-sm text-muted-foreground line-clamp-2">{product.generated_description}</p>
                      {product.images?.length > 0 && (
                        <div className="flex gap-2 mt-2">
                          {product.images.map((img: any) => (
                            <img key={img.id} src={`/api/v1/assets/${img.id}/file`} alt="" className="h-16 w-16 rounded object-cover border" />
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="processing">
          <div className="space-y-2">
            {products.filter((p: any) => p.status !== "completed" && p.status !== "failed" && p.status !== "waiting").map((product: any) => (
              <Card key={product.id}>
                <CardContent className="p-4 flex items-center gap-3">
                  <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />
                  <span className="font-medium truncate">{product.url}</span>
                  <Badge variant="outline">{statusLabel(product.status)}</Badge>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="failed">
          <div className="space-y-2">
            {products.filter((p: any) => p.status === "failed").map((product: any) => (
              <Card key={product.id}>
                <CardContent className="p-4 flex items-center gap-3">
                  <XCircle className="h-5 w-5 text-destructive shrink-0" />
                  <div className="min-w-0">
                    <p className="font-medium truncate">{product.url}</p>
                    <p className="text-sm text-muted-foreground">Processing failed</p>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => retryMutation.mutate(product.id)} disabled={retryMutation.isPending}>Retry</Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function ProjectSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-64" />
      <div className="grid gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}><CardContent className="p-6"><Skeleton className="h-8 w-16" /></CardContent></Card>
        ))}
      </div>
    </div>
  );
}
