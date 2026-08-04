import { FormEvent, useMemo, useState } from "react";

import { demoResponse } from "./mockData";
import type { Recommendation, RepositoryInvestigation, SearchResponse, View } from "./types";

const sampleQueries = [
  "适合初学者的 FastAPI 项目，MIT 许可证，最近半年活跃",
  "每周 5 小时，第一次贡献 AI 工具项目",
  "Windows 可运行、无需 GPU 的中文 OCR 项目",
];

const navItems: { id: View; label: string; eyebrow: string }[] = [
  { id: "discover", label: "智能发现", eyebrow: "DISCOVER" },
  { id: "results", label: "调查结果", eyebrow: "RESULTS" },
  { id: "compare", label: "项目对比", eyebrow: "COMPARE" },
  { id: "evals", label: "评测实验室", eyebrow: "EVAL LAB" },
];

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

function ScoreDial({ value, small = false }: { value: number; small?: boolean }) {
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

function Signal({ tone = "green" }: { tone?: "green" | "amber" | "red" }) {
  return <span className={`signal signal--${tone}`} aria-hidden="true" />;
}

function Shell({
  view,
  setView,
  compareCount,
  children,
}: {
  view: View;
  setView: (view: View) => void;
  compareCount: number;
  children: React.ReactNode;
}) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => setView("discover")} aria-label="回到 OpenScout 首页">
          <span className="brand-mark"><i /><i /><i /></span>
          <span><b>OPENSCOUT</b><small>REPOSITORY INTELLIGENCE</small></span>
        </button>

        <nav className="side-nav" aria-label="主导航">
          <p className="nav-section-label">工作区</p>
          {navItems.map((item) => (
            <button
              key={item.id}
              className={view === item.id || (view === "detail" && item.id === "results") ? "active" : ""}
              onClick={() => setView(item.id)}
            >
              <span className={`nav-glyph nav-glyph--${item.id}`} />
              <span><small>{item.eyebrow}</small>{item.label}</span>
              {item.id === "compare" && compareCount > 0 && <em>{compareCount}</em>}
            </button>
          ))}
        </nav>

        <div className="sidebar-brief">
          <div className="brief-head"><span>INDEX STATUS</span><b>LIVE</b></div>
          <strong>3,284</strong>
          <p>Python 仓库已进入观察索引</p>
          <div className="meter"><i style={{ width: "68%" }} /></div>
          <small>最近同步 · 4 分钟前</small>
        </div>

        <div className="sidebar-footer">
          <span className="avatar">XM</span>
          <span><b>夏明浩</b><small>Local workspace</small></span>
          <button aria-label="打开设置">···</button>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb"><span>OPENSCOUT</span><i>/</i><b>{view === "discover" ? "智能发现" : view === "evals" ? "评测实验室" : view === "compare" ? "项目对比" : "调查任务"}</b></div>
          <div className="top-actions">
            <span className="system-chip"><Signal /> API ONLINE</span>
            <span className="system-chip system-chip--muted">DATA · 4 MIN AGO</span>
            <a href="https://github.com/minghaoxia61-web/GitSeek" target="_blank" rel="noreferrer" className="icon-button" aria-label="打开 GitHub 仓库">↗</a>
          </div>
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}

