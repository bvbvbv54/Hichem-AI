"use client";

import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowLeft, ExternalLink, Image, Clock, CheckCircle2, XCircle, Loader2, Download, X, ChevronRight, ChevronLeft, Sparkles } from "lucide-react";
import { formatDateTime, statusLabel } from "@/lib/utils";
import { toast } from "@/hooks/use-toast";

function Lightbox({ images, index, onClose }: { images: { url: string; alt?: string }[]; index: number; onClose: () => void }) {
  const [idx, setIdx] = useState(index);
  const current = images[idx];
  if (!current) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90" onClick={onClose}>
      <button className="absolute top-4 right-4 text-white p-2 hover:bg-white/10 rounded" onClick={onClose}>
        <X className="h-6 w-6" />
      </button>
      {images.length > 1 && (
        <>
          <button className="absolute left-4 text-white p-2 hover:bg-white/10 rounded" onClick={(e) => { e.stopPropagation(); setIdx((idx - 1 + images.length) % images.length); }}>
            <ChevronLeft className="h-8 w-8" />
          </button>
          <button className="absolute right-16 text-white p-2 hover:bg-white/10 rounded" onClick={(e) => { e.stopPropagation(); setIdx((idx + 1) % images.length); }}>
            <ChevronRight className="h-8 w-8" />
          </button>
        </>
      )}
      <img
        src={current.url}
        alt={current.alt || ""}
        className="max-h-[90vh] max-w-[90vw] object-contain"
        onClick={(e) => e.stopPropagation()}
      />
      <div className="absolute bottom-4 text-white/60 text-sm">{idx + 1} / {images.length}</div>
    </div>
  );
}

