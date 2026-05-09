"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { login, register } from "@/lib/api";

type Mode = "login" | "register";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantName, setTenantName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (searchParams.get("mode") === "register") setMode("register");
  }, [searchParams]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, tenantName || "Default tenant");
      }
      router.push("/cameras");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <header className="flex h-16 items-center justify-between border-b border-border bg-bg-elevated px-6">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-[18px] font-semibold tracking-tight text-text"
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo-black.webp" alt="Vigilante.AI" width={28} height={29} className="block" />
          <span>Vigilante<span style={{ color: "#f5a623" }}>.AI</span></span>
        </Link>
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-text-muted transition hover:text-text"
        >
          <ArrowLeft size={14} strokeWidth={2.2} />
          Voltar
        </Link>
      </header>

      <main className="flex flex-1 items-center justify-center p-6">
        <div className="w-full max-w-sm space-y-6">
          <div className="text-center">
            <h1 className="text-2xl font-semibold tracking-tight text-text">
              {mode === "login" ? "Entrar na plataforma" : "Criar nova conta"}
            </h1>
            <p className="mt-1.5 text-sm text-text-muted">
              {mode === "login"
                ? "Acesse o painel Vigilante.AI"
                : "Cadastre seu tenant e usuário admin"}
            </p>
          </div>

          <form onSubmit={onSubmit} className="card space-y-4 p-6">
            {mode === "register" && (
              <div className="space-y-1.5">
                <label className="label">Nome do tenant</label>
                <input
                  required
                  type="text"
                  value={tenantName}
                  onChange={(e) => setTenantName(e.target.value)}
                  className="input"
                  placeholder="Construtora ABC"
                />
              </div>
            )}
            <div className="space-y-1.5">
              <label className="label">Email</label>
              <input
                required
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input"
                placeholder="seu@email.com"
              />
            </div>
            <div className="space-y-1.5">
              <label className="label">Senha</label>
              <input
                required
                type="password"
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input"
                placeholder="Mínimo 8 caracteres"
              />
            </div>

            {error && (
              <p className="rounded-md border border-danger/30 bg-danger-bg px-3 py-2 text-xs text-danger">
                {error}
              </p>
            )}

            <button type="submit" disabled={submitting} className="btn-primary w-full py-2.5 text-sm">
              {submitting ? "..." : mode === "login" ? "Entrar" : "Criar conta"}
            </button>

            <button
              type="button"
              onClick={() => setMode(mode === "login" ? "register" : "login")}
              className="w-full text-center text-xs text-text-muted underline-offset-2 hover:text-text hover:underline"
            >
              {mode === "login" ? "Não tem conta? Criar uma agora" : "Já tem conta? Entrar"}
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
