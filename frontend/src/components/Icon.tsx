const PATHS = {
  upload: "M12 16V5m0 0L8 9m4-4 4 4M5 19h14",
  trash: "M5 7h14M10 11v5m4-5v5M7 7l1 12h8l1-12M9 7V4h6v3",
  copy: "M9 9h10v11H9zM5 15H4V4h11v1",
  check: "M5 12.5l4.5 4.5L19 7.5",
  chevron: "M9 6l6 6-6 6",
  file: "M7 3h7l5 5v13H7zM14 3v5h5",
  refresh: "M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
