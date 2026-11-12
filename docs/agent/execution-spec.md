# 固定版本与环境的修复评测

日期：2026-10-28，更新于 2026-10-29。适用范围：优化计划 A4/A5；A6/A7 已增加[干净检出验收](clean-acceptance.md)。

## 评测清单

每个实例必须包含 `test_command` 和 `execution`。以下是结构模板，占位内容需替换为实际值，不能直接运行：

新 benchmark 还必须在 `execution` 中提供 `acceptance`，其完整结构见[验收规范](clean-acceptance.md)。
下面片段只展示版本与环境部分，单独复制不能运行完整评测。

```json
[
  {
    "instance_id": "owner__repo-123",
    "repo": "owner/repo",
    "issue_number": 123,
    "gold_files": ["src/module.py"],
    "test_command": "python -m pytest tests/test_module.py -x",
    "execution": {
      "dataset_version": "good-first-issues-v1",
      "base_commit": "<完整小写 commit SHA>",
      "environment": {
        "backend": "docker",
        "image": "<预先准备的镜像>@sha256:<64位小写十六进制摘要>",
        "platform": "linux/amd64"
      },
      "dependency_lock": {
        "path": "requirements.lock",
        "sha256": "<该文件原始字节的64位SHA-256>"
      }
    }
  }
]
```

- `base_commit` 必须是完整的 40 或 64 位小写十六进制提交哈希；分支名、标签、缩写和 HEAD 都不接受。
- `dependency_lock.path` 使用仓库内相对路径；路径穿越、绝对路径和 `.git` 内容不接受。
- 依赖文件必须存在于指定提交中，检出后的原始字节必须与清单哈希一致。
- Docker 镜像必须使用不可变 digest 引用，不能使用 `latest` 或普通版本标签代替。
- Docker 还必须固定 `linux/amd64` 或 `linux/arm64`，核对本地镜像平台并用 `--platform` 运行，避免多架构 digest 在不同主机上选择不同镜像。
- 运行前应准备包含 Git、测试工具及锁定依赖的镜像；评测不会自动拉取或构建镜像，也不在运行时安装依赖。
- 数据集和锁文件身份校验不会自动证明已安装依赖完全符合锁文件；镜像构建和后续验收仍需验证这件事。
- 公开创建任务 API 不接受 `execution_spec` 或 `test_command`。上述字段由受信任的离线评测流程写入。

## 本地工程验证

本地模式用于开发和回归测试，不能代替容器隔离与正式修复评测。它要求明确的运行时指纹：

```powershell
.\.venv\Scripts\python -c "from packages.agent_core.execution import local_runtime_identity; print(local_runtime_identity()['runtime_sha256'])"
```

将 `environment` 替换为：

```json
{
  "backend": "local",
  "runtime_sha256": "<上述命令输出的指纹>"
}
```

指纹包含 Python 版本与可执行文件哈希、操作系统和架构、Shell 哈希、Git 版本及已安装包名称/版本。
包清单、解释器或系统改变后，旧指纹不再通过。该指纹不能冻结整个操作系统、可变包源码及全部环境变量。
命令的 `--backend` 参数若与清单不一致，会被拒绝，不会静默切换执行方式。

`dataset_version` 和清单哈希绑定的是当前清单内容；Issue 正文目前仍从公开 API 获取。
真实实验的数据准备还需按计划 C2 冻结 Issue 输入，避免修复后的编辑或后续说明泄露答案。

## worker 执行门槛

1. 验证清单结构和 backend 是否匹配。
2. 浅克隆时不先检出默认分支；显式 fetch 指定 commit，再 detached checkout。
3. 核对实际 HEAD，要求初始工作区干净。缺失提交、fetch 失败或不匹配直接失败，没有回退到默认分支的逻辑。
4. 核对依赖文件字节哈希和环境身份。Docker 仅 inspect 已安装镜像，并以 `--pull never` 运行固定 digest。
5. 在构造模型客户端前保存实际执行身份；身份不匹配时不调用模型。
6. 固定版本任务从本次检出重新切块建索引，以 `fixer-run:<run_id>` 隔离定位器输入，不读取默认分支的共享代码索引。
7. 运行结束后再次核对 HEAD，避免 Agent 在执行中切换基准版本。
8. 保存验证证据并清理本次临时索引；其他任务和共享索引保持原样。

普通产品任务没有固定执行清单时仍可以生成补丁草稿，但 `identity_verified=false`，不能用于固定版本评测结论。

## 留存的身份信息

- `fixer_runs.execution_spec`：期望执行规范、清单原始字节哈希、配置版本 `config_id`。
- `result_json.execution`：请求规范、开始 commit、结束 commit、索引来源 commit、实际环境、依赖文件哈希、模型配置快照及哈希。
- 评测 JSON：每个实例的 execution 和 verification，以及整份清单的 SHA-256。
- API 任务响应中的 `execution`：用于读取上述身份记录；校验失败时保留已获得的部分证据和明确错误。

`e2e_success` 兼容指标还必须满足已有的补丁和工作区测试门槛，同时具备身份验证记录，开始／结束／索引 commit 均等于清单值。
从 A6/A7 起，新 benchmark 还要求独立验收通过，报告标记 `verification_scope=clean_checkout_tests`、
`independent_acceptance=true`，并报告本地开发实例数；不具备验收规范的普通任务仍只表示工作区验证。

## 数据库迁移与验证范围

迁移 `20261028_0011` 新增可空 JSON 字段 `fixer_runs.execution_spec`，旧记录保持空值。
使用新版 API/worker 前执行 `python -m alembic upgrade head`。
后续 A8 的当前 head 为 `20261029_0012`，允许费用未知，详见[运行证据说明](run-evidence.md)。

本轮使用临时本地 Git 仓库验证历史提交 fetch、准确检出、缺失提交拒绝、HEAD 漂移拒绝、依赖/运行时不匹配停止及索引隔离。
迁移使用临时 SQLite 验证旧记录保留和升降级；Docker digest 验证与禁止自动拉取通过确定性单元测试覆盖，未据此声称真实容器实验已经完成。

Windows 下沙箱 stdin/stdout 使用 UTF-8 字节传输，避免文本模式将 LF 补丁转换成 CRLF。
这项检查使用真实补丁、真实 Git 应用及落盘字节比对验证。

本轮全量后端验证：193 项通过；代码检查通过。当前实现与测试不代表真实 Issue 修复率提升。
