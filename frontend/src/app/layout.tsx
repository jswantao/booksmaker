import type { Metadata } from "next";
import { Crimson_Pro, Atkinson_Hyperlegible, Fira_Code } from "next/font/google";
import { ThemeProvider } from "next-themes";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import Providers from "./providers";
import "./globals.css";

const crimsonPro = Crimson_Pro({
  variable: "--font-heading-family",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const atkinson = Atkinson_Hyperlegible({
  variable: "--font-body",
  subsets: ["latin"],
  weight: ["400", "700"],
  display: "swap",
  fallback: ["Inter", "Noto Sans SC", "system-ui", "sans-serif"],
});

const firaCode = Fira_Code({
  variable: "--font-mono-family",
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "电子书翻译制作工作台",
  description: "智能翻译与EPUB工作台 — 本地历史学术翻译系统",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="zh-CN"
      suppressHydrationWarning
      className={`${crimsonPro.variable} ${atkinson.variable} ${firaCode.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <TooltipProvider>
            <Providers>
              {children}
              <Toaster richColors closeButton position="top-right" />
            </Providers>
          </TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
