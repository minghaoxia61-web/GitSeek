import { useEffect, useMemo, useRef, useState } from "react";

import { apiFetch, checkApiHealth, streamAgentRun } from "./api";
import type { AgentRunResponse, AgentStep, ContributionIssue, Recommendation, RepositoryInvestigation, SearchResponse, View } from "./types";
import type { ConnectionStatus, SavedEntry, SearchHistoryEntry, SearchOptions, SearchProblem, SearchAttempt } from "./lib/types";
import {
  DEFAULT_SEARCH_OPTIONS,
  emptySearchResponse,
  getDeviceId,
  persistSavedEntries,
  persistSearchHistory,
  problemFrom,
  readSavedEntries,
  readSearchHistory,
} from "./lib/utils";
import { Shell } from "./pages/Shell";
import { DiscoverView } from "./pages/DiscoverView";
import { ResultsView } from "./pages/ResultsView";
import { DetailView } from "./pages/DetailView";
import { CompareView } from "./pages/CompareView";
import { EvalsView } from "./pages/EvalsView";
import { SavedView } from "./pages/SavedView";
import { SettingsView } from "./pages/SettingsView";

export default function App() {
  const [view, setView] = useState<View>("discover");
  const [data, setData] = useState<SearchResponse>(() => emptySearchResponse("", DEFAULT_SEARCH_OPTIONS, null));
  const [selectedRepo, setSelectedRepo] = useState<Recommendation | null>(null);
  const [detailParent, setDetailParent] = useState<"discover" | "results" | "saved">("results");
  const [investigation, setInvestigation] = useState<RepositoryInvestigation | null>(null);
  const [investigationStatus, setInvestigationStatus] = useState<"loading" | "ready" | "unavailable">("unavailable");
  const [issues, setIssues] = useState<ContributionIssue[]>([]);
  const [issueStatus, setIssueStatus] = useState<"loading" | "ready" | "unavailable">("unavailable");
  const [compare, setCompare] = useState<string[]>([]);
  const [savedEntries, setSavedEntries] = useState<SavedEntry[]>(readSavedEntries);
  const [searchHistory, setSearchHistory] = useState<SearchHistoryEntry[]>(readSearchHistory);
  const [searchDraft, setSearchDraft] = useState<{ query: string; options: SearchOptions }>({ query: "", options: DEFAULT_SEARCH_OPTIONS });
  const [agentRun, setAgentRun] = useState<AgentRunResponse | null>(null);
  const [agentProgress, setAgentProgress] = useState<AgentStep[]>([]);
  const [searchProblem, setSearchProblem] = useState<SearchProblem | null>(null);
  const [searchNotice, setSearchNotice] = useState<string | null>(null);
  const [apiRevision, setApiRevision] = useState(0);
  const [connection, setConnection] = useState<ConnectionStatus>({ state: "checking", label: "正在连接", detail: "正在检测云端服务" });
  const searchSequence = useRef(0);
  const agentController = useRef<AbortController | null>(null);

  useEffect(() => {
    let active = true;
    async function refreshConnection(showChecking = false) {
      if (showChecking) setConnection({ state: "checking", label: "正在连接", detail: "正在检测云端服务" });
      const started = performance.now();
      try {
        const health = await checkApiHealth();
        if (!active) return;
        setConnection({ state: "online", label: "服务已连接", detail: `${health.service} · ${Math.round(performance.now() - started)}ms`, embeddingConfigured: health.embedding_configured, embeddingModel: health.embedding_model });
      } catch (error) {
        if (!active) return;
        setConnection({ state: "offline", label: "服务未连接", detail: error instanceof Error ? error.message : "连接检测失败" });
      }
    }
    void refreshConnection(true);
    const timer = window.setInterval(() => void refreshConnection(), 60_000);
    return () => { active = false; window.clearInterval(timer); };
  }, [apiRevision]);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "auto" });
  }, [view]);

  useEffect(() => {
    let active = true;
    try {
      const deviceId = getDeviceId();
      apiFetch<{ repositories: string[] }>(`/api/v1/saved?device_id=${encodeURIComponent(deviceId)}`)
        .then((payload) => {
          if (!active) return;
          setSavedEntries((current) => {
            const known = new Set(current.map((item) => item.repository));
            const merged = [...current, ...payload.repositories.filter((repository) => !known.has(repository)).map((repository) => ({ repository, savedAt: null, snapshot: null }))];
            try { persistSavedEntries(merged); } catch { /* Keep the in-memory list when storage is unavailable. */ }
            return merged;
          });
        })
        .catch(() => undefined);
    } catch {
      // Private browsing can disable storage; local UI remains usable for this session.
    }
    return () => { active = false; };
  }, [apiRevision]);

  function rememberSearch(query: string, options: SearchOptions, resultCount: number) {
    const entry: SearchHistoryEntry = { query, options, resultCount, searchedAt: new Date().toISOString() };
    setSearchHistory((current) => {
      const next = [entry, ...current.filter((item) => item.query !== query)].slice(0, 8);
      try { persistSearchHistory(next); } catch { /* Search still works when storage is unavailable. */ }
      return next;
    });
  }

  async function search(query: string, options: SearchOptions) {
    agentController.current?.abort();
    const controller = new AbortController();
    agentController.current = controller;
    const sequence = searchSequence.current + 1;
    searchSequence.current = sequence;
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
      live_query_limit: 1,
      embedding_mode: "local",
      device_id: getDeviceId(),
    };
    const pushedAfter = options.recentOnly ? recentDate.toISOString().slice(0, 10) : null;
    setSearchDraft({ query, options });
    setSearchProblem(null);
    setSearchNotice(null);
    setAgentProgress([]);
    const basePromise = apiFetch<SearchResponse>("/api/v1/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
    });
    const agentPromise = streamAgentRun(
      {
        ...requestBody,
        live_query_limit: 3,
        embedding_mode: connection.embeddingConfigured ? "external" : "local",
        investigate_limit: 0,
      },
      (step) => {
        if (sequence !== searchSequence.current) return;
        setSearchNotice(null);
        setAgentProgress((current) => [...current, step]);
      },
      controller.signal,
    );
    const baseAttempt: Promise<SearchAttempt> = basePromise.then(
      (response) => ({ kind: "base", response }),
      (error) => ({ kind: "base-error", error }),
    );
    const agentAttempt: Promise<SearchAttempt> = agentPromise.then(
      (run) => ({ kind: "agent", run }),
      (error) => ({ kind: "agent-error", error }),
    );

    let first = await Promise.race([baseAttempt, agentAttempt]);
    if (first.kind === "base-error") first = await agentAttempt;
    else if (first.kind === "agent-error") first = await baseAttempt;
    if (sequence !== searchSequence.current) return;

    if (first.kind === "agent") {
      setAgentRun(first.run);
      setAgentProgress([]);
      setData(first.run.search);
      rememberSearch(query, options, first.run.search.results.length);
      setView("results");
      return;
    }
    if (first.kind === "base") {
      setData(first.response);
      setAgentRun(null);
      rememberSearch(query, options, first.response.results.length);
      setSearchNotice("已先显示快速结果，正在后台补充语义分析…");
      setView("results");
      void agentPromise.then((run) => {
        if (sequence !== searchSequence.current) return;
        setAgentRun(run);
        setAgentProgress([]);
        setData(run.search);
        setSearchNotice(null);
      }).catch((error) => {
        if (sequence !== searchSequence.current) return;
        if (error instanceof DOMException && error.name === "AbortError") {
          setAgentProgress([]);
          setSearchNotice("已停止后台语义优化，当前快速结果仍可继续使用。");
          return;
        }
        const problem = problemFrom(error);
        setAgentProgress([]);
        setSearchNotice(problem.kind === "rate_limit" ? "快速结果已显示；智能解析当前达到限额。" : "快速结果已显示；智能解析暂时不可用。");
      });
      return;
    }

    const failure = first.error;
    setData(emptySearchResponse(query, options, pushedAfter));
    setAgentRun(null);
    setSearchProblem(problemFrom(failure));
    setView("results");
  }

  function toggleCompare(name: string) {
    setCompare((current) => current.includes(name) ? current.filter((item) => item !== name) : current.length < 3 ? [...current, name] : current);
  }

  function refreshDetail(repo: Recommendation, force = false) {
    setInvestigation(null);
    setInvestigationStatus("loading");
    setIssues([]);
    setIssueStatus("loading");
    setView("detail");
    const [owner, name] = repo.full_name.split("/");
    apiFetch<RepositoryInvestigation>(`/api/v1/repos/${encodeURIComponent(owner)}/${encodeURIComponent(name)}/investigate${force ? "?refresh=true" : ""}`)
      .then((payload) => {
        setInvestigation(payload);
        setInvestigationStatus("ready");
      })
      .catch(() => setInvestigationStatus("unavailable"));

    apiFetch<{ issues: ContributionIssue[] }>(`/api/v1/repos/${encodeURIComponent(owner)}/${encodeURIComponent(name)}/issues?limit=5${force ? "&refresh=true" : ""}`)
      .then((payload) => {
        setIssues(payload.issues);
        setIssueStatus("ready");
      })
      .catch(() => setIssueStatus("unavailable"));
  }

  function openDetail(repo: Recommendation) {
    setSelectedRepo(repo);
    setView("detail");
    refreshDetail(repo);
  }

  async function recordFeedback(repo: Recommendation, action: "helpful" | "not_relevant" | "saved" | "opened_issue", reason?: string) {
    let deviceId: string | null = null;
    try {
      deviceId = getDeviceId();
      const feedbackLog = JSON.parse(localStorage.getItem("gitseek:feedback") ?? localStorage.getItem("openscout:feedback") ?? "[]") as Array<Record<string, string>>;
      localStorage.setItem("gitseek:feedback", JSON.stringify([...feedbackLog.slice(-99), { repository: repo.full_name, action, reason: reason ?? "", query: data.query, createdAt: new Date().toISOString() }]));
    } catch {
      // Storage can be unavailable in a locked-down browser; API feedback still proceeds.
    }
    try {
      await apiFetch<unknown>("/api/v1/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repository: repo.full_name, action, reason: reason || null, query: data.query, session_id: data.session_id || null, device_id: deviceId }),
      });
    } catch {
      // Immediate UI feedback still works when the API is offline.
    }
  }

  async function saveRepository(repo: Recommendation) {
    const entry: SavedEntry = { repository: repo.full_name, savedAt: new Date().toISOString(), snapshot: repo };
    setSavedEntries((current) => {
      const next = [entry, ...current.filter((item) => item.repository !== repo.full_name)];
      try { persistSavedEntries(next); } catch { /* Keep the in-memory list when storage is unavailable. */ }
      return next;
    });
    await recordFeedback(repo, "saved");
    try {
      const deviceId = getDeviceId();
      await apiFetch<unknown>("/api/v1/saved", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ device_id: deviceId, repository: repo.full_name }) });
    } catch {
      // The local save is authoritative while offline and will remain visible.
    }
  }

  async function removeSavedRepository(repository: string) {
    setSavedEntries((current) => {
      const next = current.filter((item) => item.repository !== repository);
      try { persistSavedEntries(next); } catch { /* Keep the in-memory list when storage is unavailable. */ }
      return next;
    });
    try {
      const deviceId = getDeviceId();
      const [owner, name] = repository.split("/");
      await apiFetch<unknown>(`/api/v1/saved/${encodeURIComponent(owner)}/${encodeURIComponent(name)}?device_id=${encodeURIComponent(deviceId)}`, { method: "DELETE" });
    } catch {
      // Removing locally still works when the API is offline.
    }
  }

  async function submitFeedback(action: "helpful" | "not_relevant" | "saved" | "opened_issue", reason?: string) {
    if (!selectedRepo) return;
    if (action === "saved") await saveRepository(selectedRepo);
    else await recordFeedback(selectedRepo, action, reason);
  }

  const compareRepos = useMemo(() => compare.map((name) => data.results.find((repo) => repo.full_name === name) ?? savedEntries.find((entry) => entry.repository === name)?.snapshot).filter((repo): repo is Recommendation => Boolean(repo)), [compare, data.results, savedEntries]);

  return (
    <Shell view={view} setView={setView} compareCount={compare.length} savedCount={savedEntries.length} hasResults={Boolean(data.query)} detailParent={detailParent} connection={connection}>
      {view === "discover" && <DiscoverView onSearch={search} onOpenTrending={(repo) => { setDetailParent("discover"); openDetail(repo); }} initialQuery={searchDraft.query} initialOptions={searchDraft.options} history={searchHistory} />}
      {view === "results" && <ResultsView data={data} agentRun={agentRun} agentProgress={agentProgress} compare={compare} saved={savedEntries.map((item) => item.repository)} toggleCompare={toggleCompare} onSave={(repo) => void (savedEntries.some((item) => item.repository === repo.full_name) ? removeSavedRepository(repo.full_name) : saveRepository(repo))} problem={searchProblem} notice={searchNotice} onCancelAgent={() => agentController.current?.abort()} onNewSearch={() => setView("discover")} onDetail={(repo) => { setDetailParent("results"); openDetail(repo); }} />}
      {view === "saved" && <SavedView entries={savedEntries} onOpen={(repo) => { setDetailParent("saved"); openDetail(repo); }} onRemove={(repository) => void removeSavedRepository(repository)} onDiscover={() => setView("discover")} />}
      {view === "detail" && selectedRepo && <DetailView repo={selectedRepo} investigation={investigation} status={investigationStatus} issues={issues} issueStatus={issueStatus} onBack={() => setView(detailParent)} onCompare={() => toggleCompare(selectedRepo.full_name)} onRefresh={() => refreshDetail(selectedRepo, true)} onFeedback={submitFeedback} />}
      {view === "compare" && <CompareView repos={compareRepos} onDiscover={() => setView(data.query ? "results" : "discover")} onDetail={(repo) => { setDetailParent(data.query ? "results" : "saved"); openDetail(repo); }} onRemove={toggleCompare} />}
      {view === "evals" && <EvalsView />}
      {view === "settings" && <SettingsView connection={connection} onApiChanged={() => setApiRevision((current) => current + 1)} />}
    </Shell>
  );
}
