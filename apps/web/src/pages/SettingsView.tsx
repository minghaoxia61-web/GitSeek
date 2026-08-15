import { FormEvent, useEffect, useState } from "react";

import { apiFetch, checkApiHealth, getApiBaseUrl, getDefaultApiBaseUrl, resetApiBaseUrl, setApiBaseUrl } from "../api";
import { APP_VERSION, checkForUpdates, RELEASES_URL, type ReleaseCheck } from "../appInfo";
import type { ConnectionStatus, RepositoryIndexStatus } from "../lib/types";
import { InstallAppButton, Signal } from "../components/ui";

export function SettingsView({ connection, onApiChanged }: { connection: ConnectionStatus; onApiChanged: () => void }) {
  const [apiBase, setApiBase] = useState(getApiBaseUrl());
  const [saveMessage, setSaveMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [updateResult, setUpdateResult] = useState<ReleaseCheck | null>(null);
  const [updateMessage, setUpdateMessage] = useState("");
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [indexStatus, setIndexStatus] = useState<RepositoryIndexStatus | null>(null);

  useEffect(() => {
    let active = true;
    apiFetch<RepositoryIndexStatus>("/api/v1/index/status")
      .then((payload) => { if (active) setIndexStatus(payload); })
      .catch(() => { if (active) setIndexStatus(null); });
    return () => { active = false; };
  }, [connection.detail]);

  async function saveAndTest(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setSaveMessage("");
    let saved = false;
    try {
      const normalized = setApiBaseUrl(apiBase);
      saved = true;
      setApiBase(normalized);
      onApiChanged();
      const health = await checkApiHealth(normalized);
      setSaveMessage(`连接成功 · ${health.service}${health.environment ? ` · ${health.environment}` : ""}`);
    } catch (error) {
      const detail = error instanceof Error ? error.message : "暂时无法连接";
      setSaveMessage(saved ? `已保存，但检测失败：${detail}` : `无法保存：${detail}`);
    } finally {
      setSaving(false);
    }
  }

  function restoreDefault() {
    const restored = resetApiBaseUrl();
    setApiBase(restored);
    setSaveMessage("已恢复安装包默认地址，正在重新检测连接。");
    onApiChanged();
  }

  async function checkUpdate() {
    setCheckingUpdate(true);
    setUpdateMessage("");
    try {
      const result = await checkForUpdates();
      setUpdateResult(result);
      setUpdateMessage(result.state === "available" ? `发现新版本 ${result.latestVersion}` : result.state === "current" ? "当前已经是最新版本" : "暂时没有发布正式版本");
    } catch (error) {
      setUpdateMessage(error instanceof Error ? error.message : "暂时无法检查更新");
    } finally {
      setCheckingUpdate(false);
    }
  }

  return (
    <div className="page settings-page">
      <section className="page-heading"><div className="kicker">应用设置</div><h1>连接与版本</h1><p>后端地址保存在当前设备上，不会上传；DeepSeek 与 GitHub 密钥仍只存在于云端。</p></section>
      <div className="settings-grid">
        <form className="panel settings-card" onSubmit={saveAndTest}>
          <div className="settings-card-head"><div><small>BACKEND</small><h2>云端服务</h2></div><span className={`connection-badge connection-badge--${connection.state}`}><Signal tone={connection.state === "online" ? "green" : connection.state === "offline" ? "red" : "amber"} />{connection.label}</span></div>
          <label className="settings-field"><span>API 地址</span><input value={apiBase} onChange={(event) => setApiBase(event.target.value)} placeholder="留空表示使用当前站点；桌面版建议填写 https://…" /></label>
          <p className="settings-help">当前默认：{getDefaultApiBaseUrl() || "跟随当前站点"}</p>
          <div className="settings-actions"><button className="primary-button" disabled={saving}>{saving ? "正在检测…" : "保存并检测"}</button><button type="button" className="secondary-button" onClick={restoreDefault}>恢复默认</button></div>
          {saveMessage && <p className="settings-message">{saveMessage}</p>}
        </form>

        <article className="panel settings-card">
          <div className="settings-card-head"><div><small>VERSION</small><h2>GitSeek {APP_VERSION}</h2></div><span className="version-pill">Windows / Web</span></div>
          <p className="settings-copy">手动检查 GitHub Releases。发现新版本时会提供下载入口；正式自动安装将在签名密钥配置后启用。</p>
          <div className="settings-actions"><button className="primary-button" onClick={checkUpdate} disabled={checkingUpdate}>{checkingUpdate ? "正在检查…" : "检查更新"}</button><InstallAppButton /><a className="secondary-button" href={updateResult?.url || RELEASES_URL} target="_blank" rel="noreferrer">查看发布页 ↗</a></div>
          {updateMessage && <p className="settings-message">{updateMessage}</p>}
        </article>

        <article className="panel settings-card settings-card--wide">
          <div className="settings-card-head"><div><small>DIAGNOSTICS</small><h2>连接诊断</h2></div></div>
          <div className="diagnostic-list"><div><span>服务状态</span><b>{connection.label}</b></div><div><span>当前地址</span><b>{getApiBaseUrl() || window.location.origin}</b></div><div><span>最近结果</span><b>{connection.detail}</b></div><div><span>本地索引</span><b>{indexStatus ? indexStatus.storage_status === "unavailable" ? "数据库不可用" : `${indexStatus.repository_count} 个 · ${indexStatus.freshness_state === "fresh" ? "正常" : indexStatus.freshness_state === "stale" ? "待刷新" : indexStatus.freshness_state === "expired" ? "已过期" : "未建立"}` : "暂不可用"}</b>{indexStatus?.stale_repository_count ? <small>{indexStatus.stale_repository_count} 个超过 7 天</small> : null}</div></div>
        </article>
      </div>
    </div>
  );
}
