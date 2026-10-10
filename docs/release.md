# 发布流程（Windows / Linux 双平台）

> **macOS 不在支持范围内。** 项目只保证 Windows 与 Linux，CI 也只跑这两个 runner。
> 不要给 `.github/workflows/release.yml` 加 `macos-latest` 矩阵项。

---

## 1. 版本策略

- **一个 git tag = 一个版本**，Windows 与 Linux 从**同一个 tag** 发布，保证两端内容一致。
- tag 格式：`v<major>.<minor>.<patch>`，例如 `v0.1.0`。release workflow 会校验 `v` 前缀。
- 版本号只写在 tag 里，**不写进代码**。`pyproject.toml` 的 `version` 字段目前固定为 `0.1.0`，
  暂不参与自动化；如果将来要让它跟随 tag，需要在 release workflow 里加一步 sed 替换并回推。

### 产物命名

| 平台 | 产物名 | 内容 |
|------|--------|------|
| Windows 64 位 | `EEGWorkbench-<版本>-win64.exe` | PyInstaller one-file 薄启动器 |
| Linux x86_64 | `EEGWorkbench-<版本>-linux-x86_64.tar.gz` | `src/` + `run.sh` + `requirements-lock.txt` + `INSTALL_LINUX.md` |

---

## 2. 两个平台为什么形态不同

这不是偷懒，是两边约束不同：

**Windows 端做薄启动器而非全量打包。** MNE / scipy / sklearn 全量打包体积在 1–2 GB 量级。
薄启动器只带一个 `requirements-lock.txt`，首次运行时检查同目录的 `src/` 与 `.venv/`，
缺失就自动补齐，然后用 `.venv\Scripts\python.exe -m eeg_workbench` 拉起真实程序。
好处是产物小，且**运行时的依赖版本与锁定文件严格一致**，不会出现"打包环境和源码环境
两套依赖"的经典问题。

**Linux 端不用 PyInstaller。** PySide6 的 pip wheel 不包含 Qt 的 xcb 平台插件，也不包含
中文字体——这两样只能系统级安装。所以 Linux 上**不存在自包含二进制**可言，
硬打一个冻结 exe 只会带来新的问题（Qt 插件发现路径、glibc 版本绑定）。
`run.sh` 建 venv、装锁定依赖，依赖解析路径与 Windows 端完全一致，行为可预期、可测试。

代价是 Linux 用户必须先装系统依赖（见发行包内的 `INSTALL_LINUX.md`）。这是明说的,
不是隐藏的坑。

---

## 3. 发布前置检查

打 tag **之前**必须全部满足：

- [ ] 工作区干净，本地测试通过：
      ```powershell
      # Windows
      $env:PYTHONUTF8='1'; & ".venv\Scripts\python.exe" -m pytest tests/ -q --tb=line -p no:cacheprovider
      ```
      ```bash
      # Linux
      PYTHONUTF8=1 QT_QPA_PLATFORM=offscreen python -m pytest tests/ -q --tb=line -p no:cacheprovider
      ```
- [ ] 测试结果为 **208 passed**。已知的 8 个警告是既有的，**不要**当作回归：
  - 2× `filter_length` RuntimeWarning（`src/eeg_workbench/services/preprocessing/filtering.py`
    的 1651 / 8251 抽头滤波器，测试信号只有 1000 采样点）
  - 4× MNE ICA "data has not been high-pass filtered"（`src/eeg_workbench/services/preprocessing/ica.py`）
  - 2× sklearn FastICA ConvergenceWarning
- [ ] CI 阻断规则集通过：
      `python -m ruff check src tests --select F821,E9,F63,F7,F82`
- [ ] `master` 已推送，且 GitHub Actions 上 **Lint (windows-latest)**、
      **Lint (ubuntu-latest)**、**Tests (windows-latest, Python 3.14)**、
      **Tests (ubuntu-latest, Python 3.14)** 四个 job 全绿。

> release workflow 里的 `guard` job 会自动校验最后一条：它会查该 tag 对应 commit 的
> `ci.yml` 运行记录，只要有一个 run 不是 `success` 就中止发布。**不过闸就不能发。**

---

## 4. 发布命令

```powershell
# 1. 确认状态
git status                      # 必须干净
git fetch origin
git log --oneline origin/master -1

# 2. 打 tag（PowerShell 里 CJK 提交信息要用 -F，见 AGENTS.md）
git tag -a v0.1.0 -m "v0.1.0"
git push origin v0.1.0

# 3. 等 Release workflow 跑完，确认两个产物都挂上了
#    https://github.com/da-shan007/EEG-Visualization-Research-Workbench/releases
```

`push` tag 会触发 `.github/workflows/release.yml`。也可以在 Actions 页面
手动 `workflow_dispatch` 并填入 tag（此时远端必须已有该 tag）。

---

## 5. 发布后验收

- [ ] Release 页面有两个产物，且都能下载
- [ ] Windows：`.exe` 大小合理（薄启动器应在几十 MB 量级；若接近 GB 说明打成了全量包）
- [ ] Linux：`tar -tvzf` 里 `run.sh` 的权限位是 `-rwxr-xr-x`（workflow 里已自动校验，
      这一步是复核）
- [ ] Release 说明里的 apt 命令在干净 Kali 上能跑通

---

## 6. 回滚

发错了版本，**删 tag、删 Release、重打**，顺序不能乱：

```powershell
# 1. 先删远端 tag（这会同时作废已发布的 Release 关联）
git push origin :refs/tags/v0.1.0

# 2. 删本地 tag
git tag -d v0.1.0

# 3. 到 Releases 页面删除该 Release（tag 已删后 Release 会变成草稿/悬空，手动清掉）
#    或用 gh CLI： gh release delete v0.1.0 --yes

# 4. 修正后重新走第 4 节
git tag -a v0.1.0 -m "v0.1.0"
git push origin v0.1.0
```

已分发的二进制无法真正"收回"，只能靠删除 Release + 在 README 标注。
若某个版本已经在外面流出，建议改为**升一个 patch 版本**而不是原地重打同名 tag。