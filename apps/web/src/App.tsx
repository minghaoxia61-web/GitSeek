import { FormEvent, useEffect, useMemo, useState } from "react";

import { demoResponse } from "./mockData";
import type { AgentRunResponse, ContributionIssue, EvaluationSummary, Recommendation, RepositoryInvestigation, SearchResponse, View } from "./types";

type SearchOptions = {
  purpose: "learning" | "contribution";
  weeklyHours: number;
  platform: string | null;
  licenses: string[];
  recentOnly: boolean;
  projectSize: "small" | "medium" | "large";
};

const sampleQueries = [
  "适合初学者的 FastAPI 项目，MIT 许可证，最近半年活跃",
  "每周 5 小时，第一次贡献 AI 工具项目",
  "Windows 可运行、无需 GPU 的中文 OCR 项目",
];

const navItems: { id: View; label: string; eyebrow: string }[] = [
  { id: "discover", label: "发现项目", eyebrow: "SEARCH" },
  { id: "results", label: "候选项目", eyebrow: "RESULTS" },
  { id: "compare", label: "项目对比", eyebrow: "COMPARE" },
  { id: "evals", label: "质量记录", eyebrow: "QUALITY" },
];

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

const scoreLabels: Record<string, string> = {
  relevance: "相关度",
  activity: "活跃度",
  popularity: "采用度",
  metadata: "信息完整",
  license: "许可证",
};

function getDeviceId() {
  const key = "openscout:device-id";
  const existing = localStorage.getItem(key);
  if (existing) return existing;
  const created = crypto.randomUUID();
  localStorage.setItem(key, created);
  return created;
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
          <span><b>OpenScout</b><small>开源项目研究工具</small></span>
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
          <div className="brief-head"><span>数据来源</span><b>GitHub</b></div>
          <p>推荐结果附带来源、更新时间和已知限制。</p>
        </div>

        <div className="sidebar-footer">
          <span className="avatar">OS</span>
          <span><b>个人工作区</b><small>本地优先</small></span>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb"><span>OpenScout</span><i>/</i><b>{view === "discover" ? "发现项目" : view === "evals" ? "质量记录" : view === "compare" ? "项目对比" : "候选项目"}</b></div>
          <div className="top-actions">
            <span className="system-chip"><Signal /> 公开数据</span>
            <a href="https://github.com/minghaoxia61-web/GitSeek" target="_blank" rel="noreferrer" className="repo-link">查看源码 ↗</a>
          </div>
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}

