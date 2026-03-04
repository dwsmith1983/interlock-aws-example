"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useOverview } from "@/lib/api";
import { CDR_PIPELINES, SEQ_PIPELINES } from "@/lib/pipelines";
import { severityOf, SEVERITY_COLORS } from "@/lib/events";

const NAV_ITEMS = [
  { href: "/", label: "Overview", icon: "M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0h4" },
  { href: "/pipelines", label: "Pipelines", icon: "M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" },
  { href: "/metrics", label: "Metrics", icon: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" },
];

const SEVERITY_BG: Record<string, string> = {
  critical: "bg-[#f87171]",
  warning: "bg-[#fbbf24]",
  success: "bg-[#34d399]",
  info: "bg-[#38bdf8]",
};

function statusDot(eventType: string | undefined): string {
  if (!eventType) return "bg-slate-500";
  return SEVERITY_BG[severityOf(eventType)] ?? "bg-slate-500";
}

export default function Sidebar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const { data } = useOverview();
  const pipelines = data?.pipelines ?? {};

  const sidebarContent = (
    <>
      {/* Logo */}
      <div className="px-4 py-5">
        <Link href="/" className="flex items-center gap-2">
          <svg className="w-6 h-6 text-[#34d399]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          <span className="text-lg font-bold tracking-tight text-white">Interlock</span>
        </Link>
      </div>

      {/* Nav items */}
      <nav className="mt-2 px-2 space-y-1">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setMobileOpen(false)}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                active
                  ? "bg-white/10 text-white border-l-2 border-[#34d399]"
                  : "text-slate-400 hover:text-white hover:bg-white/5"
              }`}
            >
              <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d={item.icon} />
              </svg>
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Pipeline quick-links */}
      <div className="mt-6 px-4">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">CDR</p>
        {CDR_PIPELINES.map((id) => (
          <Link
            key={id}
            href={`/pipelines?pipeline=${id}`}
            onClick={() => setMobileOpen(false)}
            className="flex items-center gap-2 px-2 py-1.5 text-xs text-slate-400 hover:text-white rounded transition-colors"
          >
            <span className={`w-2 h-2 rounded-full ${statusDot(pipelines[id]?.lastEvent?.eventType)}`} />
            {id}
          </Link>
        ))}

        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mt-3 mb-2">SEQ</p>
        {SEQ_PIPELINES.map((id) => (
          <Link
            key={id}
            href={`/pipelines?pipeline=${id}`}
            onClick={() => setMobileOpen(false)}
            className="flex items-center gap-2 px-2 py-1.5 text-xs text-slate-400 hover:text-white rounded transition-colors"
          >
            <span className={`w-2 h-2 rounded-full ${statusDot(pipelines[id]?.lastEvent?.eventType)}`} />
            {id}
          </Link>
        ))}
      </div>

      {/* Live indicator */}
      <div className="mt-auto px-4 py-4">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#34d399] opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-[#34d399]"></span>
          </span>
          Live — 30s refresh
        </div>
      </div>
    </>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex lg:flex-col lg:w-60 lg:fixed lg:inset-y-0 glass border-r border-white/10 z-30">
        {sidebarContent}
      </aside>

      {/* Mobile hamburger */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-40 glass border-b border-white/10 px-4 py-3 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <svg className="w-5 h-5 text-[#34d399]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          <span className="font-bold text-white">Interlock</span>
        </Link>
        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-label="Toggle navigation menu"
          aria-expanded={mobileOpen}
          className="p-2 text-slate-400 hover:text-white"
        >
          <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            {mobileOpen ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            )}
          </svg>
        </button>
      </div>

      {/* Mobile slide-out */}
      {mobileOpen && (
        <>
          <div className="lg:hidden fixed inset-0 bg-black/50 z-40" onClick={() => setMobileOpen(false)} />
          <aside className="lg:hidden fixed inset-y-0 left-0 w-60 z-50 glass flex flex-col border-r border-white/10">
            {sidebarContent}
          </aside>
        </>
      )}
    </>
  );
}
