import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { ArrowUpRight } from "lucide-react";
import { ConsultProgress } from "@/components/hz/ConsultProgress";
import { Button } from "@/components/ui/button";
import { Highlighted, PageHead, Pill } from "@/components/hz/ui";
import { services, type ConsultStage } from "@/services";
import { demoSuggestions } from "@/lib/demo/fixtures";
import type { ConsultAnswer, EvidenceLevel, Tone } from "@/lib/domain/types";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Consultor normativo · Horizonte Intelligence" },
      { name: "description", content: "Pregunta en lenguaje natural y revisa la evidencia documental que sustenta cada respuesta." },
      { property: "og:title", content: "Consultor normativo · Horizonte Intelligence" },
      { property: "og:description", content: "Respuestas normativas trazables, con fuentes, versiones y advertencias." },
    ],
  }),
  component: Consultor,
});

const levelMeta: Record<EvidenceLevel, { label: string; tone: Tone }> = {
  suficiente: { label: "Evidencia suficiente", tone: "green" },
  parcial: { label: "Evidencia parcial", tone: "amber" },
  insuficiente: { label: "Evidencia insuficiente", tone: "red" },
  revision: { label: "Requiere revisión humana", tone: "amber" },
};

function Consultor() {
  const [question, setQuestion] = useState("");
  const [stage, setStage] = useState<ConsultStage>("consulta");
  const ask = useMutation({
    mutationFn: (q: string) => {
      setStage("consulta");
      return services.askQuestion(q, setStage);
    },
  });

  const submit = (q: string) => {
    const t = q.trim();
    if (!t) return;
    setQuestion(t);
    ask.mutate(t);
  };

  return (
    <section className="mx-auto w-full max-w-[1000px]">
      <PageHead
        eyebrow="Horizonte Intelligence / Consulta"
        title="Consultor normativo"
        subtitle="Pregunta en lenguaje natural. Revisa la respuesta y abre la evidencia exacta que la sustenta."
        actions={services.mode === "demo" ? <Pill>Entorno simulado</Pill> : undefined}
      />

      {ask.isPending ? (
        <ConsultProgress stage={stage} simulated={services.mode === "demo"} />
      ) : ask.isError ? (
        <div className="glass-panel rounded-[22px] p-8 text-center">
          <Pill tone="red">Error de conexión</Pill>
          <p className="mt-3 text-[13px] text-muted-foreground">No se pudo completar la consulta. No se ha emitido ninguna conclusión.</p>
          <Button className="mt-4 rounded-full" onClick={() => submit(question)}>Reintentar</Button>
        </div>
      ) : ask.data ? (
        <AnswerView answer={ask.data} />
      ) : (
        <div className="glass-panel min-h-[330px] rounded-[22px] px-8 py-11 text-center">
          <div className="mx-auto mb-4 grid size-12 place-items-center rounded-full bg-primary text-2xl text-primary-foreground">✳</div>
          <h2 className="text-[27px] font-semibold tracking-[-0.7px]">¿Qué necesitas resolver?</h2>
          <p className="mx-auto mb-6 mt-2 max-w-[600px] text-[14px] leading-relaxed text-muted-foreground">
            Te mostraré una respuesta breve, los fragmentos relevantes y la fuente exacta. Si la evidencia no basta, te lo diré.
          </p>
          <div className="flex flex-wrap justify-center gap-2">
            {demoSuggestions.map((s) => (
              <button
                key={s.label}
                onClick={() => submit(s.prompt)}
                className="rounded-3xl border border-border bg-card px-3.5 py-2 text-[11px] text-secondary-foreground transition-colors hover:border-ring hover:bg-accent"
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(question);
        }}
        className="sticky bottom-3 z-[4] mt-3.5 rounded-[19px] border border-input bg-card p-3.5 shadow-float"
      >
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(question);
            }
          }}
          rows={2}
          aria-label="Consulta normativa"
          placeholder="Ej. ¿Qué política regula la evaluación de créditos y qué excepciones contempla?"
          className="min-h-[70px] w-full resize-y bg-transparent p-1 text-[13px] outline-none placeholder:text-muted-foreground"
        />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-warning" />
            {services.mode === "demo" ? "Respuestas predefinidas de demostración · no verificadas" : "Conectado a la biblioteca documental"}
          </span>
          <Button type="submit" className="rounded-full" disabled={!question.trim() || ask.isPending}>
            Consultar <ArrowUpRight />
          </Button>
        </div>
      </form>
      <p className="mx-1 mt-3 text-center text-[10px] leading-normal text-muted-foreground">
        Las respuestas de esta versión son simuladas y sus fragmentos son ficticios. En producción, la búsqueda, el análisis documental y la recuperación de fragmentos se ejecutarán en el servidor.
      </p>
    </section>
  );
}

