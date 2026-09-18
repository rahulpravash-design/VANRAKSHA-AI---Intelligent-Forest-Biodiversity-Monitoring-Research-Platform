/** A tiny inline-SVG icon set — no icon package dependency for ~10 glyphs. */
export function NavIcon({ name, className }: { name: string; className?: string }) {
  const common = { className, fill: "none", stroke: "currentColor", strokeWidth: 1.8, viewBox: "0 0 24 24" };
  switch (name) {
    case "layout":
      return (
        <svg {...common}><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></svg>
      );
    case "camera":
      return (
        <svg {...common}><path d="M4 8h3l2-2h6l2 2h3a1 1 0 011 1v9a1 1 0 01-1 1H4a1 1 0 01-1-1V9a1 1 0 011-1z" /><circle cx="12" cy="13" r="3.5" /></svg>
      );
    case "leaf":
      return (
        <svg {...common}><path d="M20 4c-8 0-16 4-16 13 0 1.5.3 2.7.8 3.6M20 4c0 8-4 16-13 16-1.5 0-2.7-.3-3.6-.8M20 4c-4 4-9 6-13 15.2" /></svg>
      );
    case "map":
      return (
        <svg {...common}><path d="M9 4l-6 2v14l6-2 6 2 6-2V4l-6 2-6-2z" /><path d="M9 4v14M15 6v14" /></svg>
      );
    case "chart":
      return (
        <svg {...common}><path d="M4 20V10M11 20V4M18 20v-7" /><path d="M2 20h20" /></svg>
      );
    case "check":
      return (
        <svg {...common}><circle cx="12" cy="12" r="9" /><path d="M8 12.5l2.5 2.5L16 9" /></svg>
      );
    case "bell":
      return (
        <svg {...common}><path d="M6 10a6 6 0 1112 0c0 4 1.5 5.5 1.5 5.5H4.5S6 14 6 10z" /><path d="M9.5 18.5a2.5 2.5 0 005 0" /></svg>
      );
    case "radio":
      return (
        <svg {...common}><circle cx="12" cy="12" r="2.5" /><path d="M7 9a7 7 0 000 6M17 9a7 7 0 010 6M4 5a12 12 0 000 14M20 5a12 12 0 010 14" /></svg>
      );
    case "flask":
      return (
        <svg {...common}><path d="M9 3h6M10 3v6l-5.5 9.5A1.5 1.5 0 005.8 21h12.4a1.5 1.5 0 001.3-2.5L14 9V3" /></svg>
      );
    case "users":
      return (
        <svg {...common}><circle cx="9" cy="8" r="3" /><path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5" /><circle cx="17.5" cy="9" r="2.5" /><path d="M15.8 14.3c2.4.4 4.2 2.2 4.2 5.7" /></svg>
      );
    case "logout":
      return (
        <svg {...common}><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" /><path d="M16 17l5-5-5-5M21 12H9" /></svg>
      );
    case "settings":
      return (
        <svg {...common}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 00.3 1.9l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.9-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1-1.6 1.7 1.7 0 00-1.9.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.9 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1 1.7 1.7 0 00-.3-1.9l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.9.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.9-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.9V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z" /></svg>
      );
    default:
      return <svg {...common}><circle cx="12" cy="12" r="9" /></svg>;
  }
}
