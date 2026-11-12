# 干净检出验收与受保护测试

日期：2026-10-29。对应优化计划 A6/A7。

## 验收流程

配置了独立验收的任务使用三个不同工作目录：Agent 工作区、修复前基线检出、补丁验收检出。
后两个检出在模型运行前从固定提交创建，不从 Agent 工作区复制修改后的源码或未跟踪文件。

1. 校验固定 commit、环境、依赖锁文件和评测测试包哈希。
2. 将评测方提供的测试包注入基线目录；Agent 工作区中没有这个测试包。
3. 执行基线缺陷测试：要求退出码为 1、没有超时，并出现指定断言失败标记。
4. 执行基线回归测试：要求退出码为 0、没有超时，并出现指定成功标记。
5. 检查基线测试/配置完整性。未复现缺陷、测试导入错误、环境故障或回归失败，都在调用模型前停止。
6. 运行原有 Agent 修复循环及其工作区测试。
7. 检查 Agent 的受保护路径，包括暂存和未跟踪文件；正常生成的字节码缓存不会复制到验收目录。
8. 将最终 diff 正向应用到另一个干净检出，用真实 Git 检查应用结果及改动路径。
9. 拒绝修改受保护路径的补丁，再注入原始测试包，执行相同缺陷测试与回归测试。
10. 重新核对环境、依赖、测试字节完整性与 HEAD，保留命令、退出码、输出摘要和哈希。

成功必须同时满足既有工作区验证门槛和上述独立验收门槛。仅有模型 FINISH、工作区测试通过、
独立缺陷测试通过或单独的 `passed=true` 均不足够。

## 配置

在[固定版本清单](execution-spec.md)的 `execution` 下新增 `acceptance`。
新 benchmark 清单必须提供该字段；旧排队任务与普通产品任务仍可仅生成工作区验证结果。

以下仅为结构模板，测试正文、哈希、命令和标记均需替换成真实值：

```json
{
  "acceptance": {
    "files": [
      {
        "path": "_gitseek_acceptance/test_issue.py",
        "content": "<评测方持有的完整UTF-8测试正文>",
        "sha256": "<content.encode('utf-8')的SHA-256>"
      },
      {
        "path": "_gitseek_acceptance/test_regression.py",
        "content": "<相关回归测试正文>",
        "sha256": "<对应字节哈希>"
      }
    ],
    "target_command": "python -m pytest _gitseek_acceptance/test_issue.py -q",
    "regression_command": "python -m pytest _gitseek_acceptance/test_regression.py -q",
    "failure_marker": "FAILED _gitseek_acceptance/test_issue.py::test_expected_behavior",
    "success_marker": "1 passed",
    "regression_success_marker": "passed",
    "protected_paths": ["custom_checks", "test_settings.json"],
    "timeout_s": 600
  }
}
```

- 测试包目录固定为 `_gitseek_acceptance/`，路径不能越出检出目录，不能覆盖仓库已有文件。
- 文件正文必须与 SHA-256 匹配；测试包最多 100 个文件、UTF-8 总字节数不超过 2 MB。
- `target_command` 在修复前后保持一致；失败标记应对应具体断言失败，不能用泛化的 Traceback 代替。
- 成功标记应证明测试执行，而不是把任意零退出命令当作验证通过。
- `regression_command` 必填，用于拒绝“仅修对一个输入、破坏其他行为”的补丁。
- 测试包不进入代码定位索引、模型提示词或 Agent 工作区。Gold 文件清单仍只由 benchmark 使用。

## 受保护路径

默认保护所有层级的 `tests/`、`test/`、`testing/`、`_gitseek_acceptance/`，
`test_*`、`*_test.py`、`conftest.py`，以及 `pytest.ini`、`tox.ini`、`setup.cfg`、
`pyproject.toml` 和指定依赖锁文件。路径匹配忽略大小写，以覆盖 Windows 路径别名。
项目的其他测试/配置目录必须通过 `protected_paths` 补充。

修改、删除、重命名或新增受保护文件，均会拒绝自动验收；需要合理修改测试或依赖的任务应转入人工审查。
普通运行产生的未跟踪字节码只在检查 Agent 工作区时排除；补丁本身新增的受保护字节码仍检查。
评测执行前后也会比较受保护的已跟踪文件及测试包的字节快照。

## 记录与指标

`result_json.acceptance` / API 的 `acceptance` 包含：

- `version=clean-acceptance-v1`、`scope=clean_checkout_tests`、backend 和是否容器隔离。
- 基线缺陷复现、补丁应用、受保护文件完整性及环境核对状态。
- `baseline_target`、`baseline_regression`、`final_target`、`final_regression` 的命令、实际退出码、超时、时长和标记匹配结果。
- 测试包哈希、补丁哈希、改动路径；各命令保留输出前 8,000 字符及完整合并输出的 SHA-256。

独立验收失败仍保留补丁草稿和工作区测试结果，避免失败证据被成功摘要覆盖。
基线阶段停止时保留已执行命令的结果，不虚构后续检查。

新 benchmark 的 `e2e_success` 要求身份、工作区验证和 `acceptance_passed()` 同时通过。
报告标记 `verification_scope=clean_checkout_tests`、`independent_acceptance=true`，表示采用该验收协议，
不表示所有实例均通过。`local_development_instances` 报告本地模式实例数；逐例 `isolated` 标明容器隔离状态。

页面区分“工作区测试通过”和“干净检出验收通过”；缺少完整验收证据时不会展示后者。

## 运行范围

本地模式只证明工程链路：独立目录不等于安全隔离，同主机进程仍可能访问其他路径。
正式修复实验应使用已固定 digest/平台的 Docker 环境，并在报告中注明环境与实例范围。
本轮回归使用临时 Git 仓库、真实 Python unittest、真实 diff 应用以及固定模型回复，未调用外部模型。
Docker 路径未据此声称已通过真实容器实验，也不构成真实 Issue 修复率提升。

Windows 本地模式优先选择 Git for Windows 的 Bash，而不是 System32 的 WSL 启动器，
以匹配被记录的宿主 Python/路径；本地运行时指纹同步反映实际 Shell。旧本地清单须重新生成指纹。

A6/A7 验收规范和结果使用已有 JSON 字段。后续 A8 允许费用未知的迁移为 `20261029_0012`，
运行最新版 worker 前需升级到当前 head，详见[运行证据说明](run-evidence.md)。

## 本轮验证

- 全量后端：210 项通过（180.99 秒）。
- 浏览器：7 种验收/历史状态，桌面与移动端共 14 项通过。
- 前端类型检查与生产构建、变更 Python Ruff 和差异空白检查通过。
- 真实局部实验已验证“基线断言失败 → 正确补丁 → 缺陷与回归通过”，以及“表面修复通过目标测试但回归失败 → 拒绝验收”。
- 尚未据此运行或发布真实 Issue 的模型成功率、Docker 实验结果或官方基准成绩。
