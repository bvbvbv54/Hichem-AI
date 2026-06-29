"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { toast } from "@/hooks/use-toast";
import {
  Upload, CheckCircle2, Loader2, AlertTriangle, Ban, Globe, Image, Trash2, FolderKanban, Plus, Check,
} from "lucide-react";
import { cn, formatDateTime } from "@/lib/utils";
import type { AcquisitionJob, SubmitUrlsResponse } from "@/types";
import * as XLSX from "xlsx";
import mammoth from "mammoth";

const STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  scraping: "Scraping",
  scraped: "Scraped",
  completed: "Completed",
  failed: "Failed",
  error: "Error",
  skipped: "Skipped",
};

const STATUS_BADGE: Record<string, string> = {
  pending: "bg-yellow-500/10 text-yellow-500 border-yellow-500/20",
  scraping: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  scraped: "bg-indigo-500/10 text-indigo-500 border-indigo-500/20",
  completed: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
  failed: "bg-rose-500/10 text-rose-500 border-rose-500/20",
  error: "bg-rose-500/10 text-rose-500 border-rose-500/20",
  skipped: "bg-muted text-muted-foreground border-muted-foreground/20",
};

function JobStatusBadge({ status }: { status: string }) {
  const color = STATUS_BADGE[status] || "text-muted-foreground bg-muted border-muted-foreground/20";
  return <Badge className={cn(color, "text-[10px] px-1.5 py-0")}>{STATUS_LABELS[status] || status}</Badge>;
}

