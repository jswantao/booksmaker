"use client";

import { useTheme } from "next-themes";
import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useEffect, useState } from "react";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return (
      <Button variant="outline" size="sm" className="rounded-full min-w-[110px]">
        <Sun className="h-4 w-4" />
        <span className="ml-2">暗色模式</span>
      </Button>
    );
  }

  const isDark = theme === "dark";

  return (
    <Button
      variant="outline"
      size="sm"
      className="rounded-full min-w-[110px]"
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      {isDark ? (
        <>
          <Sun className="h-4 w-4" />
          <span className="ml-2">亮色模式</span>
        </>
      ) : (
        <>
          <Moon className="h-4 w-4" />
          <span className="ml-2">暗色模式</span>
        </>
      )}
    </Button>
  );
}
