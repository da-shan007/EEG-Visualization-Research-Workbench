#!/usr/bin/env bash
# EEG Workbench —— Linux / macOS 启动脚本（等价于 Windows 的 启动EEGWorkbench.exe）
#
# 行为（幂等，第二次起直接启动）：
#   1. 探测 .venv 及其中的 mne/PySide6/numpy/scipy/pandas；
#   2. 缺 venv → 用本机 >=3.12 的 python3 -m venv 创建；
#   3. 缺依赖 → 按 requirements-lock.txt 安装（首次约 3-5 分钟）；
#   4. 以 PYTHONPATH=src 启动 python -m eeg_workbench（无需 cd 到 src/）。
#
# 用法：
#   ./run.sh            启动 GUI
#   ./run.sh --offscreen 无显示器（服务器 / SSH）下跑测试或 CI

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
LOCK="$ROOT/requirements-lock.txt"
IMPORT_PROBE='import mne, PySide6, numpy, scipy, pandas'
MIN_PY="3.12"

die() { printf '\033[31m[EEG Workbench] %s\033[0m\n' "$*" >&2; exit 1; }
info() { printf '\033[36m[EEG Workbench] %s\033[0m\n' "$*"; }

# venv 里的解释器：POSIX 布局是 .venv/bin/python（Windows 才是 Scripts/python.exe）
venv_python() {
    if [[ -x "$VENV/bin/python" ]]; then printf '%s' "$VENV/bin/python"
    elif [[ -x "$VENV/bin/python3" ]]; then printf '%s' "$VENV/bin/python3"
    else printf ''; fi
}

deps_ok() {
    local py="$1"
    "$py" -c "$IMPORT_PROBE" >/dev/null 2>&1
}

# 找一个 >= 3.12 的 python3
find_base_python() {
    local c
    for c in python3.14 python3.13 python3.12 python3 python; do
        if command -v "$c" >/dev/null 2>&1; then
            if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
                command -v "$c"; return 0
            fi
        fi
    done
    return 1
}

PY="$(venv_python || true)"

if [[ -z "$PY" ]] && [[ -d "$VENV" ]]; then
    die "$VENV 已存在但里面没有 POSIX 解释器（.venv/bin/python）。
它多半是从 Windows 拷过来的（那边是 .venv/Scripts/python.exe），两者不通用。
删掉 $VENV 重跑本脚本，或改用 README 里的「路线 B/C」手动建 Linux venv。"
fi

if [[ -z "$PY" ]] || ! deps_ok "$PY"; then
    if [[ -z "$PY" ]]; then
        info "未找到 .venv，正在创建（首次运行需几分钟）..."
        BASE="$(find_base_python)" \
            || die "未找到 Python $MIN_PY+。请先安装，例如：
  Debian/Ubuntu: sudo apt install python3.12 python3.12-venv
  Fedora:        sudo dnf install python3.12
  或用 pyenv/conda 安装后重试。"
        "$BASE" -m venv "$VENV" || die "创建 venv 失败（$BASE -m venv $VENV）"
        PY="$(venv_python)"
        [[ -n "$PY" ]] || die "venv 创建成功但找不到解释器：$VENV/bin/python"
    fi

    if ! deps_ok "$PY"; then
        [[ -f "$LOCK" ]] || die "缺少 $LOCK，无法自动安装依赖。请手动 pip install。"
        info "正在安装依赖（首次约 3-5 分钟）..."
        "$PY" -m pip install --upgrade pip >/dev/null
        "$PY" -m pip install -r "$LOCK" \
            || die "依赖安装失败。请确认网络可用，或手动执行：
  $PY -m pip install -r $LOCK"
    fi
fi

# 让源码里的中文在任何 locale 下都正确读写
export PYTHONUTF8=1
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ "${1:-}" == "--offscreen" ]]; then
    export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
    info "以 offscreen 模式启动（无显示器）"
fi

info "启动中…（Ctrl+C 退出）"
exec "$PY" -m eeg_workbench