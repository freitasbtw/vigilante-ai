import Image, { type StaticImageData } from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  BrainCircuit,
  Gauge,
  ShieldAlert,
  ShieldCheck,
  Square,
  Video,
  type LucideIcon,
} from "lucide-react";

import { MarketingShell } from "@/components/MarketingShell";
import dashboardImage from "../assets/Nano_Banana_2_Premium_3D_isometric_render_of_a_sleek__bezel_less_computer_monitor_floating_in_a_dark_4.png";
import ppeImage from "../assets/Nano_Banana_2_Cinematic_wide_shot_of_a_modern_industrial_construction_site_at_dusk__volumetric_light_2.png";
import performanceImage from "../assets/Nano_Banana_2_Macro_photography_of_a_futuristic_CPU_chip_mounted_on_a_sleek_dark_circuit_board__Neon_2.png";
import heroImage from "../assets/Nano_Banana_2_Extreme_close_up_portrait_of_a_factory_worker_s_face_and_shoulders__wearing_a_yellow_h_1.png";
import smartLogicImage from "../assets/Nano_Banana_2_A_split_screen_composition_illustrating_a_safety_monitoring_comparison__Left_side__A_w_1.png";

type Showcase = {
  eyebrow: string;
  title: string;
  description: string;
  highlights: string[];
  image: StaticImageData;
  alt: string;
  icon: LucideIcon;
  reverse?: boolean;
};

const SHOWCASES: Showcase[] = [
  {
    eyebrow: "Detecção de EPI",
    title: "Reconhecimento focado no operador em campo",
    description:
      "A leitura visual identifica capacete e colete diretamente sobre o trabalhador, reduzindo zonas cinzentas e acelerando a resposta da equipe de segurança.",
    highlights: [
      "Detecção sobre o operador, não sobre o ambiente",
      "Configuração por área operacional",
      "Sinalização imediata da ausência do EPI",
    ],
    image: ppeImage,
    alt: "Operador industrial usando EPI em ambiente de fábrica.",
    icon: ShieldCheck,
  },
  {
    eyebrow: "Lógica de Compliance",
    title: "Separa conformidade real de risco real",
    description:
      "A camada de regras combina detecção e contexto da cena para distinguir um operador conforme de uma situação que exige alerta imediato.",
    highlights: [
      "Leitura de múltiplos objetos na mesma cena",
      "Regras orientadas por tipo de operação",
      "Menos ruído, mais prioridade real",
    ],
    image: smartLogicImage,
    alt: "Comparação entre cena segura e cena com violação.",
    icon: BrainCircuit,
    reverse: true,
  },
  {
    eyebrow: "Dashboard",
    title: "Visão executiva clara para acompanhar conformidade",
    description:
      "Volume de violações, histórico de sessão e indicadores de adesão consolidados para que supervisão e gestão enxerguem tendência, risco e oportunidade de ajuste.",
    highlights: [
      "Métricas críticas em leitura rápida",
      "Histórico para auditoria e análise",
      "Base visual consistente entre operação e gestão",
    ],
    image: dashboardImage,
    alt: "Renderização de monitor exibindo a interface do painel de acompanhamento.",
    icon: BarChart3,
  },
  {
    eyebrow: "Performance",
    title: "Inferência otimizada para operar em tempo real",
    description:
      "A arquitetura mantém resposta baixa e processamento contínuo, sustentando monitoramento ao vivo sem transformar a segurança em gargalo operacional.",
    highlights: [
      "Pipeline pronto para baixa latência",
      "Análise contínua sustentável",
      "Base técnica preparada para evolução do modelo",
    ],
    image: performanceImage,
    alt: "Chip de processamento em close-up.",
    icon: Gauge,
    reverse: true,
  },
];

const FEATURES = [
  {
    icon: Video,
    title: "Monitoramento em tempo real",
    description:
      "Processamento de feeds RTSP simultâneos para acompanhar operadores e equipamentos sem depender de observação manual contínua.",
  },
  {
    icon: ShieldAlert,
    title: "Alertas críticos priorizados",
    description:
      "Incidentes de conformidade ganham prioridade visual imediata para reduzir tempo de reação e aumentar rastreabilidade da ocorrência.",
  },
  {
    icon: BarChart3,
    title: "Análise de dados consolidada",
    description:
      "Histórico, agregação e leitura executiva para orientar ajustes operacionais com base em dado, não em intuição.",
  },
];