function DiscoverView({ onSearch }: { onSearch: (query: string) => Promise<void> }) {
  const [query, setQuery] = useState(demoResponse.query);
  const [mode, setMode] = useState<"learn" | "contribute">("learn");
  const [advanced, setAdvanced] = useState(false);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    await onSearch(query);
    setLoading(false);
  }

  return (
    <div className="page page--discover">
      <section className="hero-grid">
        <div className="hero-copy">
          <div className="kicker"><span>01</span> EVIDENCE-FIRST DISCOVERY</div>
          <h1>别只找热门项目。<br /><em>找到真正适合你的。</em></h1>
          <p>把技能、时间与贡献目标转化为可验证约束。OpenScout 调查项目活跃度、工程质量与新人友好度，再给出有证据的推荐。</p>
          <div className="hero-proof">
            <div><strong>95<sup>%</sup></strong><span>硬约束目标满足率</span></div>
            <div><strong>4</strong><span>独立证据维度</span></div>
            <div><strong>0</strong><span>无依据事实容忍度</span></div>
          </div>
        </div>

        <form className="search-console" onSubmit={submit}>
          <div className="console-topline">
            <span><Signal /> NEW INVESTIGATION</span>
            <code>OS-QRY / 2026.08</code>
          </div>
          <div className="mode-switch" role="tablist" aria-label="搜索模式">
            <button type="button" className={mode === "learn" ? "active" : ""} onClick={() => setMode("learn")}><span>01</span> 学习项目</button>
            <button type="button" className={mode === "contribute" ? "active" : ""} onClick={() => setMode("contribute")}><span>02</span> 首次贡献</button>
          </div>
          <label className="query-field">
            <span>用自然语言描述你的目标</span>
            <textarea value={query} onChange={(event) => setQuery(event.target.value)} rows={4} />
            <small>{query.length} / 500</small>
          </label>
          <div className="quick-constraints">
            <button type="button" className="constraint active">Python <i>×</i></button>
            <button type="button" className="constraint">MIT / Apache <i>+</i></button>
            <button type="button" className="constraint">半年内活跃 <i>+</i></button>
            <button type="button" className="constraint">Windows <i>+</i></button>
          </div>
          {advanced && (
            <div className="advanced-grid">
              <label>每周时间<select defaultValue="5"><option value="5">≤ 5 小时</option><option value="10">≤ 10 小时</option></select></label>
              <label>项目规模<select defaultValue="medium"><option value="small">小型</option><option value="medium">中型</option><option value="large">大型</option></select></label>
              <label>最低置信度<select defaultValue="medium"><option value="medium">中等以上</option><option value="high">仅高置信</option></select></label>
            </div>
          )}
          <div className="console-actions">
            <button type="button" className="text-button" onClick={() => setAdvanced(!advanced)}>{advanced ? "收起条件" : "高级约束"} <span>{advanced ? "−" : "+"}</span></button>
            <button className="primary-button" disabled={loading}>{loading ? <><i className="spinner" /> 正在规划检索</> : <>开始调查 <b>→</b></>}</button>
          </div>
        </form>
      </section>

      <section className="sample-strip">
        <span>试试这些任务</span>
        {sampleQueries.map((item, index) => <button key={item} onClick={() => setQuery(item)}><i>0{index + 1}</i>{item}</button>)}
      </section>

      <section className="intelligence-grid">
        <article className="panel process-panel">
          <div className="panel-title"><span>受控调查流程</span><small>HOW IT WORKS</small></div>
          <div className="process-flow">
            {[
              ["01", "解析目标", "硬条件 / 偏好 / 排除项"],
              ["02", "多路召回", "GitHub / 关键词 / 向量"],
              ["03", "深度调查", "文档 / 活动 / Issue"],
              ["04", "证据验证", "冲突 / 过期 / 引用"],
            ].map((step, index) => (
              <div key={step[0]}><b>{step[0]}</b><span><strong>{step[1]}</strong><small>{step[2]}</small></span>{index < 3 && <i>→</i>}</div>
            ))}
          </div>
        </article>
        <article className="panel live-panel">
          <div className="panel-title"><span>实时情报</span><small>NETWORK PULSE</small></div>
          <div className="pulse-row"><Signal /><span><b>42</b> 个候选 Issue 状态已刷新</span><time>2m</time></div>
          <div className="pulse-row"><Signal tone="amber" /><span><b>7</b> 个高 Star 停更项目被降级</span><time>8m</time></div>
          <div className="pulse-row"><Signal /><span>Python 索引完成增量同步</span><time>11m</time></div>
        </article>
      </section>
    </div>
  );
}

