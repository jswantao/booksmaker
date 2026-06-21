"use client";

import { BlurFade } from "@/components/ui/blur-fade";
import { SparklesText } from "@/components/ui/sparkles-text";
import { ThemeToggle } from "./theme-toggle";

export function Header() {
  return (
    <div className="flex justify-between items-center flex-wrap gap-4 mb-7">
      <BlurFade delay={0.1} inView>
        <h1 className="text-2xl font-heading font-bold text-foreground flex items-center gap-3 m-0">
          <span className="accent-bar" />
          <SparklesText className="text-2xl font-bold" sparklesCount={3}>
            电子书翻译制作工作台
          </SparklesText>
        </h1>
      </BlurFade>
      <ThemeToggle />
    </div>
  );
}
