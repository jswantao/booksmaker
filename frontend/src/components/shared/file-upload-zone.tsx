"use client";

import { useRef, useState } from "react";
import { Upload } from "lucide-react";
import { cn } from "@/lib/utils";

interface FileUploadZoneProps {
  accept?: string;
  onFile: (file: File) => void;
  label?: string;
  hint?: string;
  className?: string;
}

export function FileUploadZone({
  accept = ".txt,.md,.pdf,.epub",
  onFile,
  label = "点击或拖拽上传文件",
  hint,
  className,
}: FileUploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileName, setFileName] = useState("");

  return (
    <div
      className={cn(
        "border-2 border-dashed border-border rounded-lg p-6 text-center cursor-pointer hover:border-primary/50 transition-colors",
        className
      )}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        const file = e.dataTransfer.files[0];
        if (file) {
          setFileName(file.name);
          onFile(file);
        }
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) {
            setFileName(file.name);
            onFile(file);
          }
        }}
      />
      <Upload className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
      <p className="text-sm font-medium">{fileName || label}</p>
      {hint && <p className="text-xs text-muted-foreground mt-1">{hint}</p>}
    </div>
  );
}
