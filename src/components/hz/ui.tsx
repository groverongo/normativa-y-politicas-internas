import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { Tone } from "@/lib/domain/types";

const toneClass: Record<Tone, string> = {
  green: "bg-success-soft text-success",
  amber: "bg-warning-soft text-warning",
  red: "bg-danger-soft text-danger",
  gray: "bg-secondary text-secondary-foreground",
  blue: "bg-info-soft text-info",
};

export function Pill({ tone = "gray", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-1 text-[10px] font-bold", toneClass[tone], className)}>
      {children}
    </span>
  );
}

export function PageHead({ eyebrow, title, subtitle, actions }: { eyebrow: string; title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-5">
      <div className="min-w-0">
        <div className="eyebrow">{eyebrow}</div>
        <h1 className="mt-1 text-[30px] font-semibold tracking-[-1.2px]">{title}</h1>
        {subtitle && <p className="mt-1 text-[13px] text-muted-foreground">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("rounded-[18px] border border-border bg-card shadow-soft", className)}>{children}</div>;
}

export function Notice({ title, children, tone = "amber" }: { title: string; children: ReactNode; tone?: "amber" | "gray" }) {
  return (
    <div className={cn("mb-5 flex items-start gap-3 rounded-2xl px-4 py-3 text-[12px]", tone === "amber" ? "bg-warning-soft text-warning" : "bg-secondary text-secondary-foreground")}>
      <span aria-hidden className="mt-0.5 font-bold">⚠</span>
      <div>
        <strong className="block text-[13px]">{title}</strong>
        <div className="mt-0.5 leading-relaxed opacity-90">{children}</div>
      </div>
    </div>
  );
}

export function Highlighted({ text }: { text: string }) {
  const parts = text.split(/(\[\[.*?\]\])/g);
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith("[[") ? <mark key={i}>{p.slice(2, -2)}</mark> : <span key={i}>{p}</span>,
      )}
    </>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="p-9 text-center text-[12px] text-muted-foreground">{children}</div>;
}
