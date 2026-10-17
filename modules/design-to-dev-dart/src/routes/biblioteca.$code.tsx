import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Empty, PageHead, Panel, Pill } from "@/components/hz/ui";
import { services } from "@/services";
import { assessValidity, fmtDate } from "@/lib/domain/validity";
import type { Tone } from "@/lib/domain/types";

export const Route = createFileRoute("/biblioteca/$code")({
  head: ({ params }) => ({
    meta: [
      { title: `${params.code} · Ficha documental · Horizonte Intelligence` },
      { name: "description", content: `Metadatos, vigencia y versiones del documento ${params.code}.` },
      { property: "og:title", content: `${params.code} · Horizonte Intelligence` },
      { property: "og:description", content: "Ficha documental con historial de versiones y relaciones." },
    ],
  }),
  component: DocDetail,
});

function Info({ items }: { items: [string, string][] }) {
  return (
    <div className="grid grid-cols-2 gap-4 max-sm:grid-cols-1">
      {items.map(([l, v]) => (
        <div key={l}><div className="text-[10px] uppercase tracking-wide text-muted-foreground">{l}</div><div className="text-[12px] font-semibold">{v || "No registrado"}</div></div>
      ))}
    </div>
  );
}

function Card({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <Panel className="mb-4">
      <div className="border-b border-border px-5 py-4"><h2 className="text-[14px] font-bold">{title}</h2>{note && <p className="mt-1 text-[11px] text-muted-foreground">{note}</p>}</div>
      <div className="p-5">{children}</div>
    </Panel>
  );
}

function DocDetail() {
  const { code } = Route.useParams();
  const date = services.referenceDate();
  const { data: d, isLoading } = useQuery({ queryKey: ["document", code], queryFn: () => services.getDocument(code) });

  const back = <Link to="/biblioteca" className="mb-4 inline-block text-[12px] text-muted-foreground hover:text-foreground">← Volver a biblioteca</Link>;
  if (isLoading) return <>{back}<Empty>Cargando ficha…</Empty></>;
  if (!d) return <>{back}<Empty>No se encontró el documento {code}.</Empty></>;
  const a = assessValidity(d, date);

  return (
    <section>
      {back}
      <PageHead eyebrow="Ficha documental" title={d.title} subtitle="Metadatos, vigencia, historial de versiones y relaciones documentales." actions={d.isDemo ? <Pill tone="amber">Datos de prueba</Pill> : undefined} />
      <div className="grid grid-cols-[minmax(0,1.6fr)_minmax(280px,1fr)] gap-4 max-lg:grid-cols-1">
        <div>
          <Card title={`${d.code} · ${d.type}`}>
            <div className="mb-3 flex flex-wrap gap-2"><Pill tone={a.tone}>{a.label}</Pill><Pill>{d.area}</Pill></div>
            <p className="mb-5 text-[13px] leading-relaxed text-secondary-foreground">{d.description}</p>
            <Info items={[["Área responsable", d.area], ["Responsable documental", d.owner], ["Clasificación", d.classification], ["Última carga", fmtDate(d.uploaded)], ["Próxima revisión", /^\d{4}/.test(d.review) ? fmtDate(d.review) : d.review]]} />
          </Card>
          <Card title="Historial de versiones" note="La versión más reciente no necesariamente es la aplicable.">
            {d.versions.map((v) => {
              const applicable = a.version === v && !a.uncertain;
              const [label, tone]: [string, Tone] = v.status === "pending" ? ["Pendiente de validación", "amber"] : v.status === "replaced" ? ["Reemplazada", "gray"] : v.from && v.from > date ? ["Aprobada · vigencia futura", "blue"] : applicable ? ["Aplicable a la fecha", "green"] : ["Aprobada", "gray"];
              return (
                <div key={v.v} className={`mb-3 rounded-xl border p-4 ${applicable ? "border-primary" : "border-border"}`}>
                  <div className="flex flex-wrap items-center gap-2 text-[13px] font-bold">Versión {v.v} <Pill tone={tone}>{label}</Pill></div>
                  <div className="mt-1 text-[11px] text-muted-foreground">Vigencia desde: {fmtDate(v.from)} · Hasta: {fmtDate(v.until)}</div>
                  <div className="text-[11px] text-muted-foreground">Aprobación: {fmtDate(v.approved)}{v.by ? ` · ${v.by}` : ""}</div>
                  <div className="mt-1.5 text-[12px]">{v.note}</div>
                </div>
              );
            })}
          </Card>
          <Card title="Relaciones documentales" note="Relaciones declaradas entre documentos.">
            {d.relations.length ? d.relations.map((r) => (
              <div key={r.target} className="mb-3 border-b border-border pb-3 last:mb-0 last:border-0 last:pb-0">
                <div className="flex flex-wrap justify-between gap-2"><strong className="text-[12px]">{r.target}</strong><Pill tone={r.status === "confirmada" ? "green" : r.status === "no resuelta" ? "red" : "amber"}>{r.status}</Pill></div>
                <div className="mt-1 text-[12px] text-muted-foreground">{r.note}</div>
              </div>
            )) : <p className="text-[12px] text-muted-foreground">No hay relaciones documentales registradas.</p>}
          </Card>
        </div>
        <div>
          <Card title="Evaluación de vigencia" note={`Fecha de referencia: ${fmtDate(date)}`}>
            <Pill tone={a.tone}>{a.label}</Pill>
            <div className="my-3 text-[23px] font-extrabold">{a.version ? `v${a.version.v}${a.uncertain ? " · no confirmada" : ""}` : "No determinada"}</div>
            <div className={`rounded-xl px-3.5 py-3 text-[12px] leading-relaxed ${a.uncertain ? "bg-warning-soft text-warning" : "bg-success-soft text-success"}`}>{a.reason}</div>
            <p className="mt-3 text-[10px] text-muted-foreground">Regla: versión aprobada + fecha de vigencia compatible + sin validación pendiente. Jerarquía y derogaciones requieren revisión cuando no están registradas.</p>
          </Card>
          <Card title="Control y trazabilidad">
            <Info items={[["Código", d.code], ["Versiones registradas", String(d.versions.length)], ["Última actualización", fmtDate(d.uploaded)], ["Fuente de datos", d.isDemo ? "Datos de prueba" : "Biblioteca"]]} />
          </Card>
        </div>
      </div>
    </section>
  );
}
