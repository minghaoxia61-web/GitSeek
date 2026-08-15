import { FormEvent, useEffect, useState } from "react";

import { apiFetch } from "../api";
import type { Recommendation, TrendingResponse } from "../types";
import type { SearchHistoryEntry, SearchOptions } from "../lib/types";
import { formatNumber, sampleQueries } from "../lib/utils";

function TrendingPanel({ onOpen }: { onOpen: (repo: Recommendation) => void }) {
  const [range, setRange] = useState<7 | 30>(7);
  const [status, setStatus] = useState<"loading" | "ready" | "unavailable">("loading");
  const [items, setItems] = useState<Recommendation[]>([]);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setStatus("loading");
    apiFetch<TrendingResponse>(`/api/v1/trending?days=${range}&limit=6`, {
      signal: controller.signal,
    }).then((response) => {
      if (!active) return;
      setItems(response.results.slice(0, 6));
      setStatus("ready");
    }).catch(() => {
      if (!active) return;
      setItems([]);
      setStatus("unavailable");
    });
    return () => { active = false; controller.abort(); };
  }, [range, revision]);

  return (
    <section className="trending-panel" aria-labelledby="trending-title">
      <div className="trending-head">
        <div><span className="kicker">GitHub pulse</span><h2 id="trending-title">近期热榜</h2><p>结合最近更新、关注度和仓库信息完整度排序。</p></div>
        <div className="range-switch" aria-label="热榜时间范围">
          <button className={range === 7 ? "active" : ""} onClick={() => setRange(7)}>近 7 天</button>
          <button className={range === 30 ? "active" : ""} onClick={() => setRange(30)}>近 30 天</button>
        </div>
      </div>
      {status === "loading" && <div className="trending-state"><i className="spinner" /> 正在读取 GitHub 公开数据…</div>}
      {status === "unavailable" && <div className="trending-state trending-state--error"><span>热榜暂时无法更新，搜索功能不受影响。</span><button onClick={() => setRevision((value) => value + 1)}>重新加载</button></div>}
      {status === "ready" && items.length === 0 && <div className="trending-state">这个时间范围内暂时没有可用结果。</div>}
      {status === "ready" && items.length > 0 && <div className="trending-list">
        {items.map((repo, index) => {
          const [owner, name] = repo.full_name.split("/");
          return <button className="trending-row" key={repo.full_name} onClick={() => onOpen(repo)} aria-label={`查看 ${repo.full_name} 的项目档案`}>
            <span className="trending-rank">{String(index + 1).padStart(2, "0")}</span>
            <span className="trending-repo"><strong>{name}</strong><small>{owner}</small></span>
            <span className="trending-description">{repo.description || "这个仓库暂时没有提供简介。"}</span>
            <span className="trending-meta"><span>{repo.language || "多语言"}</span><b>★ {formatNumber(repo.stars)}</b></span>
            <i>→</i>
          </button>;
        })}
      </div>}
    </section>
  );
}

