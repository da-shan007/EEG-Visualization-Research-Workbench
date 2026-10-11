#!/usr/bin/env bash
# EEG Workbench —— Linux / macOS 启动脚本（等价于 Windows 的 启动EEGWorkbench.exe）
#
# 行为（幂等，第二次起直接启动）：
#   1. 探测 .venv 及其中的 mne/PySide6/numpy/scipy/pandas；
#   2. 缺 venv → 用本机 >=3.12 的 python3 -m venv 创建；
#   3. 缺依赖 → 按 requirements-lock.txt 安装（首次约 3-5 分钟）；
#   4. 以 PYTHONPATH=src 启动 python -m eeg_workbench（无需 cd 到 src/）。
#
# 关于 Python 版本：优先选 3.12。原因在 requirements-lock.txt 里的 pyEDFlib
# —— 它只发到 cp313 的 wheel，cp312 有 manylinux x86_64 轮子，而 3.13 的 Linux
# 轮子只有 aarch64、3.14 完全没有。所以在 Linux x86_64 上：
#   Python 3.10/3.11/3.12 → 直接装轮子，不需要编译器（推荐）
#   Python 3.13/3.14     → 只能从 sdist 编译 pyEDFlib，需要 gcc + 头文件
# 脚本会在开始装依赖前检查这件事，缺编译器就直接给提示退出，而不是等 pip
# 编到一半再报一堆看不懂的错。
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

# 找一个 >= 3.12 的 python3。顺序很重要：3.12 排在最前，因为它是唯一
# 能让整个锁文件免编译装完的版本（见文件头关于 pyEDFlib 的说明）。
# 只有当本机没有 3.12 时才退到 3.13 / 3.14。
find_base_python() {
    local c
    for c in python3.12 python3.13 python3.14 python3 python; do
        if command -v "$c" >/dev/null 2>&1; then
            if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
                command -v "$c"; return 0
            fi
        fi
    done
    return 1
}

# 本机有没有能编 C 扩展的编译器
has_c_compiler() {
    command -v cc >/dev/null 2>&1 ||
        command -v gcc >/dev/null 2>&1 ||
        command -v clang >/dev/null 2>&1
}

# pyEDFlib 在这个 Python 版本上有没有现成轮子。
# 0.1.42 只发到 cp313，且 cp313 的 Linux 轮子只有 aarch64 —— 所以只有
# <= 3.12 能免编译，3.13/3.14 一定会走 sdist。
pyedflib_needs_source_build() {
    "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)'
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

        # 装之前先验一下编译器。pip 装到 pyEDFlib 才发现没 gcc 的话，
        # 已经白跑好几分钟了，而且报的是一屏 gcc 的报错，很难看出根因。
        if pyedflib_needs_source_build "$PY" && ! has_c_compiler; then
            die "这个 Python 是 $($PY -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')，
装依赖需要从源码编译 pyEDFlib（它没有 cp314 / cp313 x86_64 的轮子），但本机没有 C 编译器。
两条路，任选其一：
  A. 装编译器（保持当前 Python 版本）：
       Debian/Ubuntu/Kali: sudo apt install build-essential python3-dev
       Fedora:             sudo dnf install gcc python3-devel
       Arch:               sudo pacman -S base-devel
  B. 改用 Python 3.12，整个锁文件都能装预编译轮子，不用编译器：
       Debian/Ubuntu/Kali: sudo apt install python3.12 python3.12-venv
  装完重新跑 ./run.sh。"
        fi

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