"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ArrowLeft, Check, Wand2, RotateCcw, CheckCircle2, Loader2, AlertTriangle, Info, Image,
  Lock, Sparkles, ShieldAlert, AlertCircle,
} from "lucide-react";
import Link from "next/link";
import { useNotificationsStore } from "@/lib/store";
import type { ScoreResponse, ScoredImage, ReferenceStatus } from "@/types";

function ScoreBadge({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-medium ${color}`}>
      <span className="opacity-70">{label}:</span>
      <span>{(value * 100).toFixed(0)}</span>
    </span>
  );
}

function ConfidenceBadge({ confidence, compact }: { confidence: number; compact?: boolean }) {
  if (confidence > 90) {
    return (
      <Badge variant="default" className={`bg-emerald-600 hover:bg-emerald-700 ${compact ? "text-[10px] h-4 px-1" : ""}`}>
        <Sparkles className={`${compact ? "h-2.5 w-2.5" : "h-3 w-3"} mr-1`} />
        High Confidence
      </Badge>
    );
  }
  if (confidence >= 60) {
    return (
      <Badge variant="outline" className={`border-amber-400 text-amber-700 bg-amber-50 ${compact ? "text-[10px] h-4 px-1" : ""}`}>
        <AlertCircle className={`${compact ? "h-2.5 w-2.5" : "h-3 w-3"} mr-1`} />
        Needs Review
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className={`border-red-300 text-red-600 bg-red-50 ${compact ? "text-[10px] h-4 px-1" : ""}`}>
      <ShieldAlert className={`${compact ? "h-2.5 w-2.5" : "h-3 w-3"} mr-1`} />
      Low Confidence
    </Badge>
  );
}

function ConfidenceMeter({ confidence }: { confidence: number }) {
  const color = confidence > 90 ? "bg-emerald-500" : confidence >= 60 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs font-medium text-muted-foreground w-20">Confidence</span>
      <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden max-w-[200px]">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${confidence}%` }} />
      </div>
      <span className="text-xs font-semibold tabular-nums w-8 text-right">{confidence.toFixed(0)}%</span>
      <ConfidenceBadge confidence={confidence} compact />
    </div>
  );
}

function GenerationGate({ status }: { status: ReferenceStatus | null }) {
  if (!status) return null;
  const reasons: string[] = [];
  if (status.selected_count < 3) {
    reasons.push(`Select at least 3 reference images (currently ${status.selected_count})`);
  }
  if (!status.approved) {
    reasons.push("Approve the selection to lock it in");
  }

  if (status.can_generate) {
    return (
      <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm px-4 py-3 rounded-lg flex items-center gap-2">
        <CheckCircle2 className="h-4 w-4 shrink-0" />
        <span>References approved and ready. Generation is available.</span>
      </div>
    );
  }

  return (
    <div className="bg-amber-50 border border-amber-200 text-amber-800 text-sm px-4 py-3 rounded-lg flex items-start gap-2">
      <Lock className="h-4 w-4 shrink-0 mt-0.5" />
      <div>
        <p className="font-medium">Generation locked</p>
        <ul className="list-disc list-inside text-xs mt-1 space-y-0.5 text-amber-700">
          {reasons.map((r, i) => <li key={i}>{r}</li>)}
        </ul>
      </div>
    </div>
  );
}

