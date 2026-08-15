import type { Recommendation } from "../types";
import { DataFreshness } from "./ui";
import { formatNumber } from "../lib/utils";

export function ResultCard({
  repo,
  selected,
  saved,
  onSelect,
  onSave,
  onDetail,
}: {
  repo: Recommendation;
  selected: boolean;
  saved: boolean;
  onSelect: () => void;
  onSave: () => void;
  onDetail: () => void;
}) {
  return (
    <article className="result-card card">
      <div className="result-main">
        <div className="repo-heading">
          <div><span className="result-rank">{String(repo.rank).padStart(2, "0")}</span><span className="repo-owner">{repo.full_name.split("/")[0]} /</span><h3>{repo.full_name.split("/")[1]}</h3></div>
          <strong className="plain-score">{repo.score.toFixed(0)}<small>/100</small></strong>
        </div>
        <p>{repo.description || "这个仓库暂时没有提供简介。"}</p>
        <div className="repo-meta"><span>★ {formatNumber(repo.stars)}</span>{repo.language && <span>{repo.language}</span>}<span>{repo.license_spdx ?? "无许可证"}</span>{repo.pushed_at && <span>更新于 {repo.pushed_at.slice(0, 10)}</span>}</div>
        <div className="evidence-ledger">
          <div><b>推荐</b><span>{repo.reasons.slice(0, 2).join("；")}</span></div>
          <div className="ledger-risk"><b>留意</b><span>{repo.risks[0] || "未发现明显风险，仍建议阅读仓库说明。"}</span></div>
        </div>
        <div className="result-footer">
          <span className="result-provenance">{repo.retrieval_sources?.includes("github_live") ? "GitHub 实时数据" : "已同步索引"}<DataFreshness timestamp={repo.data_fetched_at} validUntil={repo.data_valid_until} /></span>
          <div><button className={`save-toggle ${saved ? "selected" : ""}`} onClick={onSave}>{saved ? "已收藏" : "收藏"}</button><button className={`compare-toggle ${selected ? "selected" : ""}`} onClick={onSelect}>{selected ? "已加入对比" : "加入对比"}</button><button onClick={onDetail}>查看档案 →</button></div>
        </div>
      </div>
    </article>
  );
}
