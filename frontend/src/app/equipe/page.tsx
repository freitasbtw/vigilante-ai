import Image from "next/image";
import Link from "next/link";
import { ArrowLeft, GraduationCap, Users2 } from "lucide-react";
import { MarketingShell } from "@/components/MarketingShell";

const FIAP_LOGO = "https://upload.wikimedia.org/wikipedia/commons/d/d4/Fiap-logo-novo.jpg";

const TEAM = [
  { name: "Felipe Neves Cavalcanti", rm: "551619" },
  { name: "Mateus Vicente", rm: "550521" },
  { name: "Gabriel Da Silva Freitas", rm: "551195" },
  { name: "Murilo Alves de Moura", rm: "98220" },
  { name: "Roberto Felix de Araujo Guedes", rm: "99976" },
];

export default function TeamPage() {
  return (
    <MarketingShell>
      <section className="border-b border-border">
        <div className="mx-auto max-w-7xl px-6 py-16 lg:py-20">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-text-muted transition hover:text-text"
          >
            <ArrowLeft size={14} strokeWidth={2.2} />
            Voltar ao início
          </Link>

          <div className="mt-8 flex items-center gap-4">
            <div className="rounded-md border border-border bg-bg-elevated px-3 py-2">
              <Image src={FIAP_LOGO} alt="Logo FIAP" width={96} height={32} className="h-7 w-auto object-contain" />
            </div>
            <span className="eyebrow">Equipe</span>
          </div>

          <h1 className="mt-6 text-balance text-4xl font-semibold leading-tight tracking-tight text-text sm:text-5xl">
            Time responsável pelo Vigilante.AI.
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-relaxed text-text-muted sm:text-lg">
            Alunos da FIAP responsáveis pela concepção, modelagem de negócio e desenvolvimento técnico da plataforma de
            monitoramento com visão computacional aplicada à segurança operacional.
          </p>
        </div>
      </section>

      <section>
        <div className="mx-auto max-w-7xl px-6 py-16 lg:py-20">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {TEAM.map(({ name, rm }) => (
              <article key={rm} className="card card-hover p-6">
                <div className="flex items-center justify-between">
                  <span className="grid h-10 w-10 place-items-center rounded-md bg-bg-sunken text-text">
                    <Users2 size={18} strokeWidth={1.8} />
                  </span>
                  <span className="badge badge-neutral mono-num">RM {rm}</span>
                </div>
                <h2 className="mt-5 text-lg font-semibold tracking-tight text-text">{name}</h2>
                <div className="mt-4 flex items-center gap-2 text-sm text-text-muted">
                  <GraduationCap size={14} strokeWidth={1.8} />
                  <span>Aluno FIAP — Startup One</span>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>
    </MarketingShell>
  );
}