function ProductReviewCard({ product, projectId }: { product: any; projectId: string }) {
  const queryClient = useQueryClient();
  const [showGenerate, setShowGenerate] = useState(false);
  const [genNumImages, setGenNumImages] = useState(3);
  const [genModel, setGenModel] = useState("");

  const { data: img2imgSettings } = useQuery({
    queryKey: ["img2img-settings"],
    queryFn: () => api.getImg2imgSettings(),
    staleTime: 60000,
  });
  const availableModels = (img2imgSettings?.available_models || []) as Array<{ id: string; name: string; provider: string }>;

  const scoreMutation = useMutation({
    mutationFn: () => api.scoreReferences(product.id),
    onSuccess: () => {
      toast({ title: "References scored", description: "Auto-selection complete for this product." });
      queryClient.invalidateQueries({ queryKey: ["project-products", projectId] });
    },
    onError: (err: any) => {
      toast({ title: "Reference scoring failed", description: err.message, variant: "destructive" });
    },
  });

  const generateMutation = useMutation({
    mutationFn: (params: { batch_id: string; num_images: number; model_name: string }) => {
      if (!params.batch_id) throw new Error("Product has no batch ID. Upload via spreadsheet first.");
      return api.submitGeneration({
        batch_id: params.batch_id,
        num_images_per_product: params.num_images,
        image_descriptions: [],
        prompt_template: "",
        model_name: params.model_name,
      });
    },
    onSuccess: () => {
      toast({ title: "Generation queued", description: "AI image generation has been started." });
    },
    onError: (err: any) => {
      toast({ title: "Generation failed", description: err.message, variant: "destructive" });
    },
  });

  return (
    <Card key={product.id}>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <CardTitle className="text-base font-medium leading-snug">{product.display_title}</CardTitle>
            <div className="flex items-center gap-3 mt-1">
              <Badge variant="outline" className="text-xs">{statusLabel(product.status)}</Badge>
              <span className="text-xs text-muted-foreground">{product.images.length} images</span>
            </div>
          </div>
          <Link href={`/products/${product.id}`}>
            <Button variant="outline" size="sm">View</Button>
          </Link>
        </div>
      </CardHeader>
      <CardContent>
        <ImageGrid images={product.images} />
        <div className="mt-4 flex flex-wrap items-center gap-2 border-t pt-4">
          <Button
            variant="outline"
            size="sm"
            onClick={() => scoreMutation.mutate()}
            disabled={scoreMutation.isPending}
          >
            {scoreMutation.isPending ? (
              <><Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> Scoring...</>
            ) : (
              <><Sparkles className="h-3.5 w-3.5 mr-1" /> Auto-Select References</>
            )}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowGenerate(!showGenerate)}
          >
            <Image className="h-3.5 w-3.5 mr-1" />
            Generate
          </Button>
        </div>
        {showGenerate && (
          <div className="mt-3 rounded-lg border p-3 bg-muted/30 space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Images</Label>
                <Input
                  type="number"
                  min={1}
                  max={10}
                  value={genNumImages}
                  onChange={(e) => {
                    const v = parseInt(e.target.value, 10);
                    if (!isNaN(v) && v >= 1 && v <= 10) setGenNumImages(v);
                  }}
                  className="h-8 text-sm"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Model</Label>
                <Select value={genModel} onValueChange={setGenModel}>
                  <SelectTrigger className="h-8 text-sm">
                    <SelectValue placeholder="Default" />
                  </SelectTrigger>
                  <SelectContent>
                    {availableModels.map((m) => (
                      <SelectItem key={m.id} value={m.id} className="text-sm">{m.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-end">
                <Button
                  size="sm"
                  className="w-full"
                  onClick={() => generateMutation.mutate({
                    batch_id: product.batch_id,
                    num_images: genNumImages,
                    model_name: genModel,
                  })}
                  disabled={generateMutation.isPending}
                >
                  {generateMutation.isPending ? (
                    <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> Starting...</>
                  ) : (
                    <><Sparkles className="h-4 w-4 mr-1" /> Generate</>
                  )}
                </Button>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ImageGrid({ images }: { images: any[] }) {
  const [lightboxIdx, setLightboxIdx] = useState<number | null>(null);
  if (!images || images.length === 0) return null;

  const lightboxImages = images.map((img: any) => ({
    url: img.r2_url || `/api/v1/assets/${img.id}/file`,
    alt: img.filename || "",
  }));

  return (
    <>
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-2">
        {images.map((img: any, idx: number) => {
          const src = img.r2_url || `/api/v1/assets/${img.id}/file`;
          return (
            <button key={img.id || idx} className="group relative aspect-square overflow-hidden rounded-md border bg-muted" onClick={() => setLightboxIdx(idx)}>
              <img
                src={src}
                alt={img.filename || ""}
                loading="lazy"
                className="h-full w-full object-cover transition-transform group-hover:scale-105"
                onError={(e) => { (e.target as HTMLImageElement).src = `https://placehold.co/200x200?text=Error`; }}
              />
            </button>
          );
        })}
      </div>
      {lightboxIdx !== null && (
        <Lightbox images={lightboxImages} index={lightboxIdx} onClose={() => setLightboxIdx(null)} />
      )}
    </>
  );
}

export default function ProjectDetailPage() {
  const params = useParams();
  const projectId = params.id as string;

  const { data: project, isLoading } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.getProject(projectId),
    refetchInterval: 3000,
  });

  const { data: productsData } = useQuery({
    queryKey: ["project-products", projectId],
    queryFn: () => api.getProjectProducts(projectId, { limit: 200 }),
    refetchInterval: 3000,
    select: (data: any) => ({
      ...data,
      products: (data.products || []).map((p: any) => ({
        ...p,
        display_title: p.display_title || p.source_title || p.url || "No URL",
        images: p.images || [],
      })),
    }),
  });

  const queryClient = useQueryClient();

  const retryMutation = useMutation({
    mutationFn: (productId: string) => api.retryContentProduct(productId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-products", projectId] });
    },
  });

  const [exporting, setExporting] = useState(false);

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      const blob = await api.exportProjectZip(projectId, project?.name || "project");
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(project?.name || "project").replace(/[^a-zA-Z0-9_-]/g, "_")}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Export failed", err);
    } finally {
      setExporting(false);
    }
  }, [projectId, project?.name]);

  // Pagination for review tab
  const [reviewPage, setReviewPage] = useState(1);
  const REVIEW_PAGE_SIZE = 12;

  if (isLoading) return <ProjectSkeleton />;
  if (!project) return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4">
      <h2 className="text-2xl font-semibold text-muted-foreground">Project not found</h2>
      <p className="text-muted-foreground">This project may have been deleted or the link is invalid.</p>
      <Link href="/projects">
        <Button variant="outline">Back to Projects</Button>
      </Link>
    </div>
  );

  const products = productsData?.products || [];
  const completed = products.filter((p: any) => p.status === "completed" || p.status === "scraped").length;
  const failed = products.filter((p: any) => p.status === "failed" || p.status === "error").length;
  const processing = products.filter((p: any) => p.status === "generating_images" || p.status === "extracting" || p.status === "translating" || p.status === "repositioning" || p.status === "delivering" || p.status === "scraping" || p.status === "generating").length;
  const waiting = products.filter((p: any) => p.status === "waiting" || p.status === "pending" || p.status === "queued").length;
  const progress = products.length > 0 ? ((completed + failed) / products.length) * 100 : 0;

  const statusIcon = (s: string) => {
    if (s === "completed" || s === "scraped") return <CheckCircle2 className="h-4 w-4 text-success" />;
    if (s === "failed" || s === "error") return <XCircle className="h-4 w-4 text-destructive" />;
    if (s === "waiting" || s === "pending" || s === "queued") return <Clock className="h-4 w-4 text-muted-foreground" />;
    return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
  };

  const reviewProducts = products.filter((p: any) => p.status === "scraped" || p.status === "completed");
  const totalReviewPages = Math.ceil(reviewProducts.length / REVIEW_PAGE_SIZE);
  const paginatedReview = reviewProducts.slice(0, reviewPage * REVIEW_PAGE_SIZE);

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
            <Button variant="outline" size="sm" onClick={handleExport} disabled={exporting}>
              {exporting ? (
                <Loader2 className="h-4 w-4 mr-1 animate-spin" />
              ) : (
                <Download className="h-4 w-4 mr-1" />
              )}
              {exporting ? "Exporting..." : "Export ZIP"}
            </Button>
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
          <TabsTrigger value="review">Review &amp; Generate ({reviewProducts.length})</TabsTrigger>
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
                        <p className="font-medium truncate">{product.display_title}</p>
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

        <TabsContent value="review" className="mt-4">
          {reviewProducts.length === 0 ? (
            <Card><CardContent className="py-12 text-center text-muted-foreground">No products ready for review. Products must finish scraping first.</CardContent></Card>
          ) : (
            <div className="space-y-6">
              {paginatedReview.map((product: any) => (
                <ProductReviewCard key={product.id} product={product} projectId={projectId} />
              ))}
              {reviewProducts.length > REVIEW_PAGE_SIZE && paginatedReview.length < reviewProducts.length && (
                <div className="flex justify-center">
                  <Button variant="outline" onClick={() => setReviewPage((p) => p + 1)}>
                    Show More ({reviewProducts.length - paginatedReview.length} remaining)
                  </Button>
                </div>
              )}
            </div>
          )}
        </TabsContent>

        <TabsContent value="processing">
          <div className="space-y-2">
            {products.filter((p: any) => !["scraped", "completed", "failed", "error", "waiting", "pending", "queued"].includes(p.status)).map((product: any) => (
              <Card key={product.id}>
                <CardContent className="p-4 flex items-center gap-3">
                  <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />
                  <span className="font-medium truncate">{product.display_title}</span>
                  <Badge variant="outline">{statusLabel(product.status)}</Badge>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="failed">
          <div className="space-y-2">
            {products.filter((p: any) => p.status === "failed" || p.status === "error").map((product: any) => (
              <Card key={product.id}>
                <CardContent className="p-4 flex items-center gap-3">
                  <XCircle className="h-5 w-5 text-destructive shrink-0" />
                  <div className="min-w-0">
                    <p className="font-medium truncate">{product.display_title}</p>
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
