# 代码质量基线与偿还计划

- 建立日期：2026-10-05
- 对应提交：`34ec7e8`（v0.1.0 之后）

## 1. 测试

| 指标 | 值 |
|---|---|
| 用例数 | 203 |
| 结果 | 全部通过 |
| 耗时 | ~4.5 分钟（`python -m pytest tests/ -q --tb=line -p no:cacheprovider`） |
| 环境变量 | `PYTHONUTF8=1`；CI 中额外设 `QT_QPA_PLATFORM=offscreen` |

已知警告（不阻断）：

- `standard_1020` 蒙版名在 MNE 1.14 起废弃，将改用 `colin27_1020`
- 单样本 t 检验在自由度 ≤ 0 时输出 numpy `invalid value` 警告
- 滤波长度（8251）超过测试信号长度（5000）时的 `filter_length` 警告

## 2. ruff

| 指标 | 值 |
|---|---|
| `--select F821`（未定义名） | **0（通过）** |
| 全规则（E,F,I,N,W,UP,B,C4,PT,T20,SIM,RET） | ~1400 条历史问题 |

当前 CI **只阻断** `F821/E9/F63/F7/F82`（会导致运行时错误的规则），其余作为待还的技术债。

主要存量：`F401` 未使用导入、`W293` 行尾空白、`I001` 导入未排序、`UP045` 可用 `X | None` 替代 `Optional[X]`。

## 3. mypy

`mypy src/eeg_workbench --strict --ignore-missing-imports` → **1529 个错误**

| 错误码 | 数量 | 性质 |
|---|---|---|
| `no-untyped-def` | 858 | 函数缺返回/参数类型标注（机械修复） |
| `no-untyped-call` | 259 | 调用了无标注函数（补齐被调用方即消） |
| `type-arg` | 119 | 泛型缺类型参数 |
| `assignment` | 83 | 赋值类型不符（**真缺陷**） |
| `arg-type` | 80 | 传参类型不符（**真缺陷**） |
| `union-attr` | 42 | 访问了可能为 `None` 的属性（**真缺陷**） |
| `attr-defined` | 26 | 属性不存在（**真缺陷**） |
| `no-any-return` | 19 | 返回了 `Any` |
| `return-value` | 15 | 返回类型不符（**真缺陷**） |
| 其他 | ~88 | `var-annotated` / `override` / `comparison-overlap` 等 |

**约 246 个是可能在运行时暴露的真缺陷**，其余 ~1280 是标注覆盖率问题。

`pyproject.toml` 当前 `[tool.mypy]` 仍为非严格模式（`disallow_untyped_defs = false`），CI 中的 mypy 步骤为 informational（`continue-on-error: true`），避免阻塞流水线。

## 4. 偿还顺序（建议）

1. **真缺陷优先**：`models/` 与 `services/core` 中的 `assignment` / `arg-type` / `union-attr` / `attr-defined` / `return-value`（约 246 条）——这些最可能在运行时出错。
2. **标注覆盖率**：按包逐个开启 `disallow_untyped_defs`，优先 `models/`（数据契约）再 `services/`。
3. **接入 CI 防回退**：当某个包的错误数清零后，在 CI 中对该包启用严格模式。
4. 全清后把 mypy 步骤从 informational 改为阻断，并删除本文件的"待偿还"章节。

## 5. 相关文档

- [ADR 001: 技术栈选择](adr/001-tech-stack.md)
- [ADR 002: 分层架构](adr/002-mvvm-layering.md)
- 运行规范见仓库根目录 `AGENTS.md`
