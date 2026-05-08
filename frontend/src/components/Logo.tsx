interface LogoProps {
  size?: number;
  variant?: "dark" | "light";
}

/** Geometric viewfinder mark. Sharp corners, monospace dot center. */
export function LogoMark({ size = 24, variant = "dark" }: LogoProps) {
  const stroke = variant === "dark" ? "#ffffff" : "#111111";
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <rect x="2" y="2" width="20" height="20" rx="3" stroke={stroke} strokeWidth="2" />
      <rect x="9" y="9" width="6" height="6" fill={stroke} />
    </svg>
  );
}

interface LogoWordmarkProps {
  size?: number;
  variant?: "dark" | "light";
  className?: string;
}

export function Logo({ size = 28, variant = "dark", className = "" }: LogoWordmarkProps) {
  const bg = variant === "dark" ? "bg-text" : "bg-white";
  const inner = variant === "dark" ? "light" : "dark";
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <span className={`grid ${bg} place-items-center rounded-[6px]`} style={{ width: size, height: size }}>
        <LogoMark size={Math.round(size * 0.6)} variant={inner} />
      </span>
      <span className="text-[15px] font-semibold tracking-tight">Vigilante.AI</span>
    </span>
  );
}