function ResultCard({
  repo,
  selected,
  onSelect,
  onDetail,
}: {
  repo: Recommendation;
  selected: boolean;
  onSelect: () => void;
  onDetail: () => void;
}) {
  return (
    <article className="result-card">
      <div className="rank-column"><span>#{String(repo.rank).padStart(2, "0")}</span><button className={selected ? "selected" : ""} onClick={onSelect} aria-label="加入对比">{selected ? "✓" : "+"}</button></div>
      <div className="result-main">
        <div className="repo-heading">
          <div><span className="repo-owner">{repo.full_name.split("/")[0]} /</span><h3>{repo.full_name.split("/")[1]}</h3></div>
          <div className="repo-meta"><span>★ {formatNumber(repo.stars)}</span><span>{repo.language}</span><span>{repo.license_spdx ?? "NO LICENSE"}</span></div>
        </div>
        <p>{repo.description}</p>
        <div className="reason-row">{repo.reasons.slice(0, 3).map((reason) => <span key={reason}><i />{reason}</span>)}</div>
        <div className="risk-line"><b>RISK NOTE</b><span>{repo.risks[0]}</span></div>
        <div className="result-footer">
          <div className="evidence-links"><span>4 条事实证据</span><span>数据更新 {repo.pushed_at?.slice(0, 10)}</span></div>
          <button onClick={onDetail}>打开调查档案 <b>→</b></button>
        </div>
      </div>
      <div className="score-column">
        <ScoreDial value={repo.score} />
        <div className="mini-bars">
          {Object.entries(repo.score_breakdown).slice(0, 4).map(([key, value]) => <div key={key}><span>{key}</span><i><b style={{ width: `${Math.min(value / 35 * 100, 100)}%` }} /></i></div>)}
        </div>
      </div>
    </article>
  );
}

function ResultsView({
  data,
  compare,
  toggleCompare,
  onDetail,
  onNewSearch,
  fallback,
}: {
  data: SearchResponse;
  compare: string[];
  toggleCompare: (name: string) => void;
  onDetail: (repo: Recommendation) => void;
  onNewSearch: () => void;
  fallback: boolean;
}) {
  return (
    <div className="page page--results">
      <section className="results-header">
        <div>
          <div className="kicker"><span>02</span> INVESTIGATION COMPLETE</div>
          <h1>发现 <em>{data.eligible_candidate_count}</em> 个符合条件的项目</h1>
          <p>从 {formatNumber(data.source_total_count)} 个 GitHub 候选中完成硬过滤与证据评分。</p>
        </div>
        <div className="run-stamp"><small>RANKING VERSION</small><b>{data.ranking_version}</b><span><Signal /> VERIFIED PIPELINE</span></div>
      </section>

      {fallback && <div className="notice"><Signal tone="amber" /><span>后端暂时不可用，当前展示经过校准的演示数据。启动 API 后重新搜索即可切换为实时结果。</span></div>}

      <section className="query-record">
        <div><small>原始需求</small><p>“{data.query}”</p></div>
        <button onClick={onNewSearch}>编辑查询</button>
        <div className="constraint-record">
          <span>LANGUAGE · {data.constraints.language}</span>
          {data.constraints.technologies.map((item) => <span key={item}>STACK · {item}</span>)}
          {data.constraints.licenses.map((item) => <span key={item}>LICENSE · {item}</span>)}
          {data.constraints.pushed_after && <span>ACTIVE · {data.constraints.pushed_after}+</span>}
        </div>
        <code>{data.generated_github_query}</code>
      </section>

      <div className="results-layout">
        <section className="results-list">
          <div className="list-toolbar"><span>推荐排序 <b>TOP {data.results.length}</b></span><div><button className="active">综合匹配</button><button>活跃度</button><button>新人友好</button></div></div>
          {data.results.map((repo) => (
            <ResultCard key={repo.full_name} repo={repo} selected={compare.includes(repo.full_name)} onSelect={() => toggleCompare(repo.full_name)} onDetail={() => onDetail(repo)} />
          ))}
        </section>

        <aside className="evidence-rail">
          <article className="panel">
            <div className="panel-title"><span>约束审计</span><small>CONSTRAINT GATE</small></div>
            {[
              ["语言", "Python", "green"],
              ["许可证", data.constraints.licenses.join(" / ") || "不限", "green"],
              ["归档状态", "已排除", "green"],
              ["活跃时间", data.constraints.pushed_after || "不限", "green"],
            ].map((row) => <div className="audit-row" key={row[0]}><Signal tone={row[2] as "green"} /><span>{row[0]}</span><b>{row[1]}</b></div>)}
          </article>
          <article className="panel confidence-card">
            <div className="panel-title"><span>证据置信度</span><small>EVIDENCE HEALTH</small></div>
            <strong>高</strong><p>关键事实均来自近期 GitHub API；深度文档调查尚未运行。</p>
            <div className="confidence-scale"><i /><i /><i className="active" /></div>
          </article>
          <article className="panel compare-hint">
            <small>COMPARE QUEUE</small><strong>{compare.length}<span>/3</span></strong><p>选择项目进行并列证据比较</p>
          </article>
        </aside>
      </div>
    </div>
  );
}

