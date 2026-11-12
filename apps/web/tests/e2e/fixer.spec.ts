import { expect, test } from "@playwright/test";

const verification = {
  version: "fixer-verification-v1", scope: "workspace_tests",
  model_finished: true, patch_present: true, apply_ok: true,
  test_executed: true, test_ok: true, test_exit_code: 0, test_timed_out: false,
};

const passedCommand = { exit_code: 0, timed_out: false, marker_found: true };
const acceptance = {
  version: "clean-acceptance-v1", scope: "clean_checkout_tests", backend: "local",
  isolated: false, passed: true, baseline_reproduced: true, patch_applied: true,
  protected_files_unchanged: true, environment_verified: true,
  baseline_target: { ...passedCommand, exit_code: 1 }, baseline_regression: passedCommand,
  final_target: passedCommand, final_regression: passedCommand,
};

for (const scenario of [
  { name: "verified", status: "succeeded", success: true, evidence: verification, category: null, label: "工作区测试通过" },
  { name: "missing-test", status: "failed", success: false, evidence: { ...verification, test_executed: false, test_ok: null, test_exit_code: null }, category: "test_not_configured", label: "结果待验证" },
  { name: "failed-test", status: "failed", success: false, evidence: { ...verification, test_ok: false, test_exit_code: 7 }, category: "patch_logic_error", label: "验证未通过" },
  { name: "legacy", status: "succeeded", success: true, evidence: null, category: null, label: "结果待验证" },
  { name: "clean-accepted", status: "succeeded", success: true, evidence: verification, acceptance, category: null, label: "干净检出验收通过" },
  { name: "protected-tests", status: "failed", success: false, evidence: verification, acceptance: { ...acceptance, passed: false, protected_files_unchanged: false }, category: "protected_test_modified", label: "验证未通过" },
  { name: "incomplete-acceptance", status: "succeeded", success: true, evidence: verification, acceptance: { ...acceptance, final_regression: undefined }, category: null, label: "工作区测试通过" },
]) {
  test(`fixer shows evidence-based state: ${scenario.name}`, async ({ page }) => {
    await page.route("**/health", (route) => route.fulfill({ json: { status: "ok" } }));
    await page.route("**/api/v1/**", (route) => route.fulfill({ json: { results: [], repositories: [] } }));
    const run = {
      run_id: "test-run", repo_full_name: "owner/repo", issue_number: 1,
      status: scenario.status, success: scenario.success, model: "stub-model",
      max_rounds: 5, token_budget: 10000, rounds: 2, token_in: 10, token_out: 5,
      cost_usd: 0, step_count: 0, summary: "MODEL CLAIMS FIXED",
      error: null, failure_category: scenario.category, verification: scenario.evidence,
      acceptance: scenario.acceptance ?? null,
    };
    await page.route("**/api/v1/fixer/runs", (route) => route.fulfill({ json: { ...run, status: "queued" } }));
    await page.route("**/api/v1/fixer/runs/test-run/timeline**", (route) => route.fulfill({ json: { run, steps: [] } }));
    await page.goto("/");
    await page.getByRole("button", { name: "修复 Agent", exact: true }).click();
    await page.getByPlaceholder("例如 langchain-ai/langchain").fill("owner/repo");
    await page.getByPlaceholder("https://github.com/owner/repo/issues/123").fill("https://github.com/owner/repo/issues/1");
    await page.getByRole("button", { name: "运行修复 Agent", exact: true }).click();
    await expect(page.locator(".fixer-status")).toHaveText(scenario.label);
    await expect(page.getByText("费用未知", { exact: true })).toBeVisible();
    if (scenario.acceptance) {
      await expect(page.getByText("本次为本地开发验证，没有容器隔离。补丁仍需审查。")).toBeVisible();
    } else if (scenario.evidence) {
      await expect(page.getByText("独立干净环境验收尚未执行，补丁仍需审查。")).toBeVisible();
    }
    if (scenario.category) {
      await expect(page.getByText("MODEL CLAIMS FIXED", { exact: true })).toHaveCount(0);
    }
  });
}

for (const cost of [
  { name: "unknown", value: null, subtotal: 0.002, label: "费用未知" },
  { name: "explicit-free", value: 0, subtotal: 0, label: "调用估算 $0.0000" },
  { name: "priced", value: 0.0123, subtotal: 0.0123, label: "调用估算 $0.0123" },
  { name: "small-positive", value: 0.00002, subtotal: 0.00002, label: "调用估算 $0.000020" },
]) {
  test(`fixer distinguishes billing state: ${cost.name}`, async ({ page }) => {
    await page.route("**/health", (route) => route.fulfill({ json: { status: "ok" } }));
    await page.route("**/api/v1/**", (route) => route.fulfill({ json: { results: [], repositories: [] } }));
    const run = {
      run_id: "cost-run", status: "failed", success: false, repo_full_name: "owner/repo",
      issue_number: 1, max_rounds: 5, rounds: 1, token_budget: 10000, token_in: 10, token_out: 5,
      cost_usd: cost.value, failure_category: "model_error", summary: "stopped", step_count: 0,
      billing: { version: "provider-billing-v1", state: cost.value === null ? "unknown" : "known",
        estimated_cost_usd: cost.value, known_cost_subtotal_usd: cost.subtotal,
        unknown_usage_calls: cost.value === null ? 1 : 0 },
    };
    await page.route("**/api/v1/fixer/runs", (route) => route.fulfill({ json: { ...run, status: "queued" } }));
    await page.route("**/api/v1/fixer/runs/cost-run/timeline**", (route) => route.fulfill({ json: { run, steps: [] } }));
    await page.goto("/");
    await page.getByRole("button", { name: "修复 Agent", exact: true }).click();
    await page.getByPlaceholder("例如 langchain-ai/langchain").fill("owner/repo");
    await page.getByPlaceholder("https://github.com/owner/repo/issues/123").fill("https://github.com/owner/repo/issues/1");
    await page.getByRole("button", { name: "运行修复 Agent", exact: true }).click();
    await expect(page.getByText(cost.label, { exact: true })).toBeVisible();
    if (cost.value === null) {
      await expect(page.getByText("已知部分 $0.0020", { exact: true })).toBeVisible();
      await expect(page.getByText("调用估算 $0.0000", { exact: true })).toHaveCount(0);
    }
  });
}
