"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
  ArrowLeft, ExternalLink, Image, CheckCircle2, XCircle, Clock, AlertTriangle, RefreshCw,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

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

function ImageThumb({ src, label }: { src: string; label: string }) {
  const [error, setError] = useState(false);
  if (error) {
    return (
      <div className="aspect-square rounded-lg bg-muted flex items-center justify-center text-xs text-muted-foreground">
        Failed to load
      </div>
    );
  }
  return (
    <div className="space-y-1.5">
      <div className="aspect-square rounded-lg overflow-hidden bg-muted border">
        <img
          src={src}
          alt={label}
          className="w-full h-full object-cover"
          onError={() => setError(true)}
        />
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
                  src={`/api/v1/assets/${img.id}/download`}
                  label={img.filename}
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
            <p className="text-sm text-muted-foreground">No AI generated images yet. Run generation first.</p>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
              {generated_images.map((img: any) => (
                <ImageThumb
                  key={img.id}
                  src={`/api/v1/assets/${img.id}/download`}
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
