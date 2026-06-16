"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { SystemStatusPanel } from "@/components/dashboard/system-status";
import { QueuePanel } from "@/components/dashboard/queue-panel";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Users, FolderKanban, Briefcase, Activity, BarChart3 } from "lucide-react";

export default function AdminPage() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ["admin-stats"],
    queryFn: () => api.getAdminStats(),
  });

  const { data: users } = useQuery({
    queryKey: ["admin-users"],
    queryFn: () => api.listUsers(),
  });

  const { data: status } = useQuery({
    queryKey: ["system-status"],
    queryFn: () => api.getSystemStatus(),
  });

  const { data: queue } = useQuery({
    queryKey: ["queue-info"],
    queryFn: () => api.getQueueInfo(),
  });

  if (isLoading) return <AdminSkeleton />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Admin</h1>
        <p className="text-muted-foreground">Platform operations and monitoring</p>
      </div>

      {/* Overview Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-xs text-muted-foreground">Total Users</CardTitle></CardHeader>
          <CardContent className="flex items-center gap-2"><Users className="h-4 w-4 text-muted-foreground" /><span className="text-2xl font-bold">{stats?.total_users || 0}</span></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-xs text-muted-foreground">Projects</CardTitle></CardHeader>
          <CardContent className="flex items-center gap-2"><FolderKanban className="h-4 w-4 text-muted-foreground" /><span className="text-2xl font-bold">{stats?.total_projects || 0}</span></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-xs text-muted-foreground">Total Jobs</CardTitle></CardHeader>
          <CardContent className="flex items-center gap-2"><Briefcase className="h-4 w-4 text-muted-foreground" /><span className="text-2xl font-bold">{stats?.total_jobs || 0}</span></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-xs text-muted-foreground">API Calls</CardTitle></CardHeader>
          <CardContent className="flex items-center gap-2"><Activity className="h-4 w-4 text-muted-foreground" /><span className="text-2xl font-bold">{stats?.total_api_usage || 0}</span></CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-xs text-muted-foreground">Active Workers</CardTitle></CardHeader>
          <CardContent className="flex items-center gap-2"><BarChart3 className="h-4 w-4 text-muted-foreground" /><span className="text-2xl font-bold">{stats?.worker_stats?.active || 0}<span className="text-sm text-muted-foreground">/{stats?.worker_stats?.max_concurrency || 0}</span></span></CardContent>
        </Card>
      </div>

      {/* System Status & Queue */}
      <div className="grid gap-6 lg:grid-cols-2">
        <SystemStatusPanel status={status || stats?.infrastructure} />
        <QueuePanel queue={queue || stats?.queue_stats} />
      </div>

      {/* Users Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Users</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Joined</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(users?.users || []).length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="text-center text-muted-foreground py-8">No users found</TableCell>
                </TableRow>
              ) : (
                (users?.users || []).map((user: any) => (
                  <TableRow key={user.id}>
                    <TableCell className="font-medium">{user.name}</TableCell>
                    <TableCell>{user.email}</TableCell>
                    <TableCell>
                      <Badge variant={user.role === "admin" ? "default" : "secondary"}>{user.role}</Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{new Date(user.created_at).toLocaleDateString()}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

function AdminSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-8 w-32" />
      <div className="grid gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}><CardContent className="p-6"><Skeleton className="h-8 w-16" /></CardContent></Card>
        ))}
      </div>
    </div>
  );
}
