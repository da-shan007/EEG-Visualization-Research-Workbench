# ADR 001: 技术栈选择

- 状态：已接受
- 日期：2026-10-05

## 背景

需要一个跨平台的桌面 EEG 分析软件，核心算法依赖 MNE-Python 生态，用户是神经科学/心理学/脑机接口领域的研究生与研究人员。团队小、需要快速迭代、且必须能在无显示器的 CI 环境里跑测试。

## 决策

| 领域 | 选择 | 版本（实测锁定） |
|---|---|---|
| 语言 | Python | ≥3.12（实测 3.14.0） |
| GUI | PySide6 (Qt 6, LGPL) | 6.11.2 |
| 信号处理/神经影像 | MNE-Python | 1.13.2 |
| 数值 | NumPy / SciPy | 2.5.3 / 1.18.1 |
| 表格数据 | pandas | 3.0.5 |
| 绘图 | matplotlib（可选 pyqtgraph 加速） | 3.11.2 |
| 统计 | pingouin + statsmodels + scipy | 0.7.0 / 0.15.0 |
| 报告 | Jinja2 → HTML/PDF（可选 reportlab/WeasyPrint） | 3.1.6 |
| 测试 | pytest + pytest-qt | 9.1.1 / 4.5.0 |
| 静态检查 | ruff + mypy + black | 0.16.10 / 2.4.0 / 26.10.0 |
| 依赖锁定 | `requirements-lock.txt`（pip freeze） | 140 个包 |
| CI | GitHub Actions，`windows-latest` + `QT_QPA_PLATFORM=offscreen` | `.github/workflows/ci.yml` |

## 理由

- **Python**：MNE/NumPy/SciPy 生态无可替代，原型速度最快，研究人员可直接阅读和修改。
- **PySide6 而非 PyQt6**：LGPL 许可允许闭源分发，无需 GPL 传染或商业授权费。
- **PySide6 而非 Web 前端**：本地文件读写、大文件流式处理、离线分发都更简单；MNE 的 2D/3D 绑图可直接嵌入 matplotlib canvas，无需前后端两套代码。
- **pip freeze 锁定而非仅靠 pyproject 声明**：`pyproject.toml` 表达的是"允许的范围"，`requirements-lock.txt` 表达的是"被测试过的那一套"。CI 用后者，保证可复现。

## 备选方案与拒绝理由

- **Tauri / Rust + Web**：团队无 Rust 与前端经验，MNE 无 WASM 移植，风险过高。
- **Jupyter + Voila**：无法离线分发为桌面应用，缺少原生菜单/快捷键，大数据交互卡顿。
- **Matlab**：授权成本高、无法自由分发、团队以 Python 为主。

## 后果

- Python 3.12 是硬下限（NumPy 2.5 / SciPy 1.18 的要求），无法支持更老版本。
- Qt 相关问题需在 `QT_QPA_PLATFORM=offscreen` 下也能通过，禁止在测试中依赖真实窗口。
- 新增依赖必须同时更新 `pyproject.toml`、`requirements.txt`、`environment.yml`，并重新生成 `requirements-lock.txt`。
