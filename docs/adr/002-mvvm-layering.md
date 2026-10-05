# ADR 002: 分层架构 — MVVM + 无 UI 依赖的 Service 层

- 状态：已接受
- 日期：2026-10-05

## 背景

EEG 分析流程包含大量数值算法（滤波、ICA、频谱、时频、连通性、源定位、统计）。这些算法需要被 GUI、命令行脚本、批量处理和自动化测试共同使用。如果把算法写进窗口控件里，就无法单测，也无法复用。

## 决策

采用四层结构，依赖方向严格自上而下：

```
views/            ← PySide6 控件：只负责显示与收集用户输入
viewmodels/       ← 状态、命令、异步调度、事件发布；不引入 PySide6 之外的 UI 逻辑
services/         ← 纯业务逻辑与数值算法；禁止 import PySide6
models/           ← 不可变数据类（EEGDataset、各 Result、Params）
core/             ← EventBus、Config、ViewModelBase、Command 基类
utils/            ← 与业务无关的通用工具（字体、蒙版、UI 布局辅助）
```

配套约定：

1. **`models/` 用 `@dataclass(frozen=True)`**，任何"修改"都返回新实例（`dataclasses.replace`），避免隐式共享状态。
2. **`services/` 中的函数是纯函数**：输入数据 → 输出数据，不持有状态、不触碰 UI、不做全局配置读写。
3. **层间通过 `EventBus` 解耦**：服务或 ViewModel 发布 `EventType.DATASET_LOADED` 之类的事件，所有关心的视图各自订阅，避免一对多的直接引用。
4. **`services/` 不得 `import PySide6`**，这条规则由 ruff/mypy 与人工 review 共同守住。

## 理由

- **可测试**：`pytest tests/` 无需显示器即可覆盖数值逻辑（CI 用 `QT_QPA_PLATFORM=offscreen`）。
- **可复用**：同一套 `services/` 已能被命令行与批量脚本调用。
- **可并行开发**：改动 UI 不会牵动算法，改动算法不会牵动 UI。
- **可扩展**：新增分析模块 = 新增 `services/<module>/` + `viewmodels/<module>_vm.py` + `views/<module>/`，不修改既有模块。

## 备选方案与拒绝理由

- **单文件/表格式代码（所有逻辑写在 Widget 里）**：无法脱离 GUI 进行自动化测试，算法不可复用，改动风险高。
- **传统 MVC**：Qt 的信号槽机制与数据绑定更适合 ViewModel 这一层的表达方式。
- **微服务化**：单机桌面应用，拆进程只会增加复杂度，无收益。

## 后果

- 新功能必须同时考虑四层的落点，不能图省事把逻辑塞进 Widget。
- View 不得直接 `import services`，必须经由 ViewModel。
- 跨层数据传递统一使用 `models/` 中的数据类，禁止传裸 dict。

## 相关文档

- [ADR 001: 技术栈选择](001-tech-stack.md)
- 项目规则见 `AGENTS.md`
