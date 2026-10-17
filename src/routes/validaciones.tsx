import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Empty, Notice, PageHead, Panel, Pill } from "@/components/hz/ui";
import { services } from "@/services";
import { fmtDate } from "@/lib/domain/validity";
import type { FindingKind } from "@/lib/domain/types";

export const Route = createFileRoute("/validaciones")({
  head: () => ({
    meta: [
      { title: "Validaciones · Horizonte Intelligence" },
      { name: "description", content: "Revisa vigencia, inconsistencias y posibles conflictos entre documentos." },
      { property: "og:title", content: "Validaciones · Horizonte Intelligence" },
      { property: "og:description", content: "Cola de revisión documental que requiere decisión de un responsable." },
    ],
  }),
  component: Validaciones,
});

const kindLabel: Record<FindingKind, string> = {
  vencido: "Vencido / reemplazado",
  contradiccion: "Posible contradicción",
  version: "Versión inconsistente",
  revision: "Requiere revisión",
  metadatos: "Metadatos incompletos",
};

function Validaciones() {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({ queryKey: ["validations"], queryFn: services.runValidations });
  return (
    <section>
      <PageHead eyebrow="Gobierno documental" title="Centro de validaciones" subtitle="Revisiones que requieren decisión de un responsable autorizado." actions={<button onClick={() => refetch()} className="rounded-full border border-border bg-card px-4 py-2.5 text-[12px] hover:bg-accent">{isFetching ? "Revisando…" : "↻ Volver a revisar"}</button>} />
      <Notice title="La validación requiere criterio humano">
        Estos hallazgos provienen de reglas locales aplicadas a metadatos de prueba al {fmtDate(services.referenceDate())}. No son verificaciones institucionales ejecutadas ni aprueban o reemplazan documentos. La detección de contradicciones en el contenido se habilitará con el procesamiento documental.
      </Notice>
      <Panel className="overflow-hidden">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-[14px] font-bold">Cola de revisión</h2>
          {data && <Pill tone="amber">{data.filter((f) => f.reviewStatus !== "resuelto").length} pendientes</Pill>}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead className="bg-secondary text-left text-[10px] font-bold uppercase tracking-[0.4px] text-muted-foreground">
              <tr>{["Hallazgo", "Documentos implicados", "Motivo de la alerta", "Severidad", "Estado"].map((h) => <th key={h} className="px-4 py-3">{h}</th>)}</tr>
            </thead>
            <tbody>
              {isLoading && <tr><td colSpan={5}><Empty>Ejecutando reglas…</Empty></td></tr>}
              {isError && <tr><td colSpan={5}><Empty>No se pudieron ejecutar las validaciones.</Empty></td></tr>}
              {data?.length === 0 && <tr><td colSpan={5}><Empty>No se detectaron hallazgos con las reglas disponibles.</Empty></td></tr>}
              {data?.map((f) => (
                <tr key={f.id} className="border-t border-border align-top">
                  <td className="px-4 py-3"><div className="text-[10px] font-bold uppercase text-muted-foreground">{kindLabel[f.kind]}</div><div className="font-semibold">{f.title}</div><div className="mt-0.5 max-w-[360px] text-[11px] text-muted-foreground">{f.description}</div></td>
                  <td className="px-4 py-3"><div className="flex flex-wrap gap-1.5">{f.documents.map((c) => <Link key={c} to="/biblioteca/$code" params={{ code: c }} className="doc-code underline">{c}</Link>)}</div></td>
                  <td className="max-w-[280px] px-4 py-3 text-muted-foreground">{f.reason}</td>
                  <td className="px-4 py-3"><Pill tone={f.severity === "alta" ? "red" : f.severity === "media" ? "amber" : "gray"}>{f.severity}</Pill></td>
                  <td className="px-4 py-3"><Pill>{f.reviewStatus}</Pill><div className="mt-1 text-[10px] text-muted-foreground">{f.origin}</div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </section>
  );
}