const URL_REGEX = /https?:\/\/[^\s<>"']+/gi;

async function parseTXT(file: File): Promise<string[]> {
  const text = await file.text();
  return text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#") && URL_REGEX.test(l));
}

async function parseXLSX(file: File): Promise<string[]> {
  const buf = await file.arrayBuffer();
  const wb = XLSX.read(buf, { type: "array" });
  const urls: string[] = [];
  for (const name of wb.SheetNames) {
    const ws = wb.Sheets[name];
    const rows: any[][] = XLSX.utils.sheet_to_json(ws, { header: 1 });
    for (const row of rows) {
      for (const cell of row) {
        if (typeof cell === "string") {
          const found = cell.match(URL_REGEX);
          if (found) urls.push(...found);
        }
      }
    }
  }
  return urls;
}

async function parseDOCX(file: File): Promise<string[]> {
  const buf = await file.arrayBuffer();
  const result = await mammoth.extractRawText({ arrayBuffer: buf });
  const urls: string[] = [];
  const found = result.value.match(URL_REGEX);
  if (found) urls.push(...found);
  return urls;
}

async function parseFile(file: File): Promise<string[]> {
  const name = file.name.toLowerCase();
  if (name.endsWith(".txt")) return parseTXT(file);
  if (name.endsWith(".xlsx")) return parseXLSX(file);
  if (name.endsWith(".docx")) return parseDOCX(file);
  throw new Error("Unsupported file type. Use .txt, .xlsx, or .docx files.");
}

export default function UploadPage() {
  const [urlText, setUrlText] = useState("");
  const [submittedJobs, setSubmittedJobs] = useState<SubmitUrlsResponse | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [showNewProjectInput, setShowNewProjectInput] = useState(false);
  const [newProjectName, setNewProjectName] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const queryClient = useQueryClient();

  const { data: projectsData } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.listProjects({ limit: 100 }),
  });
  const projects = projectsData?.projects || [];

  const createProjectMutation = useMutation({
    mutationFn: (name: string) => api.createProject({ name }),
    onSuccess: (newProject) => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setSelectedProjectId(newProject.id);
      setShowNewProjectInput(false);
      setNewProjectName("");
      toast({ title: "Project created", description: `Project "${newProject.name}" created and selected.` });
    },
    onError: (err: any) => {
      toast({ title: "Failed to create project", description: err.message, variant: "destructive" });
    },
  });

  const selectedProject = projects.find((p: any) => p.id === selectedProjectId);

  const parseUrls = (text: string): string[] => {
    return text
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => {
        if (!line || line.startsWith("#")) return false;
        try {
          const url = new URL(line);
          return url.protocol === "http:" || url.protocol === "https:";
        } catch {
          return false;
        }
      });
  };

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setParsing(true);
    try {
      const urls = await parseFile(file);
      if (urls.length === 0) {
        toast({ title: "No URLs found", description: "Could not extract any valid URLs from the file." });
        return;
      }
      const existing = parseUrls(urlText);
      const combined = [...existing, ...urls.filter((u) => !existing.includes(u))];
      setUrlText(combined.join("\n"));
      toast({ title: "URLs extracted", description: `${urls.length} URL(s) loaded from ${file.name}` });
    } catch (err: any) {
      toast({ title: "Failed to parse file", description: err.message, variant: "destructive" });
    } finally {
      setParsing(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const submitMutation = useMutation({
    mutationFn: (urls: string[]) => api.submitUrls(urls, selectedProjectId, 0, ""),
    onSuccess: (data: SubmitUrlsResponse) => {
      setSubmittedJobs(data);
      setIsPolling(true);
      queryClient.invalidateQueries({ queryKey: ["acquisition-stats"] });
      queryClient.invalidateQueries({ queryKey: ["acquisition-jobs"] });
      toast({
        title: "URLs submitted",
        description: `${data.accepted} accepted, ${data.skipped_banned} banned domains skipped, ${data.skipped_duplicates} duplicates skipped`,
        variant: data.accepted > 0 ? "success" : "default",
      });
    },
    onError: (err: any) => {
      toast({ title: "Submission failed", description: err.message, variant: "destructive" });
    },
  });

  const { data: polledJobs, isLoading: pollingJobs } = useQuery({
    queryKey: ["acquisition-jobs", "polling"],
    queryFn: () => api.getAcquisitionJobs({ limit: 50 }),
    refetchInterval: isPolling ? 2000 : false,
    enabled: isPolling,
  });

  const handleSubmit = () => {
    const urls = parseUrls(urlText);
    if (urls.length === 0) {
      toast({
        title: "No valid URLs",
        description: "Paste URLs or upload a file (.txt, .xlsx, .docx) to get started.",
        variant: "destructive",
      });
      return;
    }
    submitMutation.mutate(urls);
  };

  const handleClear = () => {
    setUrlText("");
    setSubmittedJobs(null);
    setIsPolling(false);
  };

  const urls = parseUrls(urlText);
  const validCount = urls.length;
  const hasInvalid = urlText.trim().length > 0 && validCount === 0;

  const allJobs: AcquisitionJob[] = polledJobs?.jobs || [];
  const recentJobs = submittedJobs
    ? allJobs.filter((j) => submittedJobs.jobs.some((sj) => sj.url === j.url))
    : [];

  const terminalStates = new Set(["completed", "failed", "error", "skipped", "scraped"]);
  const allDone = recentJobs.length > 0 && recentJobs.every((j) => terminalStates.has(j.status));
  const prevDoneRef = useRef(false);

  useEffect(() => {
    if (allDone && isPolling && !prevDoneRef.current) {
      const timer = setTimeout(() => setIsPolling(false), 1500);
      prevDoneRef.current = true;
      return () => clearTimeout(timer);
    }
    if (!allDone) prevDoneRef.current = false;
  }, [allDone, isPolling]);

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Scrape & AI</h1>
        <p className="text-muted-foreground">
          Paste product URLs or upload a file to scrape images and product data.
        </p>
      </div>

      {/* Project Selector */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <FolderKanban className="h-5 w-5" />
            Project
          </CardTitle>
          <CardDescription>
            Select or create a project to organize scraped products. A project is required before submitting URLs.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {showNewProjectInput ? (
            <div className="flex items-center gap-2">
              <Input
                placeholder="New project name"
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
                className="flex-1"
                autoFocus
                disabled={createProjectMutation.isPending}
              />
              <Button
                size="sm"
                onClick={() => createProjectMutation.mutate(newProjectName)}
                disabled={!newProjectName.trim() || createProjectMutation.isPending}
              >
                {createProjectMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4 mr-1" />}
                Create
              </Button>
              <Button variant="ghost" size="sm" onClick={() => { setShowNewProjectInput(false); setNewProjectName(""); }}>
                Cancel
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Select value={selectedProjectId} onValueChange={setSelectedProjectId}>
                <SelectTrigger className="flex-1">
                  <SelectValue placeholder="Select a project..." />
                </SelectTrigger>
                <SelectContent>
                  {projects.map((p: any) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name} {p.product_count > 0 && `(${p.product_count} products)`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button variant="outline" size="sm" onClick={() => setShowNewProjectInput(true)}>
                <Plus className="h-4 w-4 mr-1" /> New
              </Button>
            </div>
          )}
          {selectedProject && (
            <p className="text-xs text-muted-foreground mt-2 flex items-center gap-1">
              <CheckCircle2 className="h-3 w-3 text-emerald-500" />
              Active project: <strong>{selectedProject.name}</strong>
              {selectedProject.product_count > 0 && <> &middot; {selectedProject.product_count} products</>}
            </p>
          )}
        </CardContent>
      </Card>

      {/* URL Input */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Upload className="h-5 w-5" />
            Product URLs
          </CardTitle>
          <CardDescription>
            Paste URLs from any supported marketplace (Amazon, DHgate, 1688, Made-in-China, etc.) or upload a file.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.xlsx,.docx"
              onChange={handleFile}
              className="block w-full text-xs text-muted-foreground file:mr-2 file:py-1 file:px-3 file:rounded-md file:border-0 file:text-xs file:font-medium file:bg-primary file:text-primary-foreground hover:file:bg-primary/90"
              disabled={parsing || submitMutation.isPending}
            />
            {parsing && <Loader2 className="h-4 w-4 animate-spin shrink-0 text-muted-foreground" />}
          </div>

          <Textarea
            placeholder={
              "https://www.amazon.com/dp/B0EXAMPLE1\n" +
              "https://www.dhgate.com/product/example/123456789.html\n" +
              "https://detail.1688.com/offer/1234567890.html"
            }
            value={urlText}
            onChange={(e) => setUrlText(e.target.value)}
            className="min-h-[150px] font-mono text-sm"
            disabled={submitMutation.isPending}
          />

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm">
              {urlText.trim().length > 0 && (
                <>
                  <Badge variant="outline" className={validCount > 0 ? "text-emerald-500" : "text-rose-500"}>
                    {validCount} valid URL{validCount !== 1 ? "s" : ""}
                  </Badge>
                  {hasInvalid && (
                    <span className="text-xs text-rose-500 flex items-center gap-1">
                      <AlertTriangle className="h-3 w-3" />
                      Invalid URLs found
                    </span>
                  )}
                </>
              )}
            </div>
            <div className="flex gap-2">
              {submittedJobs && (
                <Button variant="outline" size="sm" onClick={handleClear}>
                  <Trash2 className="h-4 w-4 mr-1" /> Clear
                </Button>
              )}
              <Button
                onClick={handleSubmit}
                disabled={!selectedProjectId || validCount === 0 || submitMutation.isPending}
                size="sm"
                title={!selectedProjectId ? "Select or create a project first" : ""}
              >
                {submitMutation.isPending ? (
                  <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> Submitting...</>
                ) : (
                  <><Upload className="h-4 w-4 mr-1" /> Start Scraping</>
                )}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Banned domain note */}
      {urls.some((u) => ["jd.com", "taobao.com", "temu.com"].some((b) => u.includes(b))) && (
        <Card className="border-amber-300 bg-amber-50 dark:bg-amber-950/20">
          <CardContent className="p-4 flex items-start gap-3">
            <Ban className="h-5 w-5 text-amber-600 mt-0.5 shrink-0" />
            <div className="space-y-1">
              <p className="font-medium text-amber-800 dark:text-amber-300">Banned Domains Detected</p>
              <p className="text-sm text-amber-700 dark:text-amber-400">
                JD.com, Taobao, and Temu are permanently banned. URLs from these domains will be
                skipped with zero network attempts.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Submission result */}
      {submittedJobs && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              Submission Result
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="rounded-lg border p-3">
                <p className="text-2xl font-bold text-emerald-500">{submittedJobs.accepted}</p>
                <p className="text-xs text-muted-foreground">Accepted</p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-2xl font-bold text-amber-500">{submittedJobs.skipped_banned}</p>
                <p className="text-xs text-muted-foreground">Banned domains</p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="text-2xl font-bold text-muted-foreground">{submittedJobs.skipped_duplicates}</p>
                <p className="text-xs text-muted-foreground">Duplicates</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Live status per job */}
      {submittedJobs && recentJobs.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              {allDone ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              ) : (
                <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
              )}
              Job Status
              {!allDone && (
                <span className="text-xs text-muted-foreground font-normal animate-pulse">updating...</span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {recentJobs.map((job) => (
              <div
                key={job.id}
                className="flex items-center justify-between gap-3 rounded-lg border p-3 text-sm"
              >
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <Globe className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                  <span className="truncate text-xs font-mono" title={job.url}>{job.url}</span>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  {job.image_count > 0 && (
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Image className="h-3 w-3" />
                      {job.image_count}
                    </span>
                  )}
                  <JobStatusBadge status={job.status} />
                  {job.status === "failed" || job.status === "error" ? (
                    <span className="text-[10px] text-rose-500 max-w-[120px] truncate" title={job.error_message}>
                      {job.failure_type || "error"}
                    </span>
                  ) : job.status === "skipped" ? (
                    <span className="text-[10px] text-muted-foreground">banned domain</span>
                  ) : null}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Info */}
      {!submittedJobs && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Supported Sites</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center gap-2"><Badge variant="outline" className="text-emerald-500 border-emerald-500/30">Working</Badge><span className="text-muted-foreground">Amazon, DHgate, 1688, Made-in-China</span></div>
            <div className="flex items-center gap-2"><Badge variant="outline" className="text-amber-500 border-amber-500/30">Known Issues</Badge><span className="text-muted-foreground">Alibaba, AliExpress (partial extraction)</span></div>
            <div className="flex items-center gap-2"><Badge variant="outline" className="text-muted-foreground">Not Supported</Badge><span className="text-muted-foreground">JD.com, Taobao, Temu (permanently banned)</span></div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