function DetailView({
  repo,
  investigation,
  status,
  onBack,
  onCompare,
}: {
  repo: Recommendation;
  investigation: RepositoryInvestigation | null;
  status: "loading" | "ready" | "unavailable";
  onBack: () => void;
  onCompare: () => void;
}) {
  const scores = investigation?.scores;
  const dossierScore = scores
    ? (scores.documentation + scores.engineering + scores.learning_friendliness) / 3
    : repo.score;
  const signals = investigation?.signals;
  const signalRows: [string, boolean | undefined][] = [
    ["README", signals?.has_readme],
    ["贡献指南", signals?.has_contributing],
    ["自动化测试", signals?.has_tests],
    ["持续集成", signals?.has_ci],
    ["pyproject.toml", signals?.has_pyproject],
    ["安全策略", signals?.has_security_policy],
    ["快速开始", signals?.readme_has_quickstart],
  ];
  const scoreRows = [
    ["社区健康", scores?.community_health ?? 0],
    ["文档完整", scores?.documentation ?? 0],
    ["工程质量", scores?.engineering ?? 0],
    ["学习友好", scores?.learning_friendliness ?? 0],
  ] as const;
  const risks = investigation?.risks ?? repo.risks;

  return (
    <div className="page detail-page">
      <button className="back-button" onClick={onBack}>← 返回调查结果</button>
      <section className="detail-hero">
        <div className="repo-monogram">{repo.full_name.split("/")[1].slice(0, 2).toUpperCase()}</div>
        <div className="detail-title">
          <div className="kicker">
            <span>REPOSITORY DOSSIER</span>
            {status === "loading" ? "正在读取 GitHub 证据" : status === "ready" ? `LIVE EVIDENCE · ${investigation?.confidence.toUpperCase()} CONFIDENCE` : "DEMO FALLBACK"}
          </div>
          <h1>{repo.full_name}</h1>
          <p>{investigation?.description ?? repo.description}</p>
          <div className="repo-meta"><span>★ {formatNumber(repo.stars)}</span><span>{repo.language}</span><span>{repo.license_spdx}</span><span>Default · {investigation?.default_branch ?? "main"}</span></div>
        </div>
        <ScoreDial value={dossierScore} />
        <div className="detail-actions"><button className="secondary-button" onClick={onCompare}>加入对比</button><a className="primary-button" href={repo.html_url} target="_blank" rel="noreferrer">打开 GitHub ↗</a></div>
      </section>

      {status === "loading" && <div className="detail-status"><i className="spinner" /> 正在读取社区档案、仓库目录、工作流和 README…</div>}
      {status === "unavailable" && <div className="notice"><Signal tone="amber" /><span>实时调查接口暂不可用，当前保留搜索阶段数据；本地 API 启动后重新打开档案即可恢复真实证据。</span></div>}

      <div className="detail-grid">
        <section className="detail-main">
          <article className="panel health-panel">
            <div className="panel-title"><span>调查评分</span><small>DETERMINISTIC SIGNALS</small></div>
            <div className="health-score"><strong>{dossierScore.toFixed(0)}</strong><span>{investigation?.confidence.toUpperCase() ?? "PENDING"}</span><p>分数仅由公开静态证据计算，不运行仓库代码，也不使用模型主观打分。</p></div>
            <div className="score-profile">
              {scoreRows.map(([label, value]) => <div key={label}><span>{label}</span><i><b style={{ width: `${value}%` }} /></i><strong>{status === "ready" ? value.toFixed(0) : "—"}</strong></div>)}
            </div>
          </article>

          <article className="panel evidence-panel">
            <div className="panel-title"><span>事实证据</span><small>{investigation?.evidence.length ?? 0} TRACEABLE CLAIMS</small></div>
            {status === "loading" && [1, 2, 3].map((item) => <div className="evidence-item evidence-item--loading" key={item}><span>0{item}</span><div><b /><p /></div></div>)}
            {status === "ready" && investigation?.evidence.map((evidence, index) => <div className="evidence-item" key={evidence.id}><span>{String(index + 1).padStart(2, "0")}</span><div><b>{evidence.fact}</b><p>观测值：{typeof evidence.value === "boolean" ? (evidence.value ? "已发现" : "未发现") : evidence.value} · {evidence.confidence.toUpperCase()} CONFIDENCE · {evidence.fetched_at.slice(0, 10)}</p></div><a href={evidence.source_url} target="_blank" rel="noreferrer">查看来源 ↗</a></div>)}
            {status === "unavailable" && repo.reasons.map((reason, index) => <div className="evidence-item" key={reason}><span>0{index + 1}</span><div><b>{reason}</b><p>来自搜索阶段的 GitHub 仓库元数据。</p></div></div>)}
          </article>

          <article className="panel coverage-panel">
            <div className="panel-title"><span>调查覆盖范围</span><small>BOUNDED READ-ONLY WORKFLOW</small></div>
            {["GitHub 仓库元数据", "社区健康档案", "根目录与 CI 工作流", "README 快速开始标记"].map((source, index) => <div className="coverage-row" key={source}><span>0{index + 1}</span><b>{source}</b><small>{status === "ready" ? "已读取" : "等待连接"}</small></div>)}
          </article>
        </section>

        <aside className="detail-side">
          <article className="panel"><div className="panel-title"><span>工程信号</span><small>REPO PROFILE</small></div>{signalRows.map(([label, value]) => <div className="audit-row" key={label}><Signal tone={value === undefined ? "amber" : value ? "green" : "red"} /><span>{label}</span><b>{value === undefined ? "读取中" : value ? "已发现" : "未发现"}</b></div>)}</article>
          <article className="panel risk-panel"><div className="panel-title"><span>风险提示</span><small>BEFORE YOU START</small></div>{risks.length ? risks.map((risk, index) => <div key={risk}><b>0{index + 1}</b><p>{risk}</p></div>) : <p className="empty-copy">当前规则未发现显著风险，仍建议阅读原始贡献说明。</p>}</article>
          <article className="panel path-card"><small>INVESTIGATION BOUNDARY</small><strong>证据优先，不执行代码</strong><p>{investigation?.limitations[0] ?? "等调查接口返回后显示能力边界。"}</p><a href={repo.html_url} target="_blank" rel="noreferrer">人工复核仓库 →</a></article>
        </aside>
      </div>
    </div>
  );
}