export default function LandingPage() {
  return (
    <MarketingShell>
      {/* Hero */}
      <section className="relative border-b border-border">
        <div className="mx-auto grid max-w-7xl gap-12 px-6 py-20 lg:grid-cols-[1.1fr_0.9fr] lg:items-center lg:py-28">
          <div className="space-y-8">
            <div className="inline-flex items-center gap-2 rounded-full border border-border bg-bg-elevated px-3 py-1.5">
              <span className="grid h-3.5 w-3.5 place-items-center">
                <Square size={10} strokeWidth={2.4} className="text-text" />
              </span>
              <span className="text-xs font-medium tracking-wide text-text-muted">
                Visão computacional para segurança industrial
              </span>
            </div>

            <h1 className="text-balance text-5xl font-semibold leading-[1.05] tracking-tight text-text sm:text-6xl">
              Vigilância inteligente para sua operação.
            </h1>

            <p className="max-w-xl text-lg leading-relaxed text-text-muted">
              O Vigilante.AI combina visão computacional, regras operacionais e análise em tempo real para detectar
              ausência de EPIs e transformar incidentes potenciais em ação imediata.
            </p>

            <div className="flex flex-wrap items-center gap-3">
              <Link href="/login" className="btn-primary px-6 py-3 text-sm">
                Acessar plataforma
                <ArrowRight size={16} strokeWidth={2.2} />
              </Link>
              <Link href="/equipe" className="btn-secondary px-6 py-3 text-sm">
                Conhecer a equipe
              </Link>
            </div>

            <dl className="grid gap-6 border-t border-border pt-8 sm:grid-cols-3">
              {[
                ["Cobertura", "EPIs críticos", "Capacete e colete refletivo, regras adaptáveis."],
                ["Resposta", "Alerta imediato", "Sinal visual no exato momento da violação."],
                ["Leitura", "Visão consolidada", "Monitor e dashboard na mesma narrativa."],
              ].map(([eyebrow, title, desc]) => (
                <div key={eyebrow}>
                  <dt className="eyebrow">{eyebrow}</dt>
                  <dd className="mt-2">
                    <div className="text-base font-semibold text-text">{title}</div>
                    <div className="mt-1 text-sm leading-relaxed text-text-muted">{desc}</div>
                  </dd>
                </div>
              ))}
            </dl>
          </div>

          <div className="relative aspect-[5/4] overflow-hidden rounded-xl border border-border shadow-lg">
            <Image
              src={heroImage}
              alt="Operador industrial usando capacete amarelo em close."
              fill
              priority
              className="object-cover"
              sizes="(min-width: 1024px) 42vw, 100vw"
            />
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="border-b border-border">
        <div className="mx-auto max-w-7xl px-6 py-20">
          <div className="mb-12 max-w-2xl">
            <p className="eyebrow">Plataforma</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-text sm:text-4xl">
              Três pilares para fechar o ciclo da segurança.
            </h2>
          </div>
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(({ icon: Icon, title, description }) => (
              <div key={title} className="card card-hover p-6">
                <div className="grid h-10 w-10 place-items-center rounded-md bg-bg-sunken text-text">
                  <Icon size={20} strokeWidth={1.8} />
                </div>
                <h3 className="mt-5 text-lg font-semibold text-text">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-text-muted">{description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Showcases */}
      {SHOWCASES.map(({ eyebrow, title, description, highlights, image, alt, icon: Icon, reverse }) => (
        <section key={eyebrow} className="border-b border-border">
          <div className="mx-auto grid max-w-7xl gap-12 px-6 py-20 lg:grid-cols-2 lg:items-center">
            <div className={reverse ? "lg:order-2" : ""}>
              <div className="inline-flex items-center gap-2.5">
                <span className="grid h-8 w-8 place-items-center rounded-md bg-bg-sunken text-text">
                  <Icon size={16} strokeWidth={1.8} />
                </span>
                <span className="eyebrow">{eyebrow}</span>
              </div>
              <h2 className="mt-5 max-w-xl text-3xl font-semibold tracking-tight text-text sm:text-4xl">
                {title}
              </h2>
              <p className="mt-4 max-w-xl text-base leading-relaxed text-text-muted">{description}</p>
              <ul className="mt-6 space-y-3">
                {highlights.map((h) => (
                  <li key={h} className="flex items-start gap-2.5">
                    <span className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-text" />
                    <span className="text-sm leading-relaxed text-text-muted">{h}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className={reverse ? "lg:order-1" : ""}>
              <div className="relative aspect-[16/10] overflow-hidden rounded-xl border border-border shadow-md">
                <Image src={image} alt={alt} fill className="object-cover" sizes="(min-width: 1024px) 42vw, 100vw" />
              </div>
            </div>
          </div>
        </section>
      ))}

      {/* Equipe CTA */}
      <section>
        <div className="mx-auto max-w-7xl px-6 py-20">
          <div className="card overflow-hidden">
            <div className="grid gap-8 p-10 sm:grid-cols-[1.4fr_0.6fr] sm:items-end lg:p-12">
              <div className="space-y-4">
                <p className="eyebrow">Equipe</p>
                <h2 className="text-3xl font-semibold tracking-tight text-text sm:text-4xl">
                  Conheça quem construiu o Vigilante.AI.
                </h2>
                <p className="max-w-2xl text-base leading-relaxed text-text-muted">
                  A equipe responsável pela concepção, produto e execução técnica da plataforma tem uma página dedicada
                  com integrantes, papéis e contexto.
                </p>
              </div>
              <Link href="/equipe" className="btn-primary justify-self-start px-6 py-3 text-sm sm:justify-self-end">
                Ver equipe
                <ArrowRight size={16} strokeWidth={2.2} />
              </Link>
            </div>
          </div>
        </div>
      </section>
    </MarketingShell>
  );
}
