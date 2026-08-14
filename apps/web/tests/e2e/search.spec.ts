import { expect, test, type Page } from "@playwright/test";

const searchResponse = {
  session_id: "e2e-session",
  query: "适合初学者的 FastAPI 项目",
  generated_github_query: "FastAPI language:Python",
  constraints: {
    purpose: "learning",
    language: "Python",
    technologies: ["FastAPI"],
    licenses: [],
    exclude_archived: true,
    pushed_after: null,
    weekly_hours: null,
    platform: null,
    project_size: null,
  },
  source_total_count: 1234,
  eligible_candidate_count: 1,
  ranking_version: "hybrid-vector-v9",
  results: [{
    rank: 1,
    full_name: "fastapi/fastapi",
    description: "FastAPI framework, easy to learn and ready for production.",
    html_url: "https://github.com/fastapi/fastapi",
    score: 96,
    stars: 100000,
    language: "Python",
    license_spdx: "MIT",
    pushed_at: "2026-08-12T00:00:00Z",
    constraint_match: { language: "MATCH", archived: "MATCH" },
    score_breakdown: { relevance: 35, activity: 25, popularity: 15, metadata: 10, license: 10 },
    reasons: ["主要语言为 Python", "匹配技术栈：FastAPI"],
    risks: ["详细工程信号将在项目档案中核验"],
    retrieval_sources: ["github_live"],
    data_fetched_at: "2026-08-12T00:00:00Z",
    data_valid_until: "2026-08-19T00:00:00Z",
  }],
  retrieval: {
    local_candidates: 0,
    github_candidates: 1,
    github_status: "live",
    index_freshest_at: null,
    embedding_status: "local",
  },
};

async function mockApi(page: Page) {
  await page.route("**/health", (route) => route.fulfill({
    json: { status: "ok", service: "gitseek-api", version: "0.1.0", environment: "test" },
  }));
  await page.route("**/api/v1/index/status", (route) => route.fulfill({
    json: { repository_count: 0, snapshot_count: 0, freshest_at: null, oldest_at: null, stale_repository_count: 0, expired_repository_count: 0, freshness_state: "empty", next_refresh_at: null, ready: false },
  }));
  await page.route("**/api/v1/saved**", (route) => route.fulfill({ json: { repositories: [] } }));
  await page.route("**/api/v1/search", (route) => route.fulfill({ json: searchResponse }));
  await page.route("**/api/v1/repos/fastapi/fastapi/investigate", (route) => route.fulfill({ json: {
    full_name: "fastapi/fastapi",
    description: "FastAPI framework, easy to learn and ready for production.",
    html_url: "https://github.com/fastapi/fastapi",
    default_branch: "master",
    fetched_at: "2026-08-13T00:00:00Z",
    confidence: "high",
    signals: {
      has_readme: true, has_contributing: true, has_code_of_conduct: true,
      has_issue_template: true, has_pull_request_template: true, has_security_policy: true,
      has_license: true, has_tests: true, has_ci: true, has_pyproject: true,
      has_dependency_file: true, has_docker: true, readme_has_quickstart: true,
    },
    scores: { community_health: 95, documentation: 95, engineering: 90, learning_friendliness: 90, maintenance: 85 },
    activity: {
      releases_sampled: 10, latest_release_at: "2026-08-01T00:00:00Z",
      median_release_interval_days: 30, pull_requests_sampled: 20,
      merged_pull_request_ratio: .9, median_pull_request_resolution_hours: 48,
      contributors_sampled: 30, top_contributor_share: .2, contributor_continuity: "distributed",
    },
    evidence: [{ id: "readme", fact: "README detected", value: true, source_url: "https://github.com/fastapi/fastapi#readme", fetched_at: "2026-08-13T00:00:00Z", confidence: "high" }],
    risks: ["开始前确认本地 Python 版本。"],
    limitations: ["只读取公开仓库信息。"],
  } }));
  await page.route("**/api/v1/repos/fastapi/fastapi/issues?limit=5", (route) => route.fulfill({ json: { issues: [] } }));
  await page.route("**/api/v1/agent/runs/stream", async (route) => {
    expect(route.request().postDataJSON()).toMatchObject({ embedding_mode: "local" });
    await route.fulfill({
      contentType: "text/event-stream",
      body: `event: result\ndata: ${JSON.stringify({
      run_id: "e2e-run",
      status: "succeeded",
      created_at: "2026-08-12T00:00:00Z",
      completed_at: "2026-08-12T00:00:01Z",
      retry_count: 0,
      interpretation: { source: "rules", summary: "已识别 FastAPI 学习项目", search_terms: ["FastAPI"] },
      search_plan: [],
      search: searchResponse,
      investigations: [],
      verification: [],
      steps: [],
      })}\n\n`,
    });
  });
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
});

test("starts empty and renders only real search results", async ({ page }) => {
  const query = page.getByRole("textbox", { name: /描述用途/ });
  await expect(query).toHaveValue("");
  await query.fill("适合初学者的 FastAPI 项目");
  await page.getByRole("button", { name: /搜索项目/ }).click();

  await expect(page.getByRole("heading", { name: "1 个项目值得继续看" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "fastapi" })).toBeVisible();
  await expect(page.getByText("默认推荐")).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
});

test("keeps primary navigation usable on a mobile viewport", async ({ page }) => {
  await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
  await page.getByRole("button", { name: "收藏" }).click();
  await expect(page.getByRole("heading", { name: "留着以后再看" })).toBeVisible();
});

test("puts a plain-language decision before detailed repository evidence", async ({ page }) => {
  const query = page.getByRole("textbox", { name: /描述用途/ });
  await query.fill("适合初学者的 FastAPI 项目");
  await page.getByRole("button", { name: /搜索项目/ }).click();
  await page.getByRole("button", { name: /查看档案/ }).click();

  const summary = page.getByRole("region", { name: "项目判断摘要" });
  await expect(summary.getByText("值得继续了解")).toBeVisible();
  await expect(summary.getByText("7 / 7")).toBeVisible();
  await expect(summary.getByText("活跃", { exact: true })).toBeVisible();
});