function CompareView({ repos, onDiscover }: { repos: Recommendation[]; onDiscover: () => void }) {
  const items = repos.length ? repos : demoResponse.results.slice(0, 3);
  return (
    <div className="page compare-page">
      <section className="page-heading"><div className="kicker"><span>03</span> SIDE-BY-SIDE EVIDENCE</div><h1>项目对比工作台</h1><p>并列查看匹配、维护、贡献门槛和风险，不被单一总分误导。</p></section>
      <div className="compare-grid">
        <div className="compare-labels"><div className="compare-empty"><span>COMPARE MATRIX</span></div>{["综合匹配", "技术相关", "维护活跃", "新人友好", "许可证", "最近推送", "主要风险"].map((label) => <div key={label}>{label}</div>)}</div>
        {items.map((repo, index) => <article className="compare-column" key={repo.full_name}><header><small>OPTION 0{index + 1}</small><h3>{repo.full_name}</h3><p>{repo.description}</p></header><div><ScoreDial value={repo.score} small /></div><div><strong>{repo.score_breakdown.relevance?.toFixed(0) ?? "—"}</strong><span>/ 35</span></div><div><strong>{repo.score_breakdown.activity?.toFixed(0) ?? "—"}</strong><span>/ 30</span></div><div><strong>{index === 0 ? "高" : "中高"}</strong></div><div><span className="license-badge">{repo.license_spdx}</span></div><div><strong>{repo.pushed_at?.slice(0, 10)}</strong></div><div className="compare-risk">{repo.risks[0]}</div><footer><button>查看完整档案 →</button></footer></article>)}
        {items.length < 3 && <button className="add-column" onClick={onDiscover}>+<span>添加一个候选项目</span></button>}
      </div>
    </div>
  );
}