export function DiscoverView({ onSearch, onOpenTrending, initialQuery, initialOptions, history }: { onSearch: (query: string, options: SearchOptions) => Promise<void>; onOpenTrending: (repo: Recommendation) => void; initialQuery: string; initialOptions: SearchOptions; history: SearchHistoryEntry[] }) {
  const [query, setQuery] = useState(initialQuery);
  const [mode, setMode] = useState<"learn" | "contribute">(initialOptions.purpose === "contribution" ? "contribute" : "learn");
  const [advanced, setAdvanced] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingStage, setLoadingStage] = useState(0);
  const [constraints, setConstraints] = useState<string[]>([
    ...(initialOptions.licenses.length ? ["MIT / Apache"] : []),
    ...(initialOptions.recentOnly ? ["半年内活跃"] : []),
    ...(initialOptions.platform === "Windows" ? ["支持 Windows"] : []),
  ]);
  const [weeklyHours, setWeeklyHours] = useState<number | null>(initialOptions.weeklyHours);
  const [platform, setPlatform] = useState(initialOptions.platform ?? "");
  const [projectSize, setProjectSize] = useState<"" | "small" | "medium" | "large">(initialOptions.projectSize ?? "");

  const constraintOptions = ["MIT / Apache", "半年内活跃", "支持 Windows"];
  const loadingStages = ["解析条件", "查询仓库", "合并去重", "相关性排序"];

  useEffect(() => {
    if (!loading) {
      setLoadingStage(0);
      return;
    }
    const timer = window.setInterval(
      () => setLoadingStage((current) => Math.min(current + 1, loadingStages.length - 1)),
      800,
    );
    return () => window.clearInterval(timer);
  }, [loading, loadingStages.length]);

  function toggleConstraint(value: string) {
    setConstraints((current) => current.includes(value)
      ? current.filter((item) => item !== value)
      : [...current, value]);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    await onSearch(query.trim(), {
      purpose: mode === "learn" ? "learning" : "contribution",
      weeklyHours,
      platform: constraints.includes("支持 Windows") ? "Windows" : platform || null,
      licenses: constraints.includes("MIT / Apache") ? ["MIT", "Apache-2.0"] : [],
      recentOnly: constraints.includes("半年内活跃"),
      projectSize: projectSize || null,
    });
    setLoading(false);
  }

  async function repeatSearch(entry: SearchHistoryEntry) {
    setLoading(true);
    await onSearch(entry.query, entry.options);
    setLoading(false);
  }

  return (
    <div className="page page--discover">
      <section className="hero-grid">
        <div className="hero-copy">
          <div className="hero-title"><div className="kicker">GitHub / repository finder</div><h1>你想找什么项目？</h1></div>
          <p>写下用途、技术和限制。GitSeek 会把不符合的仓库先排除，再说明留下它们的理由。</p>
        </div>

        <form className="search-console card" onSubmit={submit}>
          <div className="console-topline"><span>搜索描述</span><code>PUBLIC REPOSITORIES</code></div>
          <div className="mode-switch" role="tablist" aria-label="搜索模式">
            <button type="button" className={mode === "learn" ? "active" : ""} onClick={() => setMode("learn")}>用于学习</button>
            <button type="button" className={mode === "contribute" ? "active" : ""} onClick={() => setMode("contribute")}>用于贡献</button>
          </div>
          <label className="query-field">
            <span>描述用途、技术或限制</span>
            <textarea value={query} onChange={(event) => setQuery(event.target.value)} maxLength={500} placeholder="输入你真正想找的项目…" rows={4} />
            <small>{query.length} / 500</small>
          </label>
          <div className="quick-constraints" aria-label="常用条件">
            {constraintOptions.map((item) => {
              const active = constraints.includes(item);
              return <button key={item} type="button" className={`constraint ${active ? "active" : ""}`} onClick={() => toggleConstraint(item)} aria-pressed={active}>{item}<i>{active ? "×" : "+"}</i></button>;
            })}
          </div>
          {advanced && (
            <div className="advanced-grid">
              <label>每周时间<select value={weeklyHours ?? ""} onChange={(event) => setWeeklyHours(event.target.value ? Number(event.target.value) : null)}><option value="">不限</option><option value="5">≤ 5 小时</option><option value="10">≤ 10 小时</option><option value="20">≤ 20 小时</option></select></label>
              <label>项目规模<select value={projectSize} onChange={(event) => setProjectSize(event.target.value as "" | "small" | "medium" | "large")}><option value="">不限</option><option value="small">小型 · 5k Star 以下</option><option value="medium">中型 · 1k–30k Star</option><option value="large">大型 · 10k Star 以上</option></select></label>
              <label>运行平台<select value={platform} onChange={(event) => setPlatform(event.target.value)}><option value="">不限</option><option value="Windows">Windows</option><option value="macOS">macOS</option><option value="Linux">Linux</option></select></label>
            </div>
          )}
          <div className="console-actions">
            <button type="button" className="text-button" onClick={() => setAdvanced(!advanced)}>{advanced ? "收起条件" : "高级约束"} <span>{advanced ? "−" : "+"}</span></button>
            <button className="primary-button" disabled={loading}>{loading ? <><i className="spinner" /> 正在查找</> : <>搜索项目 <b>↵</b></>}</button>
          </div>
          {loading && <div className="search-progress" aria-live="polite">{loadingStages.map((stage, index) => <span className={index <= loadingStage ? "active" : ""} aria-current={index === loadingStage ? "step" : undefined} key={stage}>{stage}</span>)}</div>}
        </form>
      </section>

      <section className="sample-strip">
        {history.length > 0 && <div className="recent-searches"><span>最近搜索</span>{history.slice(0, 3).map((entry) => <button key={`${entry.query}-${entry.searchedAt}`} onClick={() => void repeatSearch(entry)} disabled={loading}><span>{entry.query}</span><small>{entry.resultCount} 个结果 · {new Date(entry.searchedAt).toLocaleDateString("zh-CN")}</small><i>再次搜索 →</i></button>)}</div>}
        <span>也可以从这里开始</span>
        {sampleQueries.map((item) => <button key={item} onClick={() => setQuery(item)}>{item}<i>→</i></button>)}
      </section>
      <TrendingPanel onOpen={onOpenTrending} />
    </div>
  );
}
