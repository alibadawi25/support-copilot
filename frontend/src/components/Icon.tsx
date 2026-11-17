import type { ReactNode } from "react";

// Inline SVG line icons (24px grid). Inline because the app must work with the network off.
const PATHS = {
  alert: <path d="M12 4 2.5 20h19zM12 10v4m0 3h.01" />,
  book: <path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H19v15H7.5A2.5 2.5 0 0 0 5 20.5zM5 20.5A2.5 2.5 0 0 1 7.5 18H19v3H7.5" />,
  check: <path d="m5 12.5 4.5 4.5L19 7" />,
  copy: <path d="M9 9h11v11H9zM5 15V4h11" />,
  hash: <path d="M5 9h14M5 15h14M10 4 8 20m8-16-2 16" />,
  inbox: <path d="M3 13h5l1.5 3h5l1.5-3h5M5.5 5h13L21 13v6H3v-6z" />,
  info: <path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zm0-10v5m0-8h.01" />,
  layers: <path d="m12 3 9 5-9 5-9-5zm-9 10 9 5 9-5" />,
  list: <path d="M9 6h11M9 12h11M9 18h7M4.5 6h.01M4.5 12h.01M4.5 18h.01" />,
  pen: <path d="M4 20h4L19 9l-4-4L4 16zm10-14 4 4" />,
  play: <path d="M7 5v14l11-7z" />,
  search: <path d="M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zm9 2-4-4" />,
  shield: <path d="M12 3 4 6v6c0 4.5 3.4 7.9 8 9 4.6-1.1 8-4.5 8-9V6zm-3.5 9 2.5 2.5 4.5-5" />,
  ticket: <path d="M4 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v2.5a2.5 2.5 0 0 0 0 5V17a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2.5a2.5 2.5 0 0 0 0-5zm10-2v14" />,
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof PATHS;

/** Decorative icon: always next to visible text, so hidden from screen readers. */
export function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  return (
    <svg
      aria-hidden="true"
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {PATHS[name]}
    </svg>
  );
}