export default function AdaptRefPage() {
  const params = useParams();
  const router = useRouter();
  const productId = params.id as string;

  const [referenceCount, setReferenceCount] = useState(3);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [autoSelectIds, setAutoSelectIds] = useState<string[]>([]);
  const [hasAutoRan, setHasAutoRan] = useState(false);
  const [isApproved, setIsApproved] = useState(false);
  const [isLocked, setIsLocked] = useState(false);
  const [approveMessage, setApproveMessage] = useState("");
  const [lastConfidence, setLastConfidence] = useState<number | null>(null);

  const { data, isLoading, error, refetch } = useQuery<ScoreResponse>({
    queryKey: ["score-references", productId, referenceCount],
    queryFn: () => api.scoreReferences(productId, referenceCount),
    enabled: false,
  });

  const { data: refStatus, refetch: refetchStatus } = useQuery<ReferenceStatus>({
    queryKey: ["reference-status", productId],
    queryFn: () => api.getReferenceStatus(productId),
    enabled: true,
  });

  useEffect(() => {
    if (refStatus) {
      setIsApproved(refStatus.approved);
      setIsLocked(refStatus.locked);
      if (refStatus.selected_count > 0 && !hasAutoRan) {
        setReferenceCount(Math.max(3, refStatus.selected_count));
      }
    }
  }, [refStatus, hasAutoRan]);

  const saveMutation = useMutation({
    mutationFn: async (params: { selected: string[]; approved: boolean }) =>
      api.saveReferenceSelection(productId, params.selected, autoSelectIds, params.approved),
    onSuccess: (_data, variables) => {
      if (variables.approved) {
        setIsApproved(true);
        setIsLocked(true);
        setApproveMessage("Selection approved and locked. Generation is now available.");
        setTimeout(() => setApproveMessage(""), 4000);
        const ns = useNotificationsStore.getState();
        ns.addNotification({
          id: `ref-approved-${Date.now()}`,
          type: "processing_finished",
          title: "Reference Images Approved",
          message: `${variables.selected.length} reference image(s) approved and locked for generation`,
          read: false,
          created_at: new Date().toISOString(),
        });
        refetchStatus();
      } else {
        setApproveMessage("Selection saved");
        setTimeout(() => setApproveMessage(""), 2000);
      }
    },
  });

  const handleAutoSelect = useCallback(() => {
    if (!data) return;
    const sorted = [...data.images].sort((a, b) => b.image_score - a.image_score);
    const topIds = sorted.slice(0, referenceCount).map((img) => img.asset_id);
    if (data.confidence >= 60) {
      setSelectedIds(new Set(topIds));
    } else {
      setSelectedIds(new Set());
    }
    setAutoSelectIds(topIds);
    setHasAutoRan(true);
    setLastConfidence(data.confidence);
  }, [data, referenceCount]);

  const handleReset = useCallback(() => {
    setSelectedIds(new Set());
    setHasAutoRan(false);
  }, []);

  const toggleImage = useCallback((assetId: string) => {
    if (isLocked) return;
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(assetId)) {
        next.delete(assetId);
      } else {
        next.add(assetId);
      }
      return next;
    });
  }, [isLocked]);

  const handleApprove = useCallback(() => {
    if (selectedIds.size < 3) return;
    saveMutation.mutate({ selected: Array.from(selectedIds), approved: true });
  }, [selectedIds, saveMutation]);

  const handleSaveDraft = useCallback(() => {
    saveMutation.mutate({ selected: Array.from(selectedIds), approved: false });
  }, [selectedIds, saveMutation]);

  const handleRun = useCallback(() => {
    refetch().then((res) => {
      if (res.data) {
        handleAutoSelect();
      }
    });
  }, [refetch, handleAutoSelect]);

  const sortedImages = useMemo(() => {
    if (!data) return [];
    return [...data.images].sort((a, b) => b.image_score - a.image_score);
  }, [data]);

  const canApprove = selectedIds.size >= 3 && !isApproved && !saveMutation.isPending;
  const canGenerateNow = refStatus?.can_generate === true;

  if (error) {
    return (
      <div className="flex flex-col items-center gap-4 py-12">
        <AlertTriangle className="h-12 w-12 text-muted-foreground" />
        <p className="text-muted-foreground">Failed to load product</p>
        <Link href="/products">
          <Button variant="outline" size="sm">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back to Products
          </Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <Link href="/products">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Adaptive Reference Selection</h1>
            <p className="text-sm text-muted-foreground">
              {data?.product_name || "Loading..."}
            </p>
          </div>
        </div>

        {isApproved && (
          <Badge variant="default" className="bg-emerald-600">
            <CheckCircle2 className="h-3 w-3 mr-1" />
            Approved
          </Badge>
        )}
      </div>

      <GenerationGate status={refStatus || null} />

      {!isLocked && !hasAutoRan && (
        <Card className="border-primary/30 bg-primary/5">
          <CardContent className="p-6 flex items-center gap-4">
            <Info className="h-8 w-8 text-primary shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-medium">Select reference images for image-to-image generation</p>
              <p className="text-xs text-muted-foreground mt-1">
                Choose 3&ndash;5 images as visual references. Use <strong>Auto Select</strong> for AI-suggested picks or manually select images below.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {isLocked && (
        <Card className="border-emerald-200 bg-emerald-50/50">
          <CardContent className="p-4 flex items-center gap-3">
            <Lock className="h-5 w-5 text-emerald-600 shrink-0" />
            <p className="text-sm text-emerald-800">
              Reference selection is approved and locked. {canGenerateNow ? "You can now proceed to generation." : "Adjust the selection below and approve when ready."}
            </p>
          </CardContent>
        </Card>
      )}

      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <label className="text-sm font-medium">Reference Count:</label>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setReferenceCount((c) => Math.max(3, c - 1))}
              disabled={referenceCount <= 3 || isLocked}
            >
              &minus;
            </Button>
            <span className="w-8 text-center text-sm font-semibold tabular-nums">{referenceCount}</span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setReferenceCount((c) => Math.min(5, c + 1))}
              disabled={referenceCount >= 5 || isLocked}
            >
              +
            </Button>
          </div>
          {data && hasAutoRan && lastConfidence !== null && (
            <ConfidenceMeter confidence={lastConfidence} />
          )}
        </div>

        <div className="flex items-center gap-2">
          {!isLocked && (
            <>
              <Button variant="outline" size="sm" onClick={handleReset} disabled={!hasAutoRan && selectedIds.size === 0}>
                <RotateCcw className="h-4 w-4 mr-1.5" />
                Reset
              </Button>
              <Button variant="default" size="sm" onClick={handleRun} disabled={isLoading}>
                {isLoading ? (
                  <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                ) : (
                  <Wand2 className="h-4 w-4 mr-1.5" />
                )}
                {isLoading ? "Scoring..." : "Auto Select"}
              </Button>
            </>
          )}
          {!isLocked && isApproved && (
            <Button variant="outline" size="sm" onClick={handleSaveDraft} disabled={saveMutation.isPending}>
              {saveMutation.isPending ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <CheckCircle2 className="h-4 w-4 mr-1.5" />}
              Save
            </Button>
          )}
          {isLocked ? (
            <Button
              variant="default"
              size="sm"
              onClick={() => router.push(`/products/${productId}`)}
            >
              <Sparkles className="h-4 w-4 mr-1.5" />
              {canGenerateNow ? "Go to Generation" : "View Product"}
            </Button>
          ) : (
            <Button
              variant="default"
              size="sm"
              onClick={isApproved ? handleApprove : handleApprove}
              disabled={!canApprove}
            >
              {saveMutation.isPending ? (
                <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
              ) : (
                <CheckCircle2 className="h-4 w-4 mr-1.5" />
              )}
              {saveMutation.isPending ? "Saving..." : `Approve & Lock (${selectedIds.size})`}
            </Button>
          )}
        </div>
      </div>

      {approveMessage && (
        <div className={`text-sm px-4 py-2 rounded-lg flex items-center gap-2 ${
          isApproved
            ? "bg-emerald-50 border border-emerald-200 text-emerald-800"
            : "bg-blue-50 border border-blue-200 text-blue-800"
        }`}>
          <CheckCircle2 className="h-4 w-4" />
          {approveMessage}
        </div>
      )}

      {hasAutoRan && data && lastConfidence !== null && lastConfidence < 60 && !isLocked && (
        <Card className="border-red-200 bg-red-50/50">
          <CardContent className="p-4 flex items-center gap-3">
            <AlertTriangle className="h-5 w-5 text-red-500 shrink-0" />
            <p className="text-sm text-red-700">
              Low confidence in auto-selection. No images were pre-selected. Please review the scores below and manually select {referenceCount} reference images.
            </p>
          </CardContent>
        </Card>
      )}

      {hasAutoRan && data && lastConfidence !== null && lastConfidence >= 60 && lastConfidence < 90 && !isLocked && (
        <Card className="border-amber-200 bg-amber-50/50">
          <CardContent className="p-4 flex items-center gap-3">
            <AlertCircle className="h-5 w-5 text-amber-500 shrink-0" />
            <p className="text-sm text-amber-700">
              Moderate confidence. Images were auto-selected but should be reviewed. Adjust the selection if needed before approving.
            </p>
          </CardContent>
        </Card>
      )}

      {isLoading && !data && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-3 space-y-2">
                <Skeleton className="aspect-square w-full rounded-lg" />
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-3 w-16" />
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {hasAutoRan && data && (
        <>
          <div className="text-xs text-muted-foreground">
            {sortedImages.length} image{sortedImages.length !== 1 ? "s" : ""} scored &middot;
            Weights: center = {(data.weights.center * 100).toFixed(0)}%, chinese = {(data.weights.chinese * 100).toFixed(0)}%,
            quality = {(data.weights.quality * 100).toFixed(0)}%, detail = {(data.weights.detail * 100).toFixed(0)}%
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
            {sortedImages.map((img) => {
              const isSelected = selectedIds.has(img.asset_id);
              const isAutoSuggested = autoSelectIds.includes(img.asset_id);
              const isLowConf = lastConfidence !== null && lastConfidence < 60;
              return (
                <Card
                  key={img.asset_id}
                  className={`transition-all ${
                    isLocked ? "cursor-default opacity-80" : "cursor-pointer"
                  } ${
                    isSelected
                      ? "ring-2 ring-primary border-primary"
                      : "hover:border-muted-foreground/30"
                  } ${isAutoSuggested && isLowConf && !isSelected ? "ring-1 ring-red-200 border-red-200" : ""}`}
                  onClick={() => toggleImage(img.asset_id)}
                >
                  <CardContent className="p-3 space-y-2">
                    <div className="relative aspect-square rounded-lg overflow-hidden bg-muted border">
                      <img
                        src={`/api/v1/assets/${img.asset_id}/file`}
                        alt={img.filename}
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          (e.target as HTMLImageElement).src = "/placeholder.svg";
                        }}
                      />
                      {isSelected && (
                        <div className="absolute inset-0 bg-primary/20 flex items-center justify-center">
                          <div className="h-8 w-8 rounded-full bg-primary flex items-center justify-center">
                            <Check className="h-5 w-5 text-white" />
                          </div>
                        </div>
                      )}
                      {isAutoSuggested && !isSelected && (
                        <div className="absolute top-1 right-1">
                          <Badge variant={isLowConf ? "destructive" : "secondary"} className="text-[10px] h-4 px-1">
                            {isLowConf ? "suggested" : "suggested"}
                          </Badge>
                        </div>
                      )}
                      {isLocked && isSelected && (
                        <div className="absolute top-1 left-1">
                          <Badge variant="default" className="bg-emerald-600 text-[10px] h-4 px-1">
                            <CheckCircle2 className="h-2.5 w-2.5 mr-0.5" />
                            locked
                          </Badge>
                        </div>
                      )}
                    </div>

                    <div className="space-y-0.5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold">
                          Score: {(img.image_score * 100).toFixed(0)}
                        </span>
                        {isAutoSuggested && isSelected && (
                          <Badge variant="default" className="text-[10px] h-4 px-1">auto</Badge>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-x-2 gap-y-0.5">
                        <ScoreBadge label="C" value={img.scores.center} color="text-blue-600" />
                        <ScoreBadge label="CN" value={img.scores.chinese} color="text-red-600" />
                        <ScoreBadge label="Q" value={img.scores.quality} color="text-emerald-600" />
                        <ScoreBadge label="D" value={img.scores.detail} color="text-purple-600" />
                      </div>
                      <p className="text-[10px] text-muted-foreground truncate" title={img.filename}>
                        {img.filename}
                      </p>
                      {img.width > 0 && img.height > 0 && (
                        <p className="text-[10px] text-muted-foreground/60">
                          {img.width}&times;{img.height}
                        </p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </>
      )}

      {!hasAutoRan && !data && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <Image className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-lg font-medium">No images scored yet</p>
            <p className="text-sm text-muted-foreground mb-4">
              Click <strong>Auto Select</strong> to score and rank scraped images
            </p>
            <Button onClick={handleRun} disabled={isLocked}>
              <Wand2 className="h-4 w-4 mr-2" />
              Auto Select
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
