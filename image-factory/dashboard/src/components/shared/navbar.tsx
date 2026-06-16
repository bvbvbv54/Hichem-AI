"use client";

import { useTheme } from "next-themes";
import { useAuthStore, useNotificationsStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Bell, Moon, Sun, LogOut, User, ChevronDown } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { api } from "@/lib/api";

export function Navbar() {
  const { theme, setTheme } = useTheme();
  const { user, logout } = useAuthStore();
  const { unreadCount, setNotifications } = useNotificationsStore();
  const router = useRouter();

  useEffect(() => {
    api.getNotifications({ unread_only: true }).then((data) => {
      setNotifications(data.notifications, data.unread_count);
    }).catch(() => {});
  }, [setNotifications]);

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-4 border-b bg-background px-4 sm:px-6">
      <div className="flex-1" />

      <Button
        variant="ghost"
        size="icon"
        className="relative"
        onClick={() => router.push("/notifications")}
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[9px] font-bold text-destructive-foreground">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </Button>

      <Button
        variant="ghost"
        size="icon"
        onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      >
        {theme === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
      </Button>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="gap-2 px-2">
            <User className="h-4 w-4" />
            <span className="hidden sm:inline text-sm">{user?.name || "User"}</span>
            <ChevronDown className="h-3 w-3 opacity-50" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          <DropdownMenuLabel>{user?.email || ""}</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => router.push("/settings")}>
            Settings
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={handleLogout}>
            <LogOut className="h-4 w-4 mr-2" /> Logout
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
