import type { Recommendation } from "../types";
import type { SavedEntry } from "../lib/types";
import { formatNumber, savedEntryAsRecommendation } from "../lib/utils";

export function SavedView({
  entries,
  onOpen,
  onRemove,
  onDiscover,
}: {
  entries: SavedEntry[];
  onOpen: (repo: Recommendation) => void;
  onRemove: (repository: string) => void;
  onDiscover: () => void;
}) {
  return (
    <div className="page saved-page">
      <section className="page-heading page-heading--row">
        <div><div className="kicker">Saved repositories</div><h1>留着以后再看</h1><p>收藏保存在当前设备，并在云端服务可用时同步。</p></div>
        <button className="primary-button" onClick={onDiscover}>继续找项目</button>
      </section>
      {!entries.length ? (
        <section className="compare-empty-state"><span>还没有收藏项目</span><p>搜索后可以直接收藏候选项目，不必先打开详情页。</p><button className="primary-button" onClick={onDiscover}>去搜索项目 →</button></section>
      ) : (
        <section className="saved-list" aria-label="收藏的项目">
          <div className="saved-list-head"><span>{entries.length} 个项目</span><small>DEVICE LIBRARY</small></div>
          {entries.map((entry, index) => {
            const repo = savedEntryAsRecommendation(entry);
            return <article className="saved-row" key={entry.repository}>
              <span className="saved-index">{String(index + 1).padStart(2, "0")}</span>
              <div className="saved-summary"><h2>{entry.repository}</h2><p>{repo.description}</p><div>{repo.language && <span>{repo.language}</span>}{repo.license_spdx && <span>{repo.license_spdx}</span>}{repo.stars > 0 && <span>★ {formatNumber(repo.stars)}</span>}<span>{entry.savedAt ? `收藏于 ${entry.savedAt.slice(0, 10)}` : "已从旧版本恢复"}</span></div></div>
              <div className="saved-actions"><button onClick={() => onOpen(repo)}>查看档案</button><a href={repo.html_url} target="_blank" rel="noreferrer">GitHub ↗</a><button className="remove-action" onClick={() => onRemove(entry.repository)}>移除</button></div>
            </article>;
          })}
        </section>
      )}
    </div>
  );
}
