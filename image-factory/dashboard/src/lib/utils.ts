import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(date: string | Date): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(date));
}

export function formatDateTime(date: string | Date): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(date));
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatCost(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

export function statusColor(status: string): string {
  const map: Record<string, string> = {
    completed: "text-success",
    failed: "text-destructive",
    processing: "text-blue-500",
    pending: "text-muted-foreground",
    waiting: "text-muted-foreground",
    queued: "text-yellow-500",
    extracting: "text-blue-500",
    translating: "text-purple-500",
    generating_images: "text-pink-500",
    delivering: "text-cyan-500",
    draft: "text-muted-foreground",
    uploading: "text-blue-500",
    healthy: "text-success",
    warning: "text-warning",
    offline: "text-destructive",
  };
  return map[status] || "text-muted-foreground";
}

export function getProductDetailUrl(productId: string): string {
  return `/products/${productId}`;
}

export function statusLabel(status: string): string {
  return status
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