function AnswerView({ answer }: { answer: ConsultAnswer }) {
  const lvl = levelMeta[answer.level];
  return (
    <article className="rounded-[22px] border border-glass-border bg-card/80 p-6 shadow-soft [overflow-wrap:anywhere] max-sm:p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Pill tone={lvl.tone}>{lvl.label}</Pill>
        <span className="text-[10px] text-muted-foreground">
          {answer.source === "demo" ? "Respuesta simulada · no verificada" : "Respuesta del motor"} ·{" "}
          {new Date(answer.answeredAt).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" })}
        </span>
      </div>
      <p className="mb-1 text-[11px] text-muted-foreground">“{answer.question}”</p>
      <h2 className="mb-3 text-[19px] font-semibold tracking-[-0.4px]">{answer.title}</h2>

      {answer.facts.length > 0 && (
        <div className="mb-3">
          <div className="eyebrow mb-1.5">Hechos respaldados por documentos</div>
          <ul className="list-disc space-y-1 pl-5 text-[13px] leading-relaxed text-secondary-foreground">
            {answer.facts.map((f) => <li key={f}>{f}</li>)}
          </ul>
        </div>
      )}
      {answer.interpretation && (
        <div className="rounded-xl bg-secondary px-4 py-3">
          <div className="eyebrow mb-1">Interpretación · no es una cita</div>
          <p className="text-[13px] leading-relaxed text-secondary-foreground">{answer.interpretation}</p>
        </div>
      )}

      {answer.evidence.length > 0 && (
        <>
          <div className="mb-2.5 mt-6 flex items-center justify-between text-[13px]">
            <strong>Fragmentos que sustentan la respuesta</strong>
            <span className="text-[10px] text-muted-foreground">{answer.evidence.length} fuentes</span>
          </div>
          {answer.evidence.map((e, i) => (
            <div key={i} className="mt-2.5 rounded-[15px] border border-border bg-card p-4">
              <div className="mb-2.5 flex flex-wrap items-center gap-2">
                <span className="doc-code">{e.code}</span>
                <strong className="text-[12px]">{e.title}</strong>
                <Pill>{e.version}</Pill>
                {answer.source === "demo" && <Pill tone="amber">Fragmento ficticio</Pill>}
              </div>
              <blockquote className="rounded-r-[10px] border-l-[3px] border-primary bg-quote px-3.5 py-3 text-[12px] leading-[1.75] text-secondary-foreground">
                <Highlighted text={e.quote} />
              </blockquote>
              <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 text-[10px] text-muted-foreground">
                <span>
                  Sección: {e.section ?? "no disponible"} · Página: {e.page ?? "no disponible"} — {e.why}
                </span>
                <Link to="/biblioteca/$code" params={{ code: e.code }} className="text-foreground underline">
                  Ver ficha documental
                </Link>
              </div>
            </div>
          ))}
        </>
      )}

      {answer.warnings.map((w) => (
        <div key={w} className="mt-4 rounded-xl bg-warning-soft px-3.5 py-3 text-[12px] leading-relaxed text-warning">⚠ {w}</div>
      ))}
      <div className="mt-4 border-t border-border pt-3 text-[11px] text-muted-foreground">
        Trazabilidad: consulta → recuperación de fragmentos → evaluación de vigencia → respuesta con evidencia vinculada a la versión documental.
      </div>
    </article>
  );
}
