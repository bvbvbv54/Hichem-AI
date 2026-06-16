"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  FolderKanban,
  Upload,
  Image,
  Package,
  Settings,
  Shield,
  ChevronLeft,
  Bell,
} from "lucide-react";
import { useUIStore, useNotificationsStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/projects", label: "Projects", icon: FolderKanban },
  { href: "/upload", label: "Upload", icon: Upload },
  { href: "/products", label: "Products", icon: Package },
];

const bottomItems = [
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/admin", label: "Admin", icon: Shield },
];

export function Sidebar() {
  const pathname = usePathname();
  const { sidebarOpen, toggleSidebar } = useUIStore();
  const unreadCount = useNotificationsStore((s) => s.unreadCount);

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-40 flex h-screen flex-col border-r bg-sidebar text-sidebar-foreground transition-all duration-300",
        sidebarOpen ? "w-60" : "w-16"
      )}
    >
      <div className="flex h-14 items-center justify-between px-4">
        {sidebarOpen && (
          <Link href="/dashboard" className="font-bold text-lg tracking-tight">
            ImageFactory
          </Link>
        )}
        <Button variant="ghost" size="icon" onClick={toggleSidebar} className="text-sidebar-foreground/70 hover:text-sidebar-foreground">
          <ChevronLeft className={cn("h-4 w-4 transition-transform", !sidebarOpen && "rotate-180")} />
        </Button>
      </div>

      <Separator className="bg-sidebar-muted" />

      <nav className="flex-1 space-y-1 p-2">
        {navItems.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link key={item.href} href={item.href}>
              <span
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-sidebar-muted text-sidebar-foreground"
                    : "text-sidebar-foreground/60 hover:bg-sidebar-muted hover:text-sidebar-foreground"
                )}
              >
                <item.icon className="h-4 w-4 shrink-0" />
                {sidebarOpen && item.label}
              </span>
            </Link>
          );
        })}
      </nav>

      <div className="p-2 space-y-1">
        <Link href="/notifications">
          <span className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-sidebar-foreground/60 hover:bg-sidebar-muted hover:text-sidebar-foreground transition-colors relative">
            <Bell className="h-4 w-4 shrink-0" />
            {sidebarOpen && "Notifications"}
            {unreadCount > 0 && (
              <span className="absolute right-2 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-destructive text-[10px] font-bold text-destructive-foreground">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </span>
        </Link>

        <Separator className="bg-sidebar-muted" />

        {bottomItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link key={item.href} href={item.href}>
              <span
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-sidebar-muted text-sidebar-foreground"
                    : "text-sidebar-foreground/60 hover:bg-sidebar-muted hover:text-sidebar-foreground"
                )}
              >
                <item.icon className="h-4 w-4 shrink-0" />
                {sidebarOpen && item.label}
              </span>
            </Link>
          );
        })}
      </div>
    </aside>
  );
}
