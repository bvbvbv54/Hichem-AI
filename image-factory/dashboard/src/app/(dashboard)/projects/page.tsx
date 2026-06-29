"use client";

import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/hooks/use-toast";
import {
  Plus, FolderKanban, ExternalLink, Trash2, Search, Clock, Loader2, CheckCircle2, AlertTriangle,
  Download, Cloud, Settings,
} from "lucide-react";
import { formatDate, statusLabel, statusColor } from "@/lib/utils";

function JobStatusBadge({ projectId }: { projectId: string }) {
  const { data: jobStatus } = useQuery({
    queryKey: ["project-jobs", projectId],
    queryFn: () => api.getProjectJobs(projectId),
    refetchInterval: 5000,
  });

  if (!jobStatus || jobStatus.total === 0) return null;

  const active = jobStatus.pending + jobStatus.scraping + jobStatus.generating;
  const failed = jobStatus.failed;
  const done = jobStatus.completed + jobStatus.scraped + jobStatus.skipped;
  const allDone = active === 0;

  if (allDone && failed > 0) {
    return (
      <div className="flex items-center gap-1 text-xs mt-2">
        <AlertTriangle className="h-3 w-3 text-amber-500" />
        <span className="text-amber-600">{done} done, {failed} failed</span>
      </div>
    );
  }

  if (allDone && done > 0) {
    return (
      <div className="flex items-center gap-1 text-xs mt-2">
        <CheckCircle2 className="h-3 w-3 text-emerald-500" />
        <span className="text-emerald-600">{done} complete</span>
      </div>
    );
  }

  if (active > 0) {
    const progress = jobStatus.total > 0 ? Math.round((done / jobStatus.total) * 100) : 0;
    return (
      <div className="flex items-center gap-1 text-xs mt-2">
        <Loader2 className="h-3 w-3 text-blue-500 animate-spin" />
        <span className="text-blue-600">
          {jobStatus.scraping > 0
            ? `Scraping: ${jobStatus.scraping} active`
            : jobStatus.generating > 0
              ? `Generating: ${jobStatus.generating} active`
              : `Queued: ${jobStatus.pending} pending`
          }
          {jobStatus.total > 0 && ` (${progress}%)`}
        </span>
      </div>
    );
  }

  return null;
}

function ExportProjectDialog({ projectId, projectName, hasProducts }: { projectId: string; projectName: string; hasProducts: boolean }) {
  const [open, setOpen] = useState(false);
  const [zipLoading, setZipLoading] = useState(false);
  const [driveLoading, setDriveLoading] = useState(false);
  const [driveResult, setDriveResult] = useState<{ success?: boolean; folder_url?: string; error?: string } | null>(null);
  const [showDriveHint, setShowDriveHint] = useState(false);
  const queryClient = useQueryClient();

  const { data: driveCreds } = useQuery({
    queryKey: ["drive-credentials"],
    queryFn: () => api.getDriveCredentials(),
    staleTime: 30000,
  });
  const isDriveConfigured = driveCreds?.configured === true;

  const handleZipDownload = async () => {
    setZipLoading(true);
    try {
      const blob = await api.exportProjectZip(projectId, projectName);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${projectName.replace(/[^a-zA-Z0-9_-]/g, "_")}.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      toast({ title: "Export complete", description: "ZIP download started." });
    } catch (err: any) {
      toast({ title: "Export failed", description: err.message || "Could not generate ZIP", variant: "destructive" });
    } finally {
      setZipLoading(false);
    }
  };

  const handleDriveExport = async () => {
    if (!isDriveConfigured) {
      setShowDriveHint(true);
      return;
    }
    setDriveLoading(true);
    setDriveResult(null);
    try {
      const res = await api.exportProjectToDrive(projectId, projectName);
      setDriveResult({ success: res.status === "success", folder_url: res.folder_url, error: res.errors?.[0] });
      if (res.status === "success") {
        toast({ title: "Drive export complete", description: `Uploaded ${res.uploaded} images to Drive.` });
        queryClient.invalidateQueries({ queryKey: ["notifications"] });
      } else {
        toast({ title: "Drive export partial", description: res.errors?.[0] || "Some files failed", variant: "destructive" });
      }
    } catch (err: any) {
      setDriveResult({ success: false, error: err.message });
      toast({ title: "Drive export failed", description: err.message, variant: "destructive" });
    } finally {
      setDriveLoading(false);
    }
  };

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" disabled={!hasProducts}>
          <Download className="h-3 w-3 mr-1" /> Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuItem onSelect={(e) => { e.preventDefault(); handleZipDownload(); }} disabled={zipLoading}>
          {zipLoading ? (
            <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Preparing ZIP...</>
          ) : (
            <><Download className="h-4 w-4 mr-2" /> Download ZIP</>
          )}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={(e) => { e.preventDefault(); handleDriveExport(); }} disabled={driveLoading}>
          {driveLoading ? (
            <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Exporting to Drive...</>
          ) : (
            <><Cloud className="h-4 w-4 mr-2" /> Export to Google Drive</>
          )}
        </DropdownMenuItem>
        {showDriveHint && !isDriveConfigured && (
          <div className="px-3 py-2 text-xs text-muted-foreground border-t" onSelect={(e) => e.preventDefault()}>
            Connect Google Drive in{" "}
            <Link href="/settings" className="text-primary hover:underline inline-flex items-center gap-0.5" onClick={() => setOpen(false)}>
              <Settings className="h-3 w-3" /> Settings
            </Link>{" "}
            to enable this option.
          </div>
        )}
        {driveResult && (
          <div className={`px-3 py-2 text-xs border-t ${driveResult.success ? "text-emerald-600" : "text-red-600"}`} onSelect={(e) => e.preventDefault()}>
            {driveResult.success ? (
              <>Exported to Drive. {driveResult.folder_url && <a href={driveResult.folder_url} target="_blank" rel="noopener noreferrer" className="underline">Open folder</a>}</>
            ) : (
              <>Failed: {driveResult.error}</>
            )}
          </div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default function ProjectsPage() {
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: () => api.listProjects({ limit: 100 }),
  });

  const createMutation = useMutation({
    mutationFn: () => api.createProject({ name: newName, description: newDesc }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setOpen(false);
      setNewName("");
      setNewDesc("");
      toast({ title: "Project created", variant: "success" });
    },
    onError: (err: any) => toast({ title: "Failed", description: err.message, variant: "destructive" }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteProject(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      toast({ title: "Project deleted" });
    },
  });

  const projects = data?.projects?.filter((p: any) =>
    p.name.toLowerCase().includes(search.toLowerCase())
  ) || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Projects</h1>
          <p className="text-muted-foreground">Manage your product localization projects</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4 mr-2" /> New Project
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create Project</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 pt-4">
              <Input placeholder="Project name" value={newName} onChange={(e) => setNewName(e.target.value)} />
              <Input placeholder="Description (optional)" value={newDesc} onChange={(e) => setNewDesc(e.target.value)} />
              <Button onClick={() => createMutation.mutate()} disabled={!newName || createMutation.isPending} className="w-full">
                Create
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search projects..."
          className="pl-9"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i}><CardContent className="p-6"><Skeleton className="h-6 w-3/4" /><Skeleton className="h-4 w-1/2 mt-2" /><Skeleton className="h-4 w-full mt-2" /></CardContent></Card>
          ))}
        </div>
      ) : projects.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <FolderKanban className="h-12 w-12 text-muted-foreground mb-4" />
            <p className="text-lg font-medium">No projects yet</p>
            <p className="text-sm text-muted-foreground">Create your first project to get started</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {projects.map((project: any) => (
            <Card key={project.id} className="group relative">
              <CardContent className="p-6">
                <div className="flex items-start justify-between">
                  <div className="space-y-1">
                    <h3 className="font-semibold leading-none">{project.name}</h3>
                    {project.description && (
                      <p className="text-sm text-muted-foreground line-clamp-2">{project.description}</p>
                    )}
                  </div>
                  <Badge variant={project.status === "completed" ? "success" : project.status === "failed" ? "destructive" : "secondary"}>
                    {statusLabel(project.status)}
                  </Badge>
                </div>
                <div className="mt-4 flex items-center gap-4 text-sm text-muted-foreground">
                  <span>{project.product_count || 0} products</span>
                  <span>{project.generated_image_count || 0} images</span>
                </div>
                <JobStatusBadge projectId={project.id} />
                <div className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  {formatDate(project.created_at)}
                </div>
                <div className="mt-4 flex gap-2">
                  <Link href={`/projects/${project.id}`}>
                    <Button variant="outline" size="sm">
                      <ExternalLink className="h-3 w-3 mr-1" /> Open
                    </Button>
                  </Link>
                  <ExportProjectDialog
                    projectId={project.id}
                    projectName={project.name}
                    hasProducts={(project.product_count || 0) > 0}
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => deleteMutation.mutate(project.id)}
                    className="text-destructive"
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
