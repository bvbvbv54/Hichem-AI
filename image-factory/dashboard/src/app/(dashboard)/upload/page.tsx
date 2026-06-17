"use client";

import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useDropzone } from "react-dropzone";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

import { toast } from "@/hooks/use-toast";
import { Upload, FileSpreadsheet, CheckCircle2, Loader2, AlertTriangle, Settings2, Image, Sparkles, ToggleLeft, ExternalLink } from "lucide-react";
import { formatFileSize } from "@/lib/utils";

type UploadState = "idle" | "uploading" | "parsed" | "configuring" | "generating" | "done" | "scraped_only";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [projectId, setProjectId] = useState<string>("");
  const [state, setState] = useState<UploadState>("idle");
  const [uploadResult, setUploadResult] = useState<any>(null);
  const [numImages, setNumImages] = useState<number>(1);
  const [autoImages, setAutoImages] = useState<boolean>(true);
  const [promptTemplate, setPromptTemplate] = useState<string>("");
  const [totalOutput, setTotalOutput] = useState<number>(0);
  const [imageDescriptions, setImageDescriptions] = useState<string[]>([]);
  const [generationResult, setGenerationResult] = useState<any>(null);
  const queryClient = useQueryClient();

  const { data: projectsData } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.listProjects({ limit: 100 }),
  });

  const { data: providerKeys } = useQuery({
    queryKey: ["provider-keys"],
    queryFn: () => api.getProviderKeys(),
  });

  const hasAnyApiKey = providerKeys && Object.values(providerKeys).some((v: any) => v?.configured);

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const f = acceptedFiles[0];
    if (f) {
      const ext = f.name.split(".").pop()?.toLowerCase();
      if (ext !== "xlsx") {
        toast({ title: "Invalid file", description: "Only .xlsx files are supported", variant: "destructive" });
        return;
      }
      setFile(f);
      setState("idle");
      setUploadResult(null);
      setGenerationResult(null);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"] },
    maxFiles: 1,
  });

  const handleUpload = async () => {
    if (!file) return;
    setState("uploading");
    try {
      const result = await api.uploadFile(file, projectId);
      setUploadResult(result);
      if (result.status === "parsed") {
        if (!hasAnyApiKey) {
          setState("scraped_only");
          toast({
            title: "Products scraped successfully",
            description: `Parsed ${result.total_products} products. No API keys configured — products will be scraped only. Configure keys in Settings to enable AI generation.`,
            variant: "default",
          });
        } else {
          setState("parsed");
          const total = autoImages
            ? (result.scraped_images || []).reduce((s: number, p: any) => s + (p.count || 1), 0)
            : (result.total_products || 0) * numImages;
          setTotalOutput(total);
          toast({ title: "File parsed", description: result.message, variant: "success" });
        }
      }
    } catch (err: any) {
      setState("idle");
      toast({ title: "Upload failed", description: err.message, variant: "destructive" });
    }
  };

  const handleGenerate = async () => {
    if (!uploadResult?.batch_id) return;
    setState("generating");
    try {
      const payload: any = {
        batch_id: uploadResult.batch_id,
        project_id: projectId,
        image_descriptions: autoImages ? [] : imageDescriptions,
        prompt_template: autoImages ? "" : promptTemplate,
      };
      if (autoImages) {
        payload.num_images_per_product = -1;
      } else {
        payload.num_images_per_product = numImages;
      }
      const result = await api.submitGeneration(payload);
      setGenerationResult(result);
      setState("done");
      toast({ title: "Generation started", description: result.message, variant: "success" });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
      queryClient.invalidateQueries({ queryKey: ["queue-info"] });
    } catch (err: any) {
      setState("configuring");
      toast({ title: "Failed to start", description: err.message, variant: "destructive" });
    }
  };

  const projects = projectsData?.projects || [];
  const totalProducts = uploadResult?.total_products || 0;
  const scrapedList = uploadResult?.scraped_images || [];

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Upload Products</h1>
        <p className="text-muted-foreground">Upload Excel, configure generation, and let AI create product images</p>
      </div>

      {/* Step Indicator */}
      <div className="flex items-center gap-2 text-sm">
        {["Upload Excel", "Configure", "Generate"].map((step, i) => {
          const stepStates: UploadState[] = ["parsed", "configuring", "generating"];
          const isActive = state === stepStates[i] || (state === "done" && i === 2);
          const isDone = (state === "done" && i <= 2) || (state === "generating" && i <= 1) || (state === "parsed" && i <= 0);
          return (
            <div key={step} className="flex items-center gap-2">
              <div className={`h-6 w-6 rounded-full flex items-center justify-center text-xs font-medium ${isDone ? "bg-primary text-primary-foreground" : isActive ? "bg-primary/20 text-primary" : "bg-muted text-muted-foreground"}`}>
                {isDone ? <CheckCircle2 className="h-4 w-4" /> : i + 1}
              </div>
              <span className={isActive ? "text-foreground font-medium" : "text-muted-foreground"}>{step}</span>
              {i < 2 && <div className="h-px w-8 bg-border" />}
            </div>
          );
        })}
      </div>

      {/* Step 1: Upload */}
      {(state === "idle" || state === "uploading") && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Select Project</CardTitle>
            </CardHeader>
            <CardContent>
              <Select value={projectId} onValueChange={setProjectId}>
                <SelectTrigger>
                  <SelectValue placeholder="Choose a project" />
                </SelectTrigger>
                <SelectContent>
                  {projects.map((p: any) => (
                    <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Upload Excel File</CardTitle>
              <CardDescription>Your spreadsheet must have a column named &quot;URL&quot;, &quot;Link&quot;, or &quot;Product URL&quot; with product links</CardDescription>
            </CardHeader>
            <CardContent>
              <div
                {...getRootProps()}
                className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors ${isDragActive ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-muted-foreground/50"}`}
              >
                <input {...getInputProps()} />
                {file ? (
                  <div className="space-y-2">
                    <FileSpreadsheet className="h-12 w-12 mx-auto text-primary" />
                    <p className="font-medium">{file.name}</p>
                    <p className="text-sm text-muted-foreground">{formatFileSize(file.size)}</p>
                    <Badge variant="secondary">Ready</Badge>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <Upload className="h-12 w-12 mx-auto text-muted-foreground" />
                    <p className="font-medium">Drop your .xlsx file here</p>
                    <p className="text-sm text-muted-foreground">Must contain a column with product URLs</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {file && (
            <Button onClick={handleUpload} disabled={state === "uploading"} className="w-full" size="lg">
              {state === "uploading" ? (
                <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Parsing & Scraping...</>
              ) : (
                <><Upload className="h-4 w-4 mr-2" /> Upload & Parse</>
              )}
            </Button>
          )}
        </>
      )}

      {/* Step 2: Configure */}
      {state === "parsed" && uploadResult && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-success" />
                File Parsed — {totalProducts} products, {uploadResult.total_images_scraped} scraped images
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div className="rounded-lg border p-3 text-center">
                  <p className="text-2xl font-bold">{totalProducts}</p>
                  <p className="text-xs text-muted-foreground">Products</p>
                </div>
                <div className="rounded-lg border p-3 text-center">
                  <p className="text-2xl font-bold">{uploadResult.total_images_scraped}</p>
                  <p className="text-xs text-muted-foreground">Scraped Images</p>
                </div>
                <div className="rounded-lg border p-3 text-center">
                  <p className="text-2xl font-bold">{autoImages ? "Auto" : numImages}</p>
                  <p className="text-xs text-muted-foreground">Per Product</p>
                </div>
                <div className="rounded-lg border p-3 text-center">
                  <p className="text-2xl font-bold">{totalOutput}</p>
                  <p className="text-xs text-muted-foreground">Total Output</p>
                </div>
              </div>
              {scrapedList.length > 0 && (
                <div className="space-y-1 text-sm">
                  <p className="text-xs text-muted-foreground font-medium">Per product:</p>
                  {scrapedList.map((s: any, i: number) => (
                    <div key={i} className="flex justify-between text-xs text-muted-foreground">
                      <span className="truncate max-w-[300px]">{s.url}</span>
                      <span>{s.count} scraped → {autoImages ? s.count : Math.min(numImages, s.count)} AI</span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Settings2 className="h-5 w-5" />
                Generation Settings
              </CardTitle>
              <CardDescription>Choose how many AI images to generate per product</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Images per product */}
              <div className="space-y-3">
                <div className="flex items-center gap-4">
                  <Button
                    type="button"
                    variant={autoImages ? "default" : "outline"}
                    size="sm"
                    onClick={() => {
                      setAutoImages(true);
                      setTotalOutput(scrapedList.reduce((s: number, p: any) => s + (p.count || 1), 0));
                    }}
                    className="gap-1.5"
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    Auto
                  </Button>
                  <Button
                    type="button"
                    variant={!autoImages ? "default" : "outline"}
                    size="sm"
                    onClick={() => {
                      setAutoImages(false);
                      setTotalOutput(totalProducts * numImages);
                    }}
                  >
                    Manual
                  </Button>
                </div>
                {!autoImages && (
                  <div className="flex items-center gap-3">
                    <Label className="text-sm font-medium min-w-fit">Images per product:</Label>
                    <Input
                      type="number"
                      min={1}
                      max={10}
                      value={numImages}
                      onChange={(e) => {
                        const n = Math.min(10, Math.max(1, parseInt(e.target.value) || 1));
                        setNumImages(n);
                        setTotalOutput(totalProducts * n);
                      }}
                      className="w-24"
                    />
                  </div>
                )}
                {autoImages && (
                  <p className="text-xs text-muted-foreground">
                    Each product will get exactly as many AI images as the number of pictures scraped for it
                  </p>
                )}
              </div>

              {/* Per-image descriptions (manual mode) or prompt template (auto mode) */}
              {autoImages ? (
                <div>
                  <label className="text-sm font-medium">Auto Mode</label>
                  <p className="text-xs text-muted-foreground mt-0.5">No prompt needed — each product gets images matching its scraped count, using the reference image alone</p>
                </div>
              ) : (
                <div className="space-y-3">
                  <label className="text-sm font-medium">Image Descriptions</label>
                  <p className="text-xs text-muted-foreground mt-0.5 mb-2">Describe what each generated image should show</p>
                  {Array.from({ length: numImages }, (_, i) => (
                    <div key={i} className="flex gap-2 items-start">
                      <span className="text-xs text-muted-foreground font-mono mt-2 w-6">#{i + 1}</span>
                      <Input
                        placeholder={`e.g. Front view, white background`}
                        value={imageDescriptions[i] || ""}
                        onChange={(e) => {
                          const next = [...imageDescriptions];
                          next[i] = e.target.value;
                          setImageDescriptions(next);
                        }}
                        className="flex-1"
                      />
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Button onClick={handleGenerate} className="w-full" size="lg">
            <Image className="h-4 w-4 mr-2" />
            Generate {totalOutput} Images
          </Button>
        </>
      )}

      {/* Scraped-only state (no API keys) */}
      {state === "scraped_only" && uploadResult && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-success" />
                Products Scraped — {uploadResult.total_products} products discovered
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="rounded-lg border p-3 text-center">
                  <p className="text-2xl font-bold">{uploadResult.total_products}</p>
                  <p className="text-xs text-muted-foreground">Products</p>
                </div>
                <div className="rounded-lg border p-3 text-center">
                  <p className="text-2xl font-bold">{uploadResult.total_products}</p>
                  <p className="text-xs text-muted-foreground">Images Scraping</p>
                </div>
              </div>

              <div className="rounded-lg bg-amber-50 border border-amber-200 p-4">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5 shrink-0" />
                  <div className="space-y-1">
                    <p className="font-medium text-amber-800">No AI API Keys Configured</p>
                    <p className="text-sm text-amber-700">
                      Products will be scraped (images and names extracted from URLs), but AI image generation
                      requires at least one AI provider API key. Navigate to <strong>Settings &gt; AI Provider Keys</strong> to configure keys, then come back to generate images.
                    </p>
                  </div>
                </div>
              </div>

              <div className="flex gap-3">
                <Button variant="outline" className="flex-1" onClick={() => { setState("idle"); setFile(null); setUploadResult(null); }}>
                  Upload Another File
                </Button>
                <Button variant="default" className="flex-1" onClick={() => window.location.href = "/products"}>
                  <ExternalLink className="h-4 w-4 mr-2" />
                  View Scraped Products
                </Button>
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {/* Step 3: Generating */}
      {state === "generating" && (
        <Card>
          <CardContent className="py-12 text-center">
            <Loader2 className="h-8 w-8 mx-auto animate-spin text-primary" />
            <p className="text-lg font-medium mt-4">Generating Images...</p>
            <p className="text-sm text-muted-foreground">AI is creating your product images. This may take a few minutes.</p>
          </CardContent>
        </Card>
      )}

      {/* Done */}
      {state === "done" && generationResult && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-success" />
              Generation Queued
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">{generationResult.message}</p>
            <Progress value={100} className="mt-2" />
            <Button variant="outline" className="w-full mt-2" onClick={() => { setState("idle"); setFile(null); setUploadResult(null); setGenerationResult(null); }}>
              Upload Another File
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Info */}
      {state === "idle" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Requirements</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center gap-2"><Badge variant="outline">XLSX</Badge><span className="text-muted-foreground">Excel file with a column named &quot;URL&quot;, &quot;Link&quot;, or &quot;Product URL&quot;</span></div>
            <div className="flex items-center gap-2"><Badge variant="outline">URLs</Badge><span className="text-muted-foreground">At least 1 product link starting with http:// or https://</span></div>
            <div className="mt-3 p-3 rounded-lg bg-muted">
              <p className="font-medium text-xs flex items-center gap-2"><AlertTriangle className="h-3 w-3 text-warning" /> Empty or invalid URLs will be rejected with a clear error</p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
