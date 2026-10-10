# Linux 安装说明

本文件随 Linux 发行包一起分发（`EEGWorkbench-<版本>-linux-x86_64.tar.gz`）。

> **macOS 不在支持范围内。** 本项目只保证 Windows 与 Linux 两个平台。

---

## 1. 先装系统依赖（必做）

PySide6 的 pip wheel **不包含** Qt 的 xcb 平台插件，也**不包含**任何中文字体。
这两样只能由系统包管理器提供，跳过这一步的话程序会在启动时报
`Could not load the Qt platform plugin "xcb"`，或者界面全是方框。

### Debian / Ubuntu / Kali

```bash
sudo apt update

# Qt 运行库
sudo apt install -y libegl1 libgl1 libglx-mesa0 libopengl0 \
                    libxkbcommon-x11-0 libdbus-1-3 libfontconfig1 \
                    libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
                    libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
                    libxcb-shape0 libxcb-xinerama0 libxcb-xkb1

# 中文字体（缺了界面和 matplotlib 图形里的中文都是方框）
sudo apt install -y fonts-noto-cjk fonts-wqy-microhei

# Python 3.12+
sudo apt install -y python3.12 python3.12-venv python3-pip
```

### Fedora

```bash
sudo dnf install -y mesa-libGL mesa-libEGL libxkbcommon-x11 dbus-libs fontconfig \
                    google-noto-sans-cjk-fonts wqy-microhei-fonts python3.12 python3.12-pip
```

### Arch

```bash
sudo pacman -S --needed glvnd libxkbcommon dbus fontconfig noto-fonts-cjk wqy-microhei
```

### 验证

```bash
python3 -c "from PySide6.QtWidgets import QApplication; print('Qt OK')"
```

打印 `Qt OK` 就说明这一步过了。

---

## 2. 启动

```bash
tar -xzf EEGWorkbench-<版本>-linux-x86_64.tar.gz
cd EEGWorkbench-<版本>-linux-x86_64
./run.sh
```

`run.sh` 会自动完成：找 Python ≥3.12 → 建 `.venv` → 按 `requirements-lock.txt`
装依赖 → 以 `PYTHONPATH=src` 启动。首次约 3-5 分钟，之后每次直接秒启。

> **注意**：`.venv` 是平台相关的。Windows 用的是 `.venv/Scripts/python.exe`，
> Linux 用的是 `.venv/bin/python`，两者不通用，不要互相拷贝。

---

## 3. 常见问题

| 现象 | 原因与处理 |
|------|-----------|
| `Could not load the Qt platform plugin "xcb"` | 缺 Qt 系统库，见第 1 步 |
| 界面和图里的中文是方框 | 没装中文字体，见第 1 步。启动时 stderr 也会打印提示 |
| 启动时 stderr 打印「未检测到中文字体」 | 同上 |
| `.venv 已存在但里面没有 POSIX 解释器` | `.venv` 是从 Windows 拷过来的，删掉它重跑 `./run.sh` |
| `找不到 Python 3.12+` | 系统 Python 太旧，装一个 ≥3.12 的，或用 conda |
| 找不到 `eeg-workbench` 命令 | 用 `PYTHONPATH=src python -m eeg_workbench` |
| 没有显示器 / SSH 登录 | `./run.sh --offscreen`，或 `xvfb-run ./run.sh` |

---

## 4. 手动安装（不想用 `run.sh` 时）

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-lock.txt
PYTHONPATH=src python -m eeg_workbench
```

或用 conda：

```bash
conda env create -f environment.yml
conda activate eeg-workbench
PYTHONPATH=src python -m eeg_workbench
```