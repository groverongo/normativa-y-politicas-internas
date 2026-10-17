import { forwardRef, useRef } from "react";
import { useReducedMotion } from "motion/react";
import { BookOpen, CalendarCheck, FileCheck2, MessageSquareText, type LucideIcon } from "lucide-react";
import { AnimatedBeam } from "@/components/ui/animated-beam";
import { cn } from "@/lib/utils";
import type { ConsultStage } from "@/services";
import { Pill } from "./ui";

const stages: { id: ConsultStage; label: string; icon: LucideIcon; status: string }[] = [
  { id: "consulta", label: "Consulta", icon: MessageSquareText, status: "Interpretando la pregunta…" },
  { id: "recuperacion", label: "Biblioteca documental", icon: BookOpen, status: "Buscando fragmentos en la biblioteca documental…" },
  { id: "vigencia", label: "Evaluación de vigencia", icon: CalendarCheck, status: "Verificando versión aplicable y vigencia…" },
  { id: "respuesta", label: "Respuesta con evidencia", icon: FileCheck2, status: "Redactando la respuesta con sus fuentes…" },
];

const Node = forwardRef<HTMLDivElement, { icon: LucideIcon; label: string; state: "done" | "active" | "idle" }>(
  ({ icon: Icon, label, state }, ref) => (
    <div className="z-10 flex w-24 flex-col items-center gap-2 text-center max-sm:w-auto max-sm:flex-row max-sm:text-left">
      <div
        ref={ref}
        className={cn(
          "grid size-14 shrink-0 place-items-center rounded-full border-2 bg-card transition-all duration-300 max-md:size-12",
          state === "active" && "scale-110 border-primary bg-primary text-primary-foreground shadow-float",
          state === "done" && "border-primary text-foreground",
          state === "idle" && "border-border text-muted-foreground",
        )}
      >
        <Icon className="size-5" />
      </div>
      <span className={cn("text-[11px] leading-tight", state === "idle" ? "text-muted-foreground" : "font-semibold text-foreground")}>{label}</span>
    </div>
  ),
);
Node.displayName = "Node";

export function ConsultProgress({ stage, simulated }: { stage: ConsultStage; simulated: boolean }) {
  const container = useRef<HTMLDivElement>(null);
  const r0 = useRef<HTMLDivElement>(null);
  const r1 = useRef<HTMLDivElement>(null);
  const r2 = useRef<HTMLDivElement>(null);
  const r3 = useRef<HTMLDivElement>(null);
  const refs = [r0, r1, r2, r3];
  const reduce = useReducedMotion();
  const idx = stages.findIndex((s) => s.id === stage);

  return (
    <div className="glass-panel flex min-h-[330px] flex-col items-center justify-center gap-7 rounded-[22px] px-6 py-10" role="status" aria-live="polite">
      <div ref={container} className="relative flex w-full max-w-[720px] items-start justify-between max-sm:flex-col max-sm:items-start max-sm:gap-8 max-sm:pl-4">
        {stages.map((s, i) => (
          <Node key={s.id} ref={refs[i]} icon={s.icon} label={s.label} state={i < idx ? "done" : i === idx ? "active" : "idle"} />
        ))}
        {[0, 1, 2].map((i) => (
          <AnimatedBeam
            key={i}
            containerRef={container}
            fromRef={refs[i]!}
            toRef={refs[i + 1]!}
            pathOpacity={i < idx ? 0.9 : 0.6}
            pathColor={i < idx ? "var(--primary)" : "var(--border)"}
            duration={reduce ? 0 : 2.2}
            delay={i * 0.35}
            repeat={reduce ? 0 : Infinity}
            gradientStartColor={reduce ? "transparent" : "var(--primary)"}
            gradientStopColor={reduce ? "transparent" : "var(--muted-foreground)"}
          />
        ))}
      </div>
      <div className="text-center">
        <div className="text-[13px] font-semibold">{stages[idx]?.status}</div>
        <div className="mt-2">{simulated && <Pill tone="amber">Simulado · sin procesamiento real</Pill>}</div>
      </div>
    </div>
  );
}
