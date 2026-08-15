import { useEffect, useState } from "react";
import type { InstallPromptEvent } from "../lib/types";

export function ScoreDial({ value, small = false }: { value: number; small?: boolean }) {
  return (
    <div
      className={`score-dial ${small ? "score-dial--small" : ""}`}
      style={{ "--score": `${Math.min(value, 100) * 3.6}deg` } as React.CSSProperties}
      aria-label={`匹配分 ${value}`}
    >
      <div><strong>{value.toFixed(0)}</strong><span>匹配</span></div>
    </div>
  );
}

export function Signal({ tone = "green" }: { tone?: "green" | "amber" | "red" }) {
  return <span className={`signal signal--${tone}`} aria-hidden="true" />;
}

export function DataFreshness({ timestamp, validUntil }: { timestamp?: string | null; validUntil?: string | null }) {
  if (!timestamp) return <span className="freshness freshness--unknown"><Signal tone="amber" /> 数据时间未知</span>;
  const days = Math.max(0, Date.now() - new Date(timestamp).getTime()) / 86_400_000;
  const expired = Boolean(validUntil && Date.now() > new Date(validUntil).getTime());
  const state = expired
    ? { label: `${timestamp.slice(0, 10)} 核验 · 已过期`, tone: "red" as const, className: "stale" }
    : days <= 1
    ? { label: "24 小时内核验", tone: "green" as const, className: "fresh" }
    : days <= 7
      ? { label: "7 天内核验", tone: "green" as const, className: "fresh" }
      : days <= 30
        ? { label: `${Math.floor(days)} 天前核验`, tone: "amber" as const, className: "aging" }
        : { label: `${timestamp.slice(0, 10)} 核验`, tone: "red" as const, className: "stale" };
  return <span className={`freshness freshness--${state.className}`} title={new Date(timestamp).toLocaleString("zh-CN")}><Signal tone={state.tone} /> {state.label}</span>;
}

export function InstallAppButton() {
  const [prompt, setPrompt] = useState<InstallPromptEvent | null>(null);
  useEffect(() => {
    const capture = (event: Event) => {
      event.preventDefault();
      setPrompt(event as InstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", capture);
    return () => window.removeEventListener("beforeinstallprompt", capture);
  }, []);
  if (!prompt) return null;
  return <button className="secondary-button" onClick={async () => { await prompt.prompt(); await prompt.userChoice; setPrompt(null); }}>安装到电脑</button>;
}