function EvalsView() {
  return (
    <div className="page evals-page">
      <section className="page-heading page-heading--row"><div><div className="kicker"><span>04</span> QUALITY CONTROL</div><h1>评测实验室</h1><p>追踪推荐质量、数据新鲜度、成本和版本退化。</p></div><button className="primary-button">运行固定评测集 <b>→</b></button></section>
      <section className="metric-grid">
        {[["约束满足率", "97.4%", "+1.2", "目标 ≥ 95%", "97%"], ["nDCG@10", "0.684", "+0.041", "vs. baseline", "84%"], ["事实准确率", "96.1%", "+0.8", "目标 ≥ 95%", "96%"], ["P95 延迟", "8.42s", "−1.7s", "目标 ≤ 12s", "72%"]].map((metric) => <article className="metric-card" key={metric[0]}><small>{metric[0]}</small><strong>{metric[1]}</strong><span>{metric[2]}</span><div><i style={{ width: metric[4] }} /></div><p>{metric[3]}</p></article>)}
      </section>
      <div className="eval-layout">
        <article className="panel run-table"><div className="panel-title"><span>版本对比</span><small>EXPERIMENT RUNS</small></div><div className="table-head"><span>版本</span><span>策略</span><span>nDCG@10</span><span>准确率</span><span>P95</span><span>状态</span></div>{[["v0.3.0", "Hybrid + Verifier", "0.684", "96.1%", "8.42s", "CURRENT"], ["v0.2.1", "Hybrid Retrieval", "0.643", "91.8%", "6.71s", "PASSED"], ["v0.1.0", "Metadata Baseline", "0.521", "95.4%", "2.14s", "BASELINE"]].map((row) => <div className="table-row" key={row[0]}>{row.map((cell, index) => <span key={cell} className={index === 5 ? "status-cell" : ""}>{cell}</span>)}</div>)}</article>
        <article className="panel trace-panel"><div className="panel-title"><span>单次 Trace</span><small>REQUEST 8F-24A</small></div>{[["parse_query", "248ms", "1.2k"], ["search_github", "624ms", "—"], ["retrieve_local", "91ms", "—"], ["investigate_repo", "4.21s", "8.4k"], ["rank + verify", "1.08s", "2.1k"]].map((trace, index) => <div className="trace-row" key={trace[0]}><b>0{index + 1}</b><span><strong>{trace[0]}</strong><small>{trace[2]} tokens</small></span><time>{trace[1]}</time></div>)}</article>
      </div>
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<View>("discover");
  const [data, setData] = useState<SearchResponse>(demoResponse);
  const [selectedRepo, setSelectedRepo] = useState<Recommendation>(demoResponse.results[0]);
  const [investigation, setInvestigation] = useState<RepositoryInvestigation | null>(null);
  const [investigationStatus, setInvestigationStatus] = useState<"loading" | "ready" | "unavailable">("unavailable");
  const [compare, setCompare] = useState<string[]>([]);
  const [fallback, setFallback] = useState(false);

  async function search(query: string) {
    try {
      const response = await fetch("/api/v1/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, limit: 10 }),
      });
      if (!response.ok) throw new Error("Search API unavailable");
      setData(await response.json() as SearchResponse);
      setFallback(false);
    } catch {
      setData({ ...demoResponse, query });
      setFallback(true);
    }
    setView("results");
  }

  function toggleCompare(name: string) {
    setCompare((current) => current.includes(name) ? current.filter((item) => item !== name) : current.length < 3 ? [...current, name] : current);
  }

  function openDetail(repo: Recommendation) {
    setSelectedRepo(repo);
    setInvestigation(null);
    setInvestigationStatus("loading");
    setView("detail");
    const [owner, name] = repo.full_name.split("/");
    fetch(`/api/v1/repos/${encodeURIComponent(owner)}/${encodeURIComponent(name)}/investigate`)
      .then((response) => {
        if (!response.ok) throw new Error("Investigation API unavailable");
        return response.json() as Promise<RepositoryInvestigation>;
      })
      .then((payload) => {
        setInvestigation(payload);
        setInvestigationStatus("ready");
      })
      .catch(() => setInvestigationStatus("unavailable"));
  }

  const compareRepos = useMemo(() => data.results.filter((repo) => compare.includes(repo.full_name)), [compare, data.results]);

  return (
    <Shell view={view} setView={setView} compareCount={compare.length}>
      {view === "discover" && <DiscoverView onSearch={search} />}
      {view === "results" && <ResultsView data={data} compare={compare} toggleCompare={toggleCompare} fallback={fallback} onNewSearch={() => setView("discover")} onDetail={openDetail} />}
      {view === "detail" && <DetailView repo={selectedRepo} investigation={investigation} status={investigationStatus} onBack={() => setView("results")} onCompare={() => toggleCompare(selectedRepo.full_name)} />}
      {view === "compare" && <CompareView repos={compareRepos} onDiscover={() => setView("results")} />}
      {view === "evals" && <EvalsView />}
    </Shell>
  );
}
