"use client";

import { useCallback, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Check = {
  ok: boolean;
  detail: string | null;
  version?: string | null;
  applied_revision?: string | null;
  expected_revision?: string | null;
  cached?: boolean;
};

type Health = {
  status: "ok" | "degraded";
  environment: string;
  schema_revision: string | null;
  checks: Record<string, Check>;
  issues: string[];
};

const LABELS: Record<string, string> = {
  postgis: "PostGIS",
  schema: "Esquema",
  model: "Modelo",
};

export default function Page() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/health`, { cache: "no-store" });
      setHealth((await response.json()) as Health);
      setError(null);
    } catch {
      // La API caida no es lo mismo que la API degradada, y se dice distinto.
      setHealth(null);
      setError(`Sin respuesta de ${API_URL}`);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 10_000);
    return () => clearInterval(timer);
  }, [load]);

  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <p className="text-xs uppercase tracking-[0.2em] text-gris">Fase 0 &middot; Esqueleto</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">Smart Report</h1>
      <p className="mt-2 text-sm text-gris">
        Estado real del servicio, leido de <code>/health</code> cada diez segundos.
      </p>

      <section className="mt-10 border border-tinta/10 bg-white">
        <header className="flex items-baseline justify-between border-b border-tinta/10 px-5 py-4">
          <span className="text-sm font-medium">Servicio</span>
          <StatusText status={error ? "down" : health?.status} />
        </header>

        {error && <p className="px-5 py-4 text-sm text-rojo">{error}</p>}

        {health && (
          <dl className="divide-y divide-tinta/10">
            {Object.entries(health.checks).map(([name, check]) => (
              <div key={name} className="flex items-baseline justify-between gap-4 px-5 py-4">
                <dt className="text-sm">{LABELS[name] ?? name}</dt>
                <dd className="text-right text-sm">
                  <span className={check.ok ? "text-verde" : "text-rojo"}>
                    {check.ok ? "en linea" : "caido"}
                  </span>
                  <span className="ml-3 text-gris">{describe(name, check)}</span>
                </dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      {health && (
        <p className="mt-4 text-xs text-gris">
          entorno {health.environment} &middot; esquema {health.schema_revision ?? "sin migrar"}
        </p>
      )}
    </main>
  );
}

function StatusText({ status }: { status?: "ok" | "degraded" | "down" }) {
  if (status === "ok") return <span className="text-sm text-verde">operativo</span>;
  if (status === "degraded") return <span className="text-sm text-rojo">degradado</span>;
  if (status === "down") return <span className="text-sm text-rojo">sin respuesta</span>;
  return <span className="text-sm text-gris">consultando</span>;
}

// El detalle del fallo se muestra entero: un estado rojo sin motivo obliga a
// ir a los logs, que es justo lo que este panel deberia ahorrar.
function describe(name: string, check: Check): string {
  if (!check.ok) return check.detail ?? "";
  if (name === "postgis") return check.version ?? "";
  if (name === "schema") return check.applied_revision ?? "";
  if (name === "model") return check.cached ? "cacheado" : "recien sondeado";
  return "";
}
