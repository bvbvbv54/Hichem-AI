"use client";

import { useQuery, useMutation } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import {
  ArrowLeft, ExternalLink, Image, CheckCircle2, XCircle, Clock, AlertTriangle, RefreshCw, Calendar, Sparkles, Loader2, DollarSign, Ban,
} from "lucide-react";
import Link from "next/link";
import { useState, useCallback } from "react";
import { toast } from "@/hooks/use-toast";

const statusColors: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  scraping: "bg-blue-100 text-blue-800",
  scraped: "bg-indigo-100 text-indigo-800",
  generating: "bg-purple-100 text-purple-800",
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-800",
  skipped: "bg-gray-100 text-gray-800",
  error: "bg-red-100 text-red-800",
};

function ImageThumb({ src, r2Url, label, imageId, onBan }: { src: string; r2Url?: string; label: string; imageId?: string; onBan?: (imageId: string) => void }) {
  const [error, setError] = useState(false);
  const imgSrc = r2Url || src;
  if (error) {
    return (
      <div className="aspect-square rounded-lg bg-muted flex items-center justify-center text-xs text-muted-foreground">
        Failed to load
      </div>
    );
  }
  return (
    <div className="space-y-1.5 group relative">
      <div className="aspect-square rounded-lg overflow-hidden bg-muted border relative">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={imgSrc}
          alt={label}
          className="w-full h-full object-cover"
          onError={() => setError(true)}
        />
        {onBan && imageId && (
          <button
            onClick={() => onBan(imageId)}
            className="absolute top-1 right-1 h-6 w-6 rounded-full bg-red-600/80 hover:bg-red-600 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
            title="Ban this image (reject hash so it won't be scraped again)"
          >
            <Ban className="h-3 w-3 text-white" />
          </button>
        )}
      </div>
      <p className="text-xs text-muted-foreground truncate">{label}</p>
    </div>
  );
}