function DiscoverView({ onSearch }: { onSearch: (query: string, options: SearchOptions) => Promise<void> }) {
  const [query, setQuery] = useState(demoResponse.query);
  const [mode, setMode] = useState<"learn" | "contribute">("learn");
  const [advanced, setAdvanced] = useState(false);
  const [loading, setLoading] = useState(false);
  const [constraints, setConstraints] = useState(["Python"]);
  const [weeklyHours, setWeeklyHours] = useState(5);
  const [platform, setPlatform] = useState("");
  const [projectSize, setProjectSize] = useState<"small" | "medium" | "large">("medium");

  const constraintOptions = ["Python", "MIT / Apache", "半年内活跃", "支持 Windows"];

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
      projectSize,
    });
    setLoading(false);
  }

  return (
    <div className="page page--discover">
      <section className="hero-grid">
        <div className="hero-copy">
          <div className="kicker">开源项目发现</div>
          <h1>找到适合现在的你，<br /><em>而不只是最热门的项目。</em></h1>
          <p>说清楚技术栈、可投入时间和目标。OpenScout 会先排除不符合条件的仓库，再把推荐理由、风险和原始来源放在一起。</p>
          <div className="hero-proof">
            <div><strong>先筛选</strong><span>许可证、语言与活跃时间</span></div>
            <div><strong>再解释</strong><span>每条结论都能查看来源</span></div>
            <div><strong>保留边界</strong><span>不确定的地方明确标出</span></div>
          </div>
        </div>

        <form className="search-console" onSubmit={submit}>
          <div className="console-topline">
            <span>新建一次项目搜索</span>
            <code>GitHub 公开仓库</code>
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
          <div className="quick-constraints" aria-label="常用条件">
            {constraintOptions.map((item) => {
              const active = constraints.includes(item);
              return <button key={item} type="button" className={`constraint ${active ? "active" : ""}`} onClick={() => toggleConstraint(item)} aria-pressed={active}>{item}<i>{active ? "×" : "+"}</i></button>;
            })}
          </div>
          {advanced && (
            <div className="advanced-grid">
              <label>每周时间<select value={weeklyHours} onChange={(event) => setWeeklyHours(Number(event.target.value))}><option value="5">≤ 5 小时</option><option value="10">≤ 10 小时</option><option value="20">≤ 20 小时</option></select></label>
              <label>项目规模<select value={projectSize} onChange={(event) => setProjectSize(event.target.value as "small" | "medium" | "large")}><option value="small">小型 · 5k Star 以下</option><option value="medium">中型 · 1k–30k Star</option><option value="large">大型 · 10k Star 以上</option></select></label>
              <label>运行平台<select value={platform} onChange={(event) => setPlatform(event.target.value)}><option value="">不限</option><option value="Windows">Windows</option><option value="macOS">macOS</option><option value="Linux">Linux</option></select></label>
            </div>
          )}
          <div className="console-actions">
            <button type="button" className="text-button" onClick={() => setAdvanced(!advanced)}>{advanced ? "收起条件" : "高级约束"} <span>{advanced ? "−" : "+"}</span></button>
            <button className="primary-button" disabled={loading}>{loading ? <><i className="spinner" /> 正在搜索</> : <>查看候选项目 <b>→</b></>}</button>
          </div>
          {loading && <div className="search-progress" aria-live="polite"><span className="active">解析条件</span><span className="active">混合检索</span><span className="active">深度调查</span><span>证据验证</span></div>}
        </form>
      </section>

      <section className="sample-strip">
        <span>试试这些任务</span>
        {sampleQueries.map((item, index) => <button key={item} onClick={() => setQuery(item)}><i>0{index + 1}</i>{item}</button>)}
      </section>

      <section className="intelligence-grid">
        <article className="panel process-panel">
          <div className="panel-title"><span>搜索过程</span><small>四个步骤</small></div>
          <div className="process-flow">
            {[
              ["01", "解析目标", "硬条件 / 偏好 / 排除项"],
              ["02", "查找仓库", "GitHub 与本地索引"],
              ["03", "检查项目", "文档 / 活跃度 / 工程信号"],
              ["04", "整理结果", "理由 / 风险 / 原始来源"],
            ].map((step, index) => (
              <div key={step[0]}><b>{step[0]}</b><span><strong>{step[1]}</strong><small>{step[2]}</small></span>{index < 3 && <i>→</i>}</div>
            ))}
          </div>
        </article>
        <article className="panel live-panel">
          <div className="panel-title"><span>结果里会看到</span><small>不只是一张榜单</small></div>
          <div className="pulse-row"><span>01</span><b>为什么推荐这个项目</b></div>
          <div className="pulse-row"><span>02</span><b>开始之前需要注意什么</b></div>
          <div className="pulse-row"><span>03</span><b>结论来自哪里、何时更新</b></div>
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
        <div className="risk-line"><b>需要留意</b><span>{repo.risks[0]}</span></div>
        <div className="result-footer">
          <div className="evidence-links">
            <span>{repo.retrieval_sources?.includes("github_live") ? "GitHub 实时" : "本地索引"}</span>
            <span>仓库更新 {repo.pushed_at?.slice(0, 10)}</span>
          </div>
          <button onClick={onDetail}>查看项目档案 <b>→</b></button>
        </div>
      </div>
      <div className="score-column">
        <ScoreDial value={repo.score} />
        <div className="mini-bars">
          {Object.entries(repo.score_breakdown).slice(0, 4).map(([key, value]) => <div key={key}><span>{scoreLabels[key] ?? key}</span><i><b style={{ width: `${Math.min(value / 35 * 100, 100)}%` }} /></i></div>)}
        </div>
      </div>
    </article>
  );
}

