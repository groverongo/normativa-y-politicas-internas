import { Link, useRouterState, useNavigate } from "@tanstack/react-router";
import { BookOpen, MessageSquareText, ShieldCheck, Search } from "lucide-react";
import { useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { services } from "@/services";

const nav = [
  { to: "/", label: "Consultor normativo", icon: MessageSquareText },
  { to: "/biblioteca", label: "Biblioteca documental", icon: BookOpen },
  { to: "/validaciones", label: "Validaciones", icon: ShieldCheck },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const isActive = (to: string) => (to === "/" ? path === "/" : path.startsWith(to));
  const current = nav.find((n) => isActive(n.to))?.label ?? "Horizonte";

  return (
    <div className="flex min-h-screen gap-3.5 p-3.5 max-md:flex-col">
      <aside className="glass-panel sticky top-3.5 flex h-[calc(100vh-28px)] w-[218px] shrink-0 flex-col rounded-[26px] px-3 py-5 shadow-soft max-md:static max-md:h-auto max-md:w-full max-md:flex-row max-md:items-center max-md:gap-2 max-md:py-3">
        <div className="flex items-center gap-2.5 border-b border-sidebar-border px-2 pb-5 max-md:border-0 max-md:pb-0">
          <div className="grid size-9 place-items-center rounded-full bg-primary text-lg font-extrabold text-primary-foreground">H</div>
          <div className="max-md:hidden">
            <div className="text-base font-bold tracking-tight">Horizonte</div>
            <div className="text-[10px] uppercase tracking-[1.2px] text-muted-foreground">Intelligence</div>
          </div>
        </div>
        <div className="eyebrow px-3 pb-2 pt-5 max-md:hidden">Espacio de trabajo</div>
        <nav className="flex flex-col gap-1 max-md:flex-row max-md:overflow-x-auto">
          {nav.map((n) => (
            <Link
              key={n.to}
              to={n.to}
              className={cn(
                "flex items-center gap-3 whitespace-nowrap rounded-3xl px-3.5 py-2.5 text-[13px] text-sidebar-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground",
                isActive(n.to) && "bg-primary font-semibold text-primary-foreground hover:bg-primary hover:text-primary-foreground",
              )}
            >
              <n.icon className="size-[17px]" />
              <span>{n.label}</span>
            </Link>
          ))}
        </nav>
        <div className="mt-auto border-t border-sidebar-border px-2 pt-4 max-md:hidden">
          <div className="flex items-center gap-2.5">
            <div className="grid size-9 place-items-center rounded-full bg-secondary text-[12px] font-bold">MC</div>
            <div>
              <div className="text-[12px] font-semibold">María Cárdenas</div>
              <div className="text-[11px] text-muted-foreground">Analista de riesgos · demo</div>
            </div>
          </div>
        </div>
      </aside>

      <main className="min-w-0 flex-1">
        <header className="glass-panel sticky top-3.5 z-10 mb-3.5 flex h-[68px] items-center justify-between gap-4 rounded-[22px] px-6">
          <div className="truncate text-[12px] text-muted-foreground">
            Financiera Horizonte <span className="mx-1.5 opacity-50">/</span>
            <strong className="font-semibold text-foreground">{current}</strong>
          </div>
          <div className="flex items-center gap-3">
            {services.mode === "demo" && (
              <span className="hidden rounded-full bg-warning-soft px-3 py-1 text-[10px] font-bold text-warning sm:inline">Datos de prueba</span>
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                navigate({ to: "/biblioteca", search: { q: q.trim() || undefined } });
              }}
              className="flex min-w-[230px] items-center gap-2 rounded-3xl bg-secondary px-3.5 py-2.5 max-sm:min-w-0"
            >
              <Search className="size-4 text-muted-foreground" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Buscar documento..."
                aria-label="Buscar documento"
                className="w-full bg-transparent text-[12px] outline-none placeholder:text-muted-foreground"
              />
            </form>
          </div>
        </header>
        <div className="mx-auto max-w-[1600px] px-6 pb-10 pt-6 max-sm:px-2">{children}</div>
      </main>
    </div>
  );
}