export default function ProductDetailPage() {
  const params = useParams();
  const productId = params.id as string;

  const { data, isLoading } = useQuery({
    queryKey: ["product-detail", productId],
    queryFn: () => api.getProductDetail(productId),
    refetchInterval: 10000,
  });

  const [genNumImages, setGenNumImages] = useState(1);
  const [genModel, setGenModel] = useState("");

  const { data: costData, isLoading: costLoading } = useQuery({
    queryKey: ["gen-cost-estimate", genModel, genNumImages],
    queryFn: () => api.getCostEstimate({
      products: 1,
      images_per_product: genNumImages,
      model_id: genModel || undefined,
      reference_count: 3,
      resolution: "1024",
    }),
    enabled: !!genModel,
    staleTime: 10000,
  });

  const { data: pricingMeta } = useQuery({
    queryKey: ["model-pricing-meta", genModel],
    queryFn: () => api.getModelPricing({ include_hidden: true }),
    enabled: !!genModel,
    staleTime: 60000,
  });

  const { data: img2imgSettings } = useQuery({
    queryKey: ["img2img-settings"],
    queryFn: () => api.getImg2imgSettings(),
    staleTime: 60000,
  });
  const availableModels = (img2imgSettings?.available_models || []) as Array<{ id: string; name: string; provider: string }>;

  const banMutation = useMutation({
    mutationFn: (params: { assetId: string; hash: string; filename: string }) =>
      api.banImageHash(params.assetId, params.hash, params.filename),
    onSuccess: () => {
      toast({ title: "Image banned", description: "This image hash will be rejected in future scrapes." });
    },
    onError: (err: any) => {
      toast({ title: "Ban failed", description: err.message, variant: "destructive" });
    },
  });

  const handleBanImage = useCallback((assetId: string) => {
    if (banMutation.isPending) return;
    banMutation.mutate({ assetId, hash: assetId, filename: "" });
  }, [banMutation]);

  const generateMutation = useMutation({
    mutationFn: (params: { batch_id: string; num_images: number; model_name: string }) =>
      api.submitGeneration({
        batch_id: params.batch_id,
        num_images_per_product: params.num_images,
        image_descriptions: [],
        prompt_template: "",
        model_name: params.model_name,
      }),
    onSuccess: () => {
      toast({ title: "Generation queued", description: "AI image generation has been started." });
    },
    onError: (err: any) => {
      toast({ title: "Generation failed", description: err.message, variant: "destructive" });
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex flex-col items-center gap-4 py-12">
        <AlertTriangle className="h-12 w-12 text-muted-foreground" />
        <p className="text-muted-foreground">Product not found</p>
        <Link href="/products">
          <Button variant="outline" size="sm">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Products
          </Button>
        </Link>
      </div>
    );
  }

  const { product, scraped_images, generated_images, jobs } = data;
  const createdDate = product.created_at
    ? new Date(product.created_at).toLocaleDateString("en-US", {
        year: "numeric", month: "long", day: "numeric",
      })
    : null;
  const updatedDate = product.updated_at
    ? new Date(product.updated_at).toLocaleDateString("en-US", {
        year: "numeric", month: "long", day: "numeric",
      })
    : null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <Link href="/products">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              {product.product_name || "Unknown Product"}
            </h1>
            <a href={product.url} target="_blank" rel="noopener noreferrer"
              className="text-sm text-muted-foreground hover:text-primary flex items-center gap-1">
              {product.url?.substring(0, 80)}...
              <ExternalLink className="h-3 w-3" />
            </a>
            {/* Real persisted date */}
            <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
              {createdDate && (
                <span className="flex items-center gap-1">
                  <Calendar className="h-3 w-3" />
                  Created: {createdDate}
                </span>
              )}
              {updatedDate && updatedDate !== createdDate && (
                <span className="flex items-center gap-1">
                  <RefreshCw className="h-3 w-3" />
                  Updated: {updatedDate}
                </span>
              )}
            </div>
          </div>
        </div>
        <Badge variant="outline" className={statusColors[product.status] || ""}>
          {product.status}
        </Badge>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Card><CardContent className="p-4">
          <div className="text-2xl font-bold text-indigo-600">{scraped_images?.length || 0}</div>
          <div className="text-xs text-muted-foreground">Scraped Images</div>
        </CardContent></Card>
        <Card><CardContent className="p-4">
          <div className="text-2xl font-bold text-primary">{generated_images?.length || 0}</div>
          <div className="text-xs text-muted-foreground">AI Generated Images</div>
        </CardContent></Card>
        <Card><CardContent className="p-4">
          <div className="text-2xl font-bold text-emerald-600">{(jobs || []).filter((j: any) => j.status === "completed").length}</div>
          <div className="text-xs text-muted-foreground">Successful Jobs</div>
        </CardContent></Card>
        <Card><CardContent className="p-4">
          <div className="text-2xl font-bold text-red-600">{(jobs || []).filter((j: any) => j.status === "failed").length}</div>
          <div className="text-xs text-muted-foreground">Failed Jobs</div>
        </CardContent></Card>
      </div>

      {/* Scraped Images */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Image className="h-4 w-4 text-indigo-500" />
            Scraped Images ({(scraped_images || []).length})
            {(scraped_images || []).length > 0 && (scraped_images || []).length <= 2 && (
              <Badge variant="outline" className="text-amber-600 border-amber-300 bg-amber-50 text-xs ml-2">
                <AlertTriangle className="h-3 w-3 mr-1" />
                Low image count — scrape may be partial
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!scraped_images || scraped_images.length === 0 ? (
            <p className="text-sm text-muted-foreground">No scraped images available.</p>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
              {scraped_images.map((img: any) => (
                <ImageThumb
                  key={img.id}
                  src={`/api/v1/assets/${img.id}/file`}
                  r2Url={img.r2_url}
                  label={img.filename}
                  imageId={img.id}
                  onBan={(id) => handleBanImage(id)}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* AI Generated Images */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Image className="h-4 w-4 text-primary" />
            AI Generated Images ({(generated_images || []).length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!generated_images || generated_images.length === 0 ? (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">No AI generated images yet. Run generation first.</p>
              {data?.reference_status?.can_generate && (
                <div className="rounded-lg border p-4 space-y-3 bg-muted/30">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <Sparkles className="h-4 w-4 text-primary" />
                    Generate AI Images
                  </div>
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
                            <SelectItem key={m.id} value={m.id} className="text-sm">
                              {m.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex items-end">
                      <Button
                        size="sm"
                        onClick={() => generateMutation.mutate({
                          batch_id: data.product.batch_id,
                          num_images: genNumImages,
                          model_name: genModel,
                        })}
                        disabled={generateMutation.isPending}
                        className="w-full"
                      >
                        {generateMutation.isPending ? (
                          <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> Starting...</>
                        ) : (
                          <><Sparkles className="h-4 w-4 mr-1" /> Generate</>
                        )}
                      </Button>
                    </div>
                  </div>

                  {/* Cost Estimate */}
                  {genModel && (
                    <div className="mt-2">
                      {costLoading ? (
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          Calculating cost...
                        </div>
                      ) : costData?.available && costData.cost_breakdown ? (
                        <div className="rounded-lg border border-emerald-500/20 bg-emerald-50/50 dark:bg-emerald-950/10 p-3 space-y-1.5">
                          <div className="flex items-center gap-2 text-xs font-medium text-emerald-700 dark:text-emerald-400">
                            <DollarSign className="h-3.5 w-3.5" />
                            Estimated Cost
                          </div>
                          <div className="text-[11px] text-muted-foreground space-y-0.5">
                            {costData.cost_breakdown.lines?.map((line: any, i: number) => (
                              <div key={i} className="flex justify-between">
                                <span>{line.label}</span>
                                <span className="font-mono">${(line.cost_cents / 100).toFixed(4)}</span>
                              </div>
                            ))}
                            <div className="flex justify-between pt-1 border-t border-border/40 mt-1">
                              <span>Subtotal</span>
                              <span className="font-mono">${(costData.cost_breakdown.subtotal_cents / 100).toFixed(4)}</span>
                            </div>
                            <div className="flex justify-between">
                              <span>Safety buffer ({costData.cost_breakdown.safety_buffer_pct}%)</span>
                              <span className="font-mono">+${(costData.cost_breakdown.safety_buffer_cents / 100).toFixed(4)}</span>
                            </div>
                            <div className="flex justify-between pt-1 border-t border-border/40 mt-1 text-xs font-semibold text-emerald-700 dark:text-emerald-400">
                              <span>Total estimate</span>
                              <span className="font-mono">~${(costData.cost_breakdown.total_cents / 100).toFixed(3)}</span>
                            </div>
                          </div>
                          <div className="text-[10px] text-muted-foreground">
                            Model: {costData.display_name || genModel}
                            {(() => {
                              const meta = pricingMeta?.models?.find((m: any) => m.model_id === genModel);
                              if (!meta?.deprecated) return null;
                              return (
                                <span className="text-amber-500 ml-2 flex items-center gap-1">
                                  <AlertTriangle className="h-3 w-3" /> Deprecated — {meta.sunset_date ? `removed after ${meta.sunset_date}` : ""}
                                </span>
                              );
                            })()}
                            {costData.deficit_cents > 0 && (
                              <span className="text-rose-500 ml-2">
                                Insufficient credits
                              </span>
                            )}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
              {generated_images.map((img: any) => (
                <ImageThumb
                  key={img.id}
                  src={`/api/v1/assets/${img.id}/download`}
                  r2Url={img.r2_url}
                  label={img.filename}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Job History */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Processing History</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {!jobs || jobs.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">No processing history.</p>
          ) : (
            <div className="divide-y">
              {jobs.map((job: any) => (
                <div key={job.id} className="flex items-center justify-between px-4 py-3">
                  <div className="flex items-center gap-3">
                    {job.status === "completed" ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                    ) : job.status === "failed" ? (
                      <XCircle className="h-4 w-4 text-red-500" />
                    ) : (
                      <Clock className="h-4 w-4 text-yellow-500" />
                    )}
                    <div>
                      <div className="text-sm font-medium">{job.type}</div>
                      <div className="text-xs text-muted-foreground">
                        Created: {job.created_at ? new Date(job.created_at).toLocaleString() : "N/A"}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {job.error_message && (
                      <span className="text-xs text-red-500 max-w-[200px] truncate" title={job.error_message}>
                        {job.error_message}
                      </span>
                    )}
                    <Badge variant="outline" className={statusColors[job.status] || ""}>
                      {job.status}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