function ResultsView({
  data,
  agentRun,
  compare,
  toggleCompare,
  onDetail,
  onNewSearch,
  fallback,
}: {
  data: SearchResponse;
  agentRun: AgentRunResponse | null;
  compare: string[];
  toggleCompare: (name: string) => void;
  onDetail: (repo: Recommendation) => void;
  onNewSearch: () => void;
  fallback: boolean;
}) {
  const [sortBy, setSortBy] = useState<"match" | "activity" | "approachable">("match");
  const sortedResults = useMemo(() => [...data.results].sort((left, right) => {
    if (sortBy === "activity") return (right.score_breakdown.activity ?? 0) - (left.score_breakdown.activity ?? 0);
    if (sortBy === "approachable") return left.stars - right.stars;
    return right.score - left.score;
  }), [data.results, sortBy]);

  return (
    <div className="page page--results">
      <section className="results-header">
        <div>
          <div className="kicker">搜索结果</div>
          <h1>发现 <em>{data.eligible_candidate_count}</em> 个符合条件的项目</h1>
          <p>从 {formatNumber(data.source_total_count)} 个候选中完成硬过滤与证据评分；实时结果与已同步索引会自动合并。</p>
        </div>
        <div className="run-stamp"><small>排序规则</small><b>{data.ranking_version}</b><span>可查看每条推荐的依据</span></div>
      </section>

      {fallback && <div className="notice"><Signal tone="amber" /><span>后端暂时不可用，当前展示经过校准的演示数据。启动 API 后重新搜索即可切换为实时结果。</span></div>}
      {!fallback && data.retrieval?.github_status === "unavailable" && <div className="notice"><Signal tone="amber" /><span>GitHub 当前限流或暂不可用，本次结果来自已同步索引，页面已保留数据时间。</span></div>}

      <section className="query-record">
        <div><small>原始需求</small><p>“{data.query}”</p></div>
        <button onClick={onNewSearch}>编辑查询</button>
        <div className="constraint-record">
          <span>目标 · {data.constraints.purpose === "contribution" ? "首次贡献" : "学习项目"}</span>
          <span>语言 · {data.constraints.language}</span>
          {data.constraints.technologies.map((item) => <span key={item}>技术 · {item}</span>)}
          {data.constraints.licenses.map((item) => <span key={item}>许可 · {item}</span>)}
          {data.constraints.pushed_after && <span>更新 · {data.constraints.pushed_after} 之后</span>}
          {data.constraints.weekly_hours && <span>时间 · 每周 {data.constraints.weekly_hours} 小时</span>}
          {data.constraints.platform && <span>平台 · {data.constraints.platform}</span>}
          {data.constraints.project_size && <span>规模 · {data.constraints.project_size === "small" ? "小型" : data.constraints.project_size === "medium" ? "中型" : "大型"}</span>}
        </div>
        <code>{data.generated_github_query}</code>
      </section>

      <div className="results-layout">
        <section className="results-list">
          <div className="list-toolbar"><span>共 <b>{data.results.length}</b> 个候选项目</span><div><button className={sortBy === "match" ? "active" : ""} onClick={() => setSortBy("match")}>综合匹配</button><button className={sortBy === "activity" ? "active" : ""} onClick={() => setSortBy("activity")}>最近活跃</button><button className={sortBy === "approachable" ? "active" : ""} onClick={() => setSortBy("approachable")}>规模较小</button></div></div>
          {sortedResults.map((repo) => (
            <ResultCard key={repo.full_name} repo={repo} selected={compare.includes(repo.full_name)} onSelect={() => toggleCompare(repo.full_name)} onDetail={() => onDetail(repo)} />
          ))}
        </section>

        <aside className="evidence-rail">
          {agentRun && <article className="panel">
            <div className="panel-title"><span>Agent 执行</span><small>{agentRun.status === "succeeded" ? "完整完成" : "部分降级"}</small></div>
            {agentRun.steps.map((step) => <div className="audit-row" key={step.node}><Signal tone={step.status === "completed" ? "green" : "amber"} /><span>{step.summary}</span><b>{step.duration_ms}ms</b></div>)}
            <p className="panel-note">证据支持率 {agentRun.verification.length ? Math.round(agentRun.verification.reduce((sum, item) => sum + item.support_ratio, 0) / agentRun.verification.length * 100) : 0}% · 最多重试 {agentRun.retry_count} 次</p>
          </article>}
          <article className="panel">
            <div className="panel-title"><span>已应用的条件</span><small>搜索范围</small></div>
            {[
              ["语言", "Python", "green"],
              ["许可证", data.constraints.licenses.join(" / ") || "不限", "green"],
              ["归档状态", "已排除", "green"],
              ["活跃时间", data.constraints.pushed_after || "不限", "green"],
            ].map((row) => <div className="audit-row" key={row[0]}><Signal tone={row[2] as "green"} /><span>{row[0]}</span><b>{row[1]}</b></div>)}
          </article>
          <article className="panel confidence-card">
            <div className="panel-title"><span>检索来源</span><small>当前结果</small></div>
            <strong>{data.retrieval?.github_status === "unavailable" ? "索引" : "混合"}</strong>
            <p>本地索引 {data.retrieval?.local_candidates ?? 0} 个，GitHub 实时 {data.retrieval?.github_candidates ?? data.results.length} 个；相同仓库已自动去重。</p>
            <div className="confidence-scale"><i /><i /><i className="active" /></div>
          </article>
          <article className="panel compare-hint">
            <small>对比列表</small><strong>{compare.length}<span>/3</span></strong><p>最多选择三个项目并排查看</p>
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
  issues,
  issueStatus,
  onBack,
  onCompare,
  onFeedback,
}: {
  repo: Recommendation;
  investigation: RepositoryInvestigation | null;
  status: "loading" | "ready" | "unavailable";
  issues: ContributionIssue[];
  issueStatus: "loading" | "ready" | "unavailable";
  onBack: () => void;
  onCompare: () => void;
  onFeedback: (action: "helpful" | "not_relevant" | "saved" | "opened_issue") => Promise<void>;
}) {
  const [feedbackMessage, setFeedbackMessage] = useState("");
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

  async function feedback(action: "helpful" | "not_relevant" | "saved") {
    await onFeedback(action);
    setFeedbackMessage(action === "helpful" ? "已记录：推荐有帮助" : action === "saved" ? "已收藏到当前设备" : "已记录，我们会把它作为失败样本检查");
  }

  return (
    <div className="page detail-page">
      <button className="back-button" onClick={onBack}>← 返回调查结果</button>
      <section className="detail-hero">
        <div className="repo-monogram">{repo.full_name.split("/")[1].slice(0, 2).toUpperCase()}</div>
        <div className="detail-title">
          <div className="kicker">{status === "loading" ? "正在读取仓库信息" : status === "ready" ? `项目档案 · ${investigation?.confidence === "high" ? "高" : investigation?.confidence === "medium" ? "中" : "低"}置信度` : "项目档案 · 演示数据"}</div>
          <h1>{repo.full_name}</h1>
          <p>{investigation?.description ?? repo.description}</p>
          <div className="repo-meta"><span>★ {formatNumber(repo.stars)}</span><span>{repo.language}</span><span>{repo.license_spdx}</span><span>Default · {investigation?.default_branch ?? "main"}</span></div>
        </div>
        <ScoreDial value={dossierScore} />
        <div className="detail-actions"><button className="secondary-button" onClick={onCompare}>加入对比</button><button className="secondary-button" onClick={() => feedback("saved")}>收藏项目</button><a className="primary-button" href={repo.html_url} target="_blank" rel="noreferrer">打开 GitHub ↗</a></div>
      </section>

      {status === "loading" && <div className="detail-status"><i className="spinner" /> 正在读取社区档案、仓库目录、工作流和 README…</div>}
      {status === "unavailable" && <div className="notice"><Signal tone="amber" /><span>实时调查接口暂不可用，当前保留搜索阶段数据；本地 API 启动后重新打开档案即可恢复真实证据。</span></div>}

      <div className="detail-grid">
        <section className="detail-main">
          <article className="panel health-panel">
            <div className="panel-title"><span>项目概览</span><small>基于公开仓库信号</small></div>
            <div className="health-score"><strong>{dossierScore.toFixed(0)}</strong><span>{investigation ? `${investigation.confidence === "high" ? "高" : investigation.confidence === "medium" ? "中" : "低"}置信度` : "等待数据"}</span><p>分数来自公开静态信息。不会运行仓库代码，也不替代人工判断。</p></div>
            <div className="score-profile">
              {scoreRows.map(([label, value]) => <div key={label}><span>{label}</span><i><b style={{ width: `${value}%` }} /></i><strong>{status === "ready" ? value.toFixed(0) : "—"}</strong></div>)}
            </div>
          </article>

          <article className="panel evidence-panel">
            <div className="panel-title"><span>推荐依据</span><small>{investigation?.evidence.length ?? 0} 条可追溯记录</small></div>
            {status === "loading" && [1, 2, 3].map((item) => <div className="evidence-item evidence-item--loading" key={item}><span>0{item}</span><div><b /><p /></div></div>)}
            {status === "ready" && investigation?.evidence.map((evidence, index) => <div className="evidence-item" key={evidence.id}><span>{String(index + 1).padStart(2, "0")}</span><div><b>{evidence.fact}</b><p>观测值：{typeof evidence.value === "boolean" ? (evidence.value ? "已发现" : "未发现") : evidence.value} · {evidence.confidence.toUpperCase()} CONFIDENCE · {evidence.fetched_at.slice(0, 10)}</p></div><a href={evidence.source_url} target="_blank" rel="noreferrer">查看来源 ↗</a></div>)}
            {status === "unavailable" && repo.reasons.map((reason, index) => <div className="evidence-item" key={reason}><span>0{index + 1}</span><div><b>{reason}</b><p>来自搜索阶段的 GitHub 仓库元数据。</p></div></div>)}
          </article>

          <article className="panel coverage-panel">
            <div className="panel-title"><span>已检查的内容</span><small>只读检查</small></div>
            {["GitHub 仓库元数据", "社区健康档案", "根目录与 CI 工作流", "README 快速开始标记"].map((source, index) => <div className="coverage-row" key={source}><span>0{index + 1}</span><b>{source}</b><small>{status === "ready" ? "已读取" : "等待连接"}</small></div>)}
          </article>

          <article className="panel issues-panel">
            <div className="panel-title"><span>适合开始的 Issue</span><small>{issueStatus === "ready" ? `${issues.length} 个候选` : issueStatus === "loading" ? "正在刷新状态" : "暂不可用"}</small></div>
            {issueStatus === "loading" && <div className="issues-loading"><i className="spinner" /> 正在检查开放状态、认领情况与任务描述…</div>}
            {issueStatus === "ready" && issues.map((issue) => <a className="issue-row" href={issue.html_url} target="_blank" rel="noreferrer" key={issue.number} onClick={() => onFeedback("opened_issue")}><span className={`difficulty ${issue.difficulty}`}>{issue.difficulty === "easy" ? "容易" : issue.difficulty === "medium" ? "中等" : "较难"}</span><div><b>#{issue.number} {issue.title}</b><p>{issue.reasons.join(" · ")}{issue.risks[0] ? `；${issue.risks[0]}` : ""}</p></div><strong>{issue.score.toFixed(0)}</strong></a>)}
            {issueStatus === "ready" && !issues.length && <p className="empty-copy">当前没有找到未认领且信息足够的开放 Issue。OpenScout 不会为了填满列表推荐不确定任务。</p>}
            {issueStatus === "unavailable" && <p className="empty-copy">Issue 状态暂时无法刷新，请稍后再试或直接到 GitHub 查看。</p>}
          </article>
        </section>

        <aside className="detail-side">
          <article className="panel"><div className="panel-title"><span>工程信号</span><small>仓库文件检查</small></div>{signalRows.map(([label, value]) => <div className="audit-row" key={label}><Signal tone={value === undefined ? "amber" : value ? "green" : "red"} /><span>{label}</span><b>{value === undefined ? "读取中" : value ? "已发现" : "未发现"}</b></div>)}</article>
          <article className="panel risk-panel"><div className="panel-title"><span>开始前留意</span><small>已知风险</small></div>{risks.length ? risks.map((risk, index) => <div key={risk}><b>0{index + 1}</b><p>{risk}</p></div>) : <p className="empty-copy">当前规则未发现显著风险，仍建议阅读原始贡献说明。</p>}</article>
          <article className="panel path-card"><small>检查范围</small><strong>只读取公开信息</strong><p>{investigation?.limitations[0] ?? "连接调查接口后，这里会显示本次检查没有覆盖的内容。"}</p><a href={repo.html_url} target="_blank" rel="noreferrer">到 GitHub 人工确认 →</a></article>
          <article className="panel feedback-card"><div className="panel-title"><span>这条推荐怎么样？</span><small>反馈用于回归检查</small></div><div><button onClick={() => feedback("helpful")}>有帮助</button><button onClick={() => feedback("not_relevant")}>不太相关</button></div>{feedbackMessage && <p>{feedbackMessage}</p>}</article>
        </aside>
      </div>
    </div>
  );
}

function CompareView({ repos, onDiscover, onDetail, onRemove }: { repos: Recommendation[]; onDiscover: () => void; onDetail: (repo: Recommendation) => void; onRemove: (name: string) => void }) {
  if (!repos.length) {
    return (
      <div className="page compare-page">
        <section className="page-heading"><div className="kicker">项目对比</div><h1>把候选项目放在一起看</h1><p>从搜索结果中选择最多三个项目，这里不会自动塞入示例数据。</p></section>
        <section className="compare-empty-state"><span>还没有选择项目</span><p>返回候选项目，点击项目左侧的“＋”加入对比。</p><button className="primary-button" onClick={onDiscover}>去选择项目 →</button></section>
      </div>
    );
  }

  const items = repos;
  return (
    <div className="page compare-page">
      <section className="page-heading"><div className="kicker">项目对比</div><h1>并排看清差异</h1><p>综合分只是入口。这里重点比较相关度、维护情况、许可证和主要风险。</p></section>
      <div className="compare-grid">
        <div className="compare-labels"><div className="compare-empty"><span>比较项</span></div>{["综合匹配", "技术相关", "维护活跃", "项目规模", "许可证", "最近推送", "主要风险"].map((label) => <div key={label}>{label}</div>)}</div>
        {items.map((repo, index) => <article className="compare-column" key={repo.full_name}><header><div className="compare-column-head"><small>候选 {index + 1}</small><button onClick={() => onRemove(repo.full_name)} aria-label={`移除 ${repo.full_name}`}>移除</button></div><h3>{repo.full_name}</h3><p>{repo.description}</p></header><div><ScoreDial value={repo.score} small /></div><div><strong>{repo.score_breakdown.relevance?.toFixed(0) ?? "—"}</strong><span>/ 35</span></div><div><strong>{repo.score_breakdown.activity?.toFixed(0) ?? "—"}</strong><span>/ 30</span></div><div><strong>{formatNumber(repo.stars)}</strong><span> Stars</span></div><div><span className="license-badge">{repo.license_spdx}</span></div><div><strong>{repo.pushed_at?.slice(0, 10)}</strong></div><div className="compare-risk">{repo.risks[0]}</div><footer><button onClick={() => onDetail(repo)}>查看项目档案 →</button></footer></article>)}
        {items.length < 3 && <button className="add-column" onClick={onDiscover}>+<span>添加一个候选项目</span></button>}
      </div>
    </div>
  );
}

function EvalsView() {
  const [summary, setSummary] = useState<EvaluationSummary | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "unavailable">("loading");
  const [running, setRunning] = useState(false);

  async function load(method: "GET" | "POST" = "GET") {
    if (method === "POST") setRunning(true);
    try {
      const response = await fetch(method === "GET" ? "/api/v1/evals/summary" : "/api/v1/evals/run", { method });
      if (!response.ok) throw new Error("Evaluation API unavailable");
      setSummary(await response.json() as EvaluationSummary);
      setStatus("ready");
    } catch {
      setStatus("unavailable");
    } finally {
      setRunning(false);
    }
  }

  useEffect(() => { void load(); }, []);

  return (
    <div className="page evals-page">
      <section className="page-heading page-heading--row"><div><div className="kicker">质量记录</div><h1>固定用例的真实结果</h1><p>只展示实际执行过的确定性检查；失败项会直接列出，不用漂亮数字遮住。</p></div><button className="primary-button" onClick={() => load("POST")} disabled={running}>{running ? <><i className="spinner" /> 正在运行</> : "重新运行评测"}</button></section>
      {status === "loading" && <div className="eval-state"><i className="spinner" /> 正在读取评测结果…</div>}
      {status === "unavailable" && <div className="notice"><Signal tone="amber" /><span>评测接口暂不可用。启动后端后即可运行固定用例。</span></div>}
      {summary && <>
        <section className="metric-grid">
          {summary.metrics.map((metric) => <article className="metric-card" key={metric.key}><small>{metric.label}</small><strong>{metric.value}{metric.unit}</strong><span className={metric.passed ? "passed" : "failed"}>{metric.passed ? "达到目标" : "未达到目标"}</span><p>目标 ≥ {metric.target}{metric.unit}</p></article>)}
          <article className="metric-card"><small>固定测试样本</small><strong>{summary.sample_count}</strong><span className="passed">{summary.dataset_version}</span><p>版本 {summary.version}</p></article>
        </section>
        <article className="panel eval-failures"><div className="panel-title"><span>失败样本</span><small>{summary.failures.length ? `${summary.failures.length} 项需要处理` : "全部通过"}</small></div>{summary.failures.length ? summary.failures.map((failure) => <div className="failure-row" key={`${failure.case}-${failure.expected}`}><b>{failure.case}</b><span>期望：{failure.expected}</span><span>实际：{failure.actual}</span></div>) : <p className="eval-success">当前固定用例全部通过。新增解析规则时仍需扩充困难样本。</p>}</article>
      </>}
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<View>("discover");
  const [data, setData] = useState<SearchResponse>(demoResponse);
  const [selectedRepo, setSelectedRepo] = useState<Recommendation>(demoResponse.results[0]);
  const [investigation, setInvestigation] = useState<RepositoryInvestigation | null>(null);
  const [investigationStatus, setInvestigationStatus] = useState<"loading" | "ready" | "unavailable">("unavailable");
  const [issues, setIssues] = useState<ContributionIssue[]>([]);
  const [issueStatus, setIssueStatus] = useState<"loading" | "ready" | "unavailable">("unavailable");
  const [compare, setCompare] = useState<string[]>([]);
  const [fallback, setFallback] = useState(false);
  const [agentRun, setAgentRun] = useState<AgentRunResponse | null>(null);

  async function search(query: string, options: SearchOptions) {
    const recentDate = new Date();
    recentDate.setDate(recentDate.getDate() - 183);
    const requestBody = {
      query,
      limit: 10,
      purpose: options.purpose,
      weekly_hours: options.weeklyHours,
      platform: options.platform,
      project_size: options.projectSize,
      licenses: options.licenses.length ? options.licenses : null,
      pushed_after: options.recentOnly ? recentDate.toISOString().slice(0, 10) : null,
      investigate_limit: 2,
    };
    try {
      const response = await fetch("/api/v1/agent/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
      });
      if (!response.ok) throw new Error("Agent API unavailable");
      const run = await response.json() as AgentRunResponse;
      setAgentRun(run);
      setData(run.search);
      setFallback(false);
    } catch {
      try {
        const response = await fetch("/api/v1/search", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(requestBody),
        });
        if (!response.ok) throw new Error("Search API unavailable");
        setData(await response.json() as SearchResponse);
        setAgentRun(null);
        setFallback(false);
      } catch {
        setData({
          ...demoResponse,
          query,
          constraints: {
            ...demoResponse.constraints,
            purpose: options.purpose,
            weekly_hours: options.weeklyHours,
            platform: options.platform,
            project_size: options.projectSize,
            licenses: options.licenses,
            pushed_after: options.recentOnly ? recentDate.toISOString().slice(0, 10) : null,
          },
        });
        setAgentRun(null);
        setFallback(true);
      }
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
    setIssues([]);
    setIssueStatus("loading");
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

    fetch(`/api/v1/repos/${encodeURIComponent(owner)}/${encodeURIComponent(name)}/issues?limit=5`)
      .then((response) => {
        if (!response.ok) throw new Error("Issue API unavailable");
        return response.json() as Promise<{ issues: ContributionIssue[] }>;
      })
      .then((payload) => {
        setIssues(payload.issues);
        setIssueStatus("ready");
      })
      .catch(() => setIssueStatus("unavailable"));
  }

  async function submitFeedback(action: "helpful" | "not_relevant" | "saved" | "opened_issue") {
    let deviceId: string | null = null;
    try {
      deviceId = getDeviceId();
      const feedbackLog = JSON.parse(localStorage.getItem("openscout:feedback") ?? "[]") as Array<Record<string, string>>;
      localStorage.setItem("openscout:feedback", JSON.stringify([...feedbackLog.slice(-99), { repository: selectedRepo.full_name, action, query: data.query, createdAt: new Date().toISOString() }]));
      if (action === "saved") {
        const stored = JSON.parse(localStorage.getItem("openscout:saved") ?? "[]") as string[];
        localStorage.setItem("openscout:saved", JSON.stringify([...new Set([...stored, selectedRepo.full_name])]));
      }
    } catch {
      // Storage can be unavailable in a locked-down browser; API feedback still proceeds.
    }
    try {
      const requests = [fetch("/api/v1/feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            repository: selectedRepo.full_name,
            action,
            query: data.query,
            session_id: fallback ? null : data.session_id,
            device_id: deviceId,
          }),
        })];
      if (action === "saved" && deviceId) {
        requests.push(fetch("/api/v1/saved", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device_id: deviceId, repository: selectedRepo.full_name }),
        }));
      }
      await Promise.all(requests);
    } catch {
      // Device-local save and immediate UI feedback still work when the API is offline.
    }
  }

  const compareRepos = useMemo(() => data.results.filter((repo) => compare.includes(repo.full_name)), [compare, data.results]);

  return (
    <Shell view={view} setView={setView} compareCount={compare.length}>
      {view === "discover" && <DiscoverView onSearch={search} />}
      {view === "results" && <ResultsView data={data} agentRun={agentRun} compare={compare} toggleCompare={toggleCompare} fallback={fallback} onNewSearch={() => setView("discover")} onDetail={openDetail} />}
      {view === "detail" && <DetailView repo={selectedRepo} investigation={investigation} status={investigationStatus} issues={issues} issueStatus={issueStatus} onBack={() => setView("results")} onCompare={() => toggleCompare(selectedRepo.full_name)} onFeedback={submitFeedback} />}
      {view === "compare" && <CompareView repos={compareRepos} onDiscover={() => setView("results")} onDetail={openDetail} onRemove={toggleCompare} />}
      {view === "evals" && <EvalsView />}
    </Shell>
  );
}
