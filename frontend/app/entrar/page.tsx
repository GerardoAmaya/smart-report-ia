"use client";

/**
 * Entrar al tablero.
 *
 * Dos formas, y la diferencia se dice en voz alta: Google para quien trabaja
 * aqui, contraseña para quien viene a mirar. Esconder que el usuario de prueba
 * es limitado haria que alguien se topara con un 403 sin saber por que.
 */
import { motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Eye } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/api";
import { MarcaGoogle, MarcaTelegram } from "@/componentes/Marcas-svg";

export default function Entrar() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  async function entrarDePrueba(e: React.FormEvent) {
    e.preventDefault();
    setEnviando(true);
    setError(null);
    try {
      await api.entrarDePrueba(password);
      router.push("/");
      router.refresh();
    } catch {
      setError("Esa contraseña no es. Revisala y probá de nuevo.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: "easeOut" }}
        className="w-full max-w-sm"
      >
        <Card>
          <CardHeader>
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
              Smart Report
            </p>
            <CardTitle className="text-xl">Entrar al tablero</CardTitle>
            <CardDescription>
              Reportes ciudadanos de hallazgos en la vía pública de El Salvador.
            </CardDescription>
          </CardHeader>

          <CardContent className="space-y-5">
            <Button asChild variant="outline" className="w-full">
              <a href={api.urlEntrarConGoogle()}>
                <MarcaGoogle className="size-4" />
                Entrar con Google
              </a>
            </Button>
            <p className="-mt-3 text-xs text-muted-foreground">
              Solo cuentas autorizadas. Tener cuenta de Google no da acceso.
            </p>

            <div className="flex items-center gap-3">
              <Separator className="flex-1" />
              <span className="text-xs uppercase tracking-wider text-muted-foreground">
                o mirar
              </span>
              <Separator className="flex-1" />
            </div>

            <form onSubmit={entrarDePrueba} className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="password">Usuario de prueba</Label>
                <p className="text-xs text-muted-foreground">
                  Puede asignar, agrupar, separar y cerrar. No puede borrar.
                </p>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  placeholder="Contraseña"
                />
              </div>
              <Button type="submit" disabled={enviando || !password} className="w-full">
                <Eye className="size-4" />
                {enviando ? "Entrando…" : "Entrar a mirar"}
              </Button>
            </form>

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </CardContent>
        </Card>

        <p className="mt-4 flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
          <MarcaTelegram className="size-3.5" />
          Los reportes entran por un bot de Telegram
        </p>
      </motion.div>
    </main>
  );
}
