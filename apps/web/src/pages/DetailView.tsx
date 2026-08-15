import { useState } from "react";

import type { ContributionIssue, Recommendation, RepositoryInvestigation } from "../types";
import { formatNumber } from "../lib/utils";
import { DataFreshness, ScoreDial, Signal } from "../components/ui";

export function DetailView({
  repo,
  investigation,
  status,
  issues,
  issueStatus,
  onBack,
  onCompare,
  onRefresh,
  onFeedback,
}: {
  repo: Recommendation;
  investigation: RepositoryInvestigation | null;
  status: "loading" | "ready" | "unavailable";
  issues: ContributionIssue[];
  issueStatus: "loading" | "ready" | "unavailable";
  onBack: () => void;
  onCompare: () => void;
  onRefresh: () => void;
  onFeedback: (action: "helpful" | "not_relevant" | "saved" | "opened_issue", reason?: string) => Promise<void>;
}) {
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const [showFeedbackReasons, setShowFeedbackReasons] = useState(false);
  const scores = investigation?.scores;
  const dossierScore = scores
    ? (scores.documentation + scores.engineering + scores.learning_friendliness + (scores.maintenance ?? scores.community_health)) / 4
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
    ["维护状态", scores?.maintenance ?? 0],
  ] as const;
  const risks = investigation?.risks ?? repo.risks;
  const activity = investigation?.activity;
  const verifiedSignalCount = signalRows.filter(([, value]) => value === true).length;
  const decisionTitle = status !== "ready"
    ? "等待仓库核验"
    : dossierScore >= 75 && risks.length <= 2
      ? "值得继续了解"
      : dossierScore >= 55
        ? "可以尝试，先确认风险"
        : "暂不建议直接投入";
  const decisionCopy = status !== "ready"
    ? "先保留搜索阶段判断，核验完成后再决定是否投入时间。"
    : signals?.has_contributing && signals.readme_has_quickstart
      ? "入门路径比较清楚，先按贡献指南完成一次本地运行。"
      : "项目仍可查看，但开始前需要自己补齐环境与贡献步骤。";
  const maintenanceLabel = !activity
    ? "等待数据"
    : (scores?.maintenance ?? 0) >= 70
      ? "活跃"
      : (scores?.maintenance ?? 0) >= 45
        ? "一般"
        : "需确认";

  async function feedback(action: "helpful" | "not_relevant" | "saved", reason?: string) {
    await onFeedback(action, reason);
    setShowFeedbackReasons(false);
    setFeedbackMessage(action === "helpful" ? "已记录：推荐有帮助" : action === "saved" ? "已收藏到当前设备" : "已记录，我们会把它作为失败样本检查");
  }

  return (
    <div className="page detail-page">
      <button className="back-button" onClick={onBack}>← 返回调查结果</button>
      <section className="detail-hero">
        <div className="repo-monogram">{repo.full_name.split("/")[1].slice(0, 2).toUpperCase()}</div>
        <div className="detail-title">
          <div className="kicker">{status === "loading" ? "正在读取仓库信息" : status === "ready" ? `项目档案 · ${investigation?.confidence === "high" ? "高" : investigation?.confidence === "medium" ? "中" : "低"}置信度` : "项目档案 · 搜索阶段数据"}</div>
          <h1>{repo.full_name}</h1>
          <p>{investigation?.description ?? repo.description}</p>
          <div className="repo-meta"><span>★ {formatNumber(repo.stars)}</span>{repo.language && <span>{repo.language}</span>}{repo.license_spdx && <span>{repo.license_spdx}</span>}<span>Default · {investigation?.default_branch ?? "main"}</span><DataFreshness timestamp={investigation?.fetched_at ?? repo.data_fetched_at} validUntil={investigation ? null : repo.data_valid_until} /></div>
        </div>
        <ScoreDial value={dossierScore} />
        <div className="detail-actions"><button className="secondary-button" onClick={onRefresh} disabled={status === "loading" || issueStatus === "loading"}>{status === "loading" || issueStatus === "loading" ? "正在核验…" : "重新核验"}</button><button className="secondary-button" onClick={onCompare}>加入对比</button><button className="secondary-button" onClick={() => feedback("saved")}>收藏项目</button><a className="primary-button" href={repo.html_url} target="_blank" rel="noreferrer">打开 GitHub ↗</a></div>
      </section>

      {status === "loading" && <div className="detail-status"><i className="spinner" /> 正在读取社区档案、仓库目录、工作流和 README…</div>}
      {status === "unavailable" && <div className="notice"><Signal tone="amber" /><span>实时调查接口暂不可用，当前保留搜索阶段数据；本地 API 启动后重新打开档案即可恢复真实证据。</span></div>}

      <section className="decision-brief" aria-label="项目判断摘要">
        <div className="decision-verdict">
          <small>当前建议</small>
          <strong>{decisionTitle}</strong>
          <p>{decisionCopy}</p>
        </div>
        <dl>
          <div><dt>已验证信号</dt><dd>{status === "ready" ? `${verifiedSignalCount} / ${signalRows.length}` : "—"}</dd></div>
          <div><dt>维护状态</dt><dd>{maintenanceLabel}</dd></div>
          <div><dt>首要注意</dt><dd>{risks[0] ?? "暂未发现明显阻碍"}</dd></div>
        </dl>
      </section>

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

          <article className="panel start-path-panel">
            <div className="panel-title"><span>建议开始方式</span><small>开始前仍需人工确认</small></div>
            <ol>
              <li><b>先确认项目是否适合你</b><p>{signals?.has_readme ? "阅读 README 的用途、安装条件和快速开始。" : "仓库未检测到明确 README，先查看项目首页与最近活动。"}</p></li>
              <li><b>再准备本地环境</b><p>{signals?.has_contributing ? "按贡献指南准备环境；只复制你理解并确认安全的命令。" : "未发现贡献指南，先从文档和依赖文件确认环境，不要直接运行陌生脚本。"}</p></li>
              <li><b>最后选择一个小任务</b><p>{issues.length ? `优先查看下方 ${issues.length} 个未认领候选，并在开始前确认仍为开放状态。` : "当前没有可靠候选 Issue，可以先阅读讨论区或从文档改进开始。"}</p></li>
            </ol>
          </article>

          <article className="panel activity-panel">
            <div className="panel-title"><span>维护活动</span><small>GitHub 公开样本</small></div>
            <div className="activity-grid">
              <div><span>最近发布</span><strong>{activity?.latest_release_at?.slice(0, 10) ?? "未发现"}</strong><small>{activity?.median_release_interval_days != null ? `发布间隔中位数 ${activity.median_release_interval_days} 天` : `${activity?.releases_sampled ?? 0} 个正式版本样本`}</small></div>
              <div><span>PR 处理</span><strong>{activity?.median_pull_request_resolution_hours != null ? `${Math.round(activity.median_pull_request_resolution_hours / 24)} 天` : "未知"}</strong><small>{activity?.merged_pull_request_ratio != null ? `${Math.round(activity.merged_pull_request_ratio * 100)}% 样本已合并` : `${activity?.pull_requests_sampled ?? 0} 个关闭 PR 样本`}</small></div>
              <div><span>贡献连续性</span><strong>{activity?.contributor_continuity === "distributed" ? "较分散" : activity?.contributor_continuity === "concentrated" ? "较集中" : "未知"}</strong><small>{activity?.contributors_sampled ? `${activity.contributors_sampled} 位贡献者样本` : "样本不足"}</small></div>
            </div>
          </article>

          <article className="panel issues-panel">
            <div className="panel-title"><span>适合开始的 Issue</span><small>{issueStatus === "ready" ? `${issues.length} 个候选` : issueStatus === "loading" ? "正在刷新状态" : "暂不可用"}</small></div>
            {issueStatus === "loading" && <div className="issues-loading"><i className="spinner" /> 正在检查开放状态、认领情况与任务描述…</div>}
            {issueStatus === "ready" && issues.map((issue) => <a className="issue-row" href={issue.html_url} target="_blank" rel="noreferrer" key={issue.number} onClick={() => onFeedback("opened_issue")}><span className={`difficulty ${issue.difficulty}`}>{issue.difficulty === "easy" ? "容易" : issue.difficulty === "medium" ? "中等" : "较难"}</span><div><b>#{issue.number} {issue.title}</b><p>{issue.reasons.join(" · ")}{issue.risks[0] ? `；${issue.risks[0]}` : ""}</p></div><strong>{issue.score.toFixed(0)}</strong></a>)}
            {issueStatus === "ready" && !issues.length && <p className="empty-copy">当前没有找到未认领且信息足够的开放 Issue。GitSeek 不会为了填满列表推荐不确定任务。</p>}
            {issueStatus === "unavailable" && <p className="empty-copy">Issue 状态暂时无法刷新，请稍后再试或直接到 GitHub 查看。</p>}
          </article>
        </section>

        <aside className="detail-side">
          <article className="panel"><div className="panel-title"><span>工程信号</span><small>仓库文件检查</small></div>{signalRows.map(([label, value]) => <div className="audit-row" key={label}><Signal tone={value === undefined ? "amber" : value ? "green" : "red"} /><span>{label}</span><b>{value === undefined ? "读取中" : value ? "已发现" : "未发现"}</b></div>)}</article>
          <article className="panel risk-panel"><div className="panel-title"><span>开始前留意</span><small>已知风险</small></div>{risks.length ? risks.map((risk, index) => <div key={risk}><b>0{index + 1}</b><p>{risk}</p></div>) : <p className="empty-copy">当前规则未发现显著风险，仍建议阅读原始贡献说明。</p>}</article>
          <article className="panel path-card"><small>检查范围</small><strong>只读取公开信息</strong><p>{investigation?.limitations[0] ?? "连接调查接口后，这里会显示本次检查没有覆盖的内容。"}</p><a href={repo.html_url} target="_blank" rel="noreferrer">到 GitHub 人工确认 →</a></article>
          <article className="panel feedback-card"><div className="panel-title"><span>这条推荐怎么样？</span><small>反馈用于回归检查</small></div><div><button onClick={() => feedback("helpful")}>有帮助</button><button onClick={() => setShowFeedbackReasons((current) => !current)}>不太相关</button></div>{showFeedbackReasons && <div className="feedback-reasons" aria-label="不相关原因">{["技术不符", "项目停更", "难度太高", "许可证问题", "没有合适 Issue", "其他"].map((reason) => <button key={reason} onClick={() => feedback("not_relevant", reason)}>{reason}</button>)}</div>}{feedbackMessage && <p>{feedbackMessage}</p>}</article>
        </aside>
      </div>
    </div>
  );
}
