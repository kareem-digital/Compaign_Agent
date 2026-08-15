import type { PropsWithChildren } from "react";

import { cn } from "@/lib/utils";

/* Paths are lifted verbatim from the design frame, with its hardcoded strokes
 * swapped for `currentColor` so the theme drives them. Size comes from the
 * caller's class, never from width/height attributes. */

interface IconProps {
  className?: string;
}

function Line({
  className,
  strokeWidth = 1.7,
  children,
}: PropsWithChildren<IconProps & { strokeWidth?: number }>) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      className={className}
    >
      {children}
    </svg>
  );
}

/** Two-tone product mark. The dot deliberately overrides the inherited colour. */
export function BrandMark({ className }: IconProps) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      fill="none"
      className={cn("text-accent", className)}
    >
      <circle cx="11" cy="13" r="8.4" stroke="currentColor" strokeWidth={1.5} />
      <path
        d="M11 8.5l1.3 3.2L15.5 13l-3.2 1.3L11 17.5 9.7 14.3 6.5 13l3.2-1.3z"
        fill="currentColor"
      />
      <circle cx="20" cy="4.5" r="2" fill="currentColor" className="text-secondary" />
    </svg>
  );
}

export function Plus({ className }: IconProps) {
  return (
    <Line className={className}>
      <path d="M12 5v14M5 12h14" />
    </Line>
  );
}

export function Clock({ className }: IconProps) {
  return (
    <Line className={className}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.5V12l3 2" />
    </Line>
  );
}

export function Paperclip({ className }: IconProps) {
  return (
    <Line className={className}>
      <path d="M21 11l-8.5 8.5a4.6 4.6 0 01-6.5-6.5L14 4.5a3.2 3.2 0 014.5 4.5l-8 8a1.8 1.8 0 01-2.5-2.5l7-7" />
    </Line>
  );
}

export function Send({ className }: IconProps) {
  return (
    <Line className={className}>
      <path d="M21 3L10.5 13.5M21 3l-6.5 18-4-8-8-4z" />
    </Line>
  );
}

export function Info({ className }: IconProps) {
  return (
    <Line className={className} strokeWidth={1.6}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5M12 8h.01" />
    </Line>
  );
}

export function Upload({ className }: IconProps) {
  return (
    <Line className={className}>
      <path d="M12 16V4m0 0L8 8m4-4l4 4M4 18v2h16v-2" />
    </Line>
  );
}

export function PlayRect({ className }: IconProps) {
  return (
    <Line className={className}>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M10 9.5l5 2.5-5 2.5z" />
    </Line>
  );
}

export function DollarCircle({ className }: IconProps) {
  return (
    <Line className={className}>
      <circle cx="12" cy="12" r="9" />
      <path d="M14.5 9.5c-.6-.9-1.6-1.3-2.6-1.3-1.3 0-2.4.7-2.4 1.8s1.1 1.6 2.5 1.9c1.4.3 2.5.8 2.5 1.9s-1.1 1.8-2.5 1.8c-1.1 0-2.1-.4-2.7-1.3M12 6.3v11.4" />
    </Line>
  );
}

export function ChevronDown({ className }: IconProps) {
  return (
    <Line className={className} strokeWidth={2.2}>
      <path d="M6 9l6 6 6-6" />
    </Line>
  );
}

export function ChevronRight({ className }: IconProps) {
  return (
    <Line className={className} strokeWidth={2.2}>
      <path d="M9 6l6 6-6 6" />
    </Line>
  );
}

export function Lock({ className }: IconProps) {
  return (
    <Line className={className} strokeWidth={1.8}>
      <rect x="4" y="11" width="16" height="10" rx="2" />
      <path d="M8 11V8a4 4 0 018 0v3" />
    </Line>
  );
}

export function Check({ className }: IconProps) {
  return (
    <Line className={className} strokeWidth={2.2}>
      <path d="M20 6.5L9.5 17 4 11.5" />
    </Line>
  );
}

export function Expand({ className }: IconProps) {
  return (
    <Line className={className} strokeWidth={1.9}>
      <path d="M14 4h6v6M20 4l-7 7M10 20H4v-6M4 20l7-7" />
    </Line>
  );
}

export function TrendUp({ className }: IconProps) {
  return (
    <Line className={className} strokeWidth={2.6}>
      <path d="M4 19V7M4 19h16" />
      <path d="M6 16c3-6 7-8 12-8.5" />
    </Line>
  );
}

export function FileText({ className }: IconProps) {
  return (
    <Line className={className}>
      <path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8zM14 3v5h5M9 13h6M9 16.5h4" />
    </Line>
  );
}
