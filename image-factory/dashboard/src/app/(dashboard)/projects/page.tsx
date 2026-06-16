"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "@/hooks/use-toast";
import { Plus, FolderKanban, ExternalLink, Trash2, Search, Clock } from "lucide-react";
import { formatDate, statusLabel, statusColor } from "@/lib/utils";

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
