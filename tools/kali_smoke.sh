#!/usr/bin/env bash
# ============================================================================
# Kali 容器内的「普通 Linux 用户」实测脚本
#
# 模拟一个什么都没装的 Kali 用户，从零走一遍：
#   clone → 装系统依赖 → ./run.sh → 看 GUI/中文字体 → 打开 EDF/BDF
#
# 原则：只观察和记录，不修改项目代码。每一步都打印 PASS/FAIL，最后给汇总。
# 故意不用 set -e：某一步挂了要继续跑完，才能拿到完整报告。
# ============================================================================
set -uo pipefail

REF="${1:-master}"
SHA="${2:-1509412}"
OUT="${OUT:-/out}"
WORK="/tmp/eegsmoke"
mkdir -p "$OUT" "$WORK"

FAILURES=0
declare -a RESULTS

step() { printf '\n\033[1;36m########## %s\033[0m\n' "$*"; }
record() {  # record <名称> <PASS|FAIL|SKIP> <说明>
  RESULTS+=("$1|$2|$3")
  case "$2" in
    PASS) printf '\033[32m[PASS]\033[0m %s — %s\n' "$1" "$3" ;;
    FAIL) printf '\033[31m[FAIL]\033[0m %s — %s\n' "$1" "$3"; FAILURES=$((FAILURES+1)) ;;
    SKIP) printf '\033[33m[SKIP]\033[0m %s — %s\n' "$1" "$3" ;;
  esac
}

# ---------------------------------------------------------------- 0. 环境快照
step "0. Kali 环境快照"
cat /etc/os-release 2>/dev/null | head -4
echo "python3: $(command -v python3 || echo 'NOT FOUND') $(python3 -V 2>&1)"
echo "kernel:   $(uname -srm)"
echo "user:     $(id -un) uid=$(id -u)"
echo "arch:     $(dpkg --print-architecture 2>/dev/null || uname -m)"

# ------------------------------------------------------------ 1. 系统依赖安装
step "1. 安装系统依赖（README 的 apt 清单）"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >"$OUT/apt-update.log" 2>&1
echo "apt-get update rc=$?"

# ca-certificates：裸镜像里没有，git clone https 会报 "Problem with the SSL CA cert"
# python3/venv/pip：裸镜像里连 python3 都没有（真实 Kali 装机自带，但容器不是），
#   这里显式装上，等价于 INSTALL_LINUX.md 让用户自己敲的那几条
APT_PKGS="ca-certificates git xvfb x11-utils imagemagick fontconfig \
python3 python3-venv python3-pip \
libegl1 libgl1 libglx-mesa0 libopengl0 libxkbcommon-x11-0 libdbus-1-3 \
libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libfontconfig1 \
fonts-noto-cjk fonts-wqy-microhei"
# shellcheck disable=SC2086
if apt-get install -y --no-install-recommends $APT_PKGS >"$OUT/apt-install.log" 2>&1; then
  record "系统依赖安装" "PASS" "apt 装完 Qt xcb 运行库 + Xvfb + 中文字体"
else
  record "系统依赖安装" "FAIL" "apt 失败，见 $OUT/apt-install.log"
  tail -20 "$OUT/apt-install.log"
fi

# ------------------------------------------------------- 2. 系统中文字体是否存在
step "2. 系统中文字体（不依赖项目代码，验证 apt 那一层真的生效）"
CJK_N=$(fc-list 2>/dev/null | grep -ciE 'noto sans cjk|wenquanyi|noto serif cjk|droid sans fallback' || true)
echo "fc-list 匹配到的 CJK 字体条目数: $CJK_N"
fc-list 2>/dev/null | grep -oiE '(Noto Sans CJK [A-Z]+|WenQuanYi [A-Za-z]+)' | sort -u | head
if [ "$CJK_N" -gt 0 ]; then
  record "系统中文字体" "PASS" "$CJK_N 条 CJK 字体已安装"
else
  record "系统中文字体" "FAIL" "一个 CJK 字体都没有，Qt UI 必然全是方块"
fi

# ------------------------------------------------------------------- 3. clone 仓库
step "3. git clone（普通用户流程，不是 checkout CI 的工作区）"
if git clone -q https://github.com/da-shan007/EEG-Visualization-Research-Workbench.git "$WORK/repo"; then
  cd "$WORK/repo" || exit 1
  git checkout -q "$SHA" 2>/dev/null || git checkout -q "$REF"
  ACTUAL_SHA=$(git rev-parse --short HEAD)
  git log -1 --pretty='commit: %h  %s'
  echo "工作区实际 checkout: $ACTUAL_SHA (目标 $SHA)"
  if [ "$ACTUAL_SHA" = "$(echo "$SHA" | cut -c1-7)" ]; then
    record "clone 仓库" "PASS" "github.com clone 成功，HEAD=$ACTUAL_SHA"
  else
    record "clone 仓库" "FAIL" "HEAD=$ACTUAL_SHA 与期望 $SHA 不符"
  fi
else
  record "clone 仓库" "FAIL" "git clone 失败"
  echo "没有仓库就没法继续，退出。"
  exit 1
fi

# ------------------------------------------------------ 4. run.sh 权限与换行符
step "4. run.sh 本身（权限位 / CRLF / 解释器）"
ls -l run.sh
file run.sh 2>/dev/null || true
HEAD_BYTES=$(head -c 2 run.sh | od -An -tx1 | tr -d ' \n')
echo "文件头两字节: $HEAD_BYTES  (# 21 = '#!')"
if [ "$HEAD_BYTES" = "2321" ]; then
  record "run.sh shebang" "PASS" "以 #! 开头"
else
  record "run.sh shebang" "FAIL" "开头不是 #!，可能被 CRLF 污染"
fi
if head -c 400 run.sh | grep -q $'\r'; then
  record "run.sh 换行符" "FAIL" "含 CRLF，Linux 上会报 \$'\\r': command not found"
else
  record "run.sh 换行符" "PASS" "纯 LF，无 CRLF 污染"
fi
if bash -n run.sh 2>"$OUT/runsh-syntax.log"; then
  record "run.sh 语法" "PASS" "bash -n 通过"
else
  record "run.sh 语法" "FAIL" "bash -n 报错：$(cat "$OUT/runsh-syntax.log")"
fi

# ------------------------------------------------------------- 5. Xvfb 起 GUI
step "5. 启动 Xvfb + ./run.sh（真实 GUI 路径）"
Xvfb :99 -screen 0 1600x1000x24 -nolisten tcp >"$OUT/xvfb.log" 2>&1 &
XVFB_PID=$!
export DISPLAY=:99
sleep 3
if kill -0 "$XVFB_PID" 2>/dev/null; then
  record "Xvfb 启动" "PASS" "DISPLAY=:99 虚拟屏 1600x1000x24"
else
  record "Xvfb 启动" "FAIL" "Xvfb 起不来：$(cat "$OUT/xvfb.log")"
fi

echo "--- 执行 ./run.sh（首次会建 venv + 装依赖，可能要几分钟）---"
START=$(date +%s)
setsid ./run.sh >"$OUT/runsh.stdout.log" 2>"$OUT/runsh.stderr.log" &
RUNSH_PID=$!
echo "run.sh pid=$RUNSH_PID"

# 等窗口出现，最多 900 秒（装依赖很慢）
WINDOW_OK=0
for i in $(seq 1 180); do
  sleep 5
  if ! kill -0 "$RUNSH_PID" 2>/dev/null; then
    echo "!! run.sh 进程已退出（第 $((i*5)) 秒）"
    break
  fi
  if xwininfo -root -tree 2>/dev/null | grep -qiE 'EEG'; then
    WINDOW_OK=1
    echo "窗口出现，用时 $(( $(date +%s) - START )) 秒"
    break
  fi
  if [ $((i % 12)) -eq 0 ]; then
    echo "  ...仍在等待（$((i*5)) 秒），当前窗口列表："
    xwininfo -root -tree 2>/dev/null | tail -n +4 | head -8 | sed 's/^/    /'
    echo "  run.sh stderr 末尾："; tail -3 "$OUT/runsh.stderr.log" | sed 's/^/    /'
  fi
done

echo "--- xwininfo -root -tree ---"
xwininfo -root -tree 2>/dev/null | grep -iE 'EEG|Workbench' | head -10
echo "--- run.sh stderr 全文 ---"
cat "$OUT/runsh.stderr.log"

if [ "$WINDOW_OK" = "1" ]; then
  record "GUI 启动" "PASS" "Qt 窗口成功创建并映射到 X server"
else
  record "GUI 启动" "FAIL" "900 秒内没等到窗口；看 runsh.stderr.log 与 runsh.stdout.log"
fi

# 截图
if [ "$WINDOW_OK" = "1" ]; then
  sleep 5
  if command -v import >/dev/null 2>&1 && import -window root "$OUT/gui-mainwindow.png" 2>"$OUT/import.log"; then
    SZ=$(identify "$OUT/gui-mainwindow.png" 2>/dev/null | awk '{print $3}')
    record "GUI 截图" "PASS" "gui-mainwindow.png $SZ"
  else
    record "GUI 截图" "FAIL" "imagemagick import 失败：$(cat "$OUT/import.log" 2>/dev/null)"
  fi
fi

# venv 与依赖的落地情况
VENV="$WORK/repo/.venv"
if [ -x "$VENV/bin/python" ]; then
  record "Python venv" "PASS" "$("$VENV/bin/python" -V 2>&1) @ .venv/bin/python"
else
  record "Python venv" "FAIL" ".venv/bin/python 不存在"
fi

if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c 'import mne, PySide6, numpy, scipy, pandas, pyedflib' 2>"$OUT/importprobe.log"; then
  record "依赖安装" "PASS" "mne/PySide6/numpy/scipy/pandas/pyedflib 全部可导入"
  "$VENV/bin/python" - <<'PY' 2>&1 | sed 's/^/    /'
import importlib.metadata as md
for p in ("mne", "PySide6", "numpy", "scipy", "pandas", "pyedflib"):
    try:
        print(f"{p} == {md.version(p)}")
    except Exception as e:
        print(f"{p}: {e}")
PY
else
  record "依赖安装" "FAIL" "依赖导入失败：$(tail -5 "$OUT/importprobe.log")"
fi

# 关掉 GUI，后面用 offscreen 做断言
kill "$RUNSH_PID" 2>/dev/null
pkill -f 'python -m eeg_workbench' 2>/dev/null
sleep 2

# ------------------------------------------- 6. 中文字体是否真被项目选中
step "6. 项目自己的 CJK 字体探测（ensure_qt_cjk_font / ensure_cjk_font）"
if [ -x "$VENV/bin/python" ]; then
  PYTHONPATH="$WORK/repo/src" "$VENV/bin/python" - <<'PY' 2>&1 | sed 's/^/    /'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
app = QApplication([])
print("Qt platform:", app.platformName())
fams = QFontDatabase.families()
print("Qt 字体库条目数:", len(fams))
cands = [f for f in fams if any(k in f for k in ("Noto", "WenQuanYi", "CJK", "YaHei", "Hei", "Song"))]
print("Qt 可见 CJK 候选:", sorted(set(cands))[:10])
from eeg_workbench.utils.fonts import ensure_cjk_font, ensure_qt_cjk_font, missing_cjk_font_hint
ml = ensure_cjk_font()
print("ensure_cjk_font (matplotlib) ->", ml)
qt = ensure_qt_cjk_font(app)
print("ensure_qt_cjk_font (Qt) ->", qt)
print("app.font().family() ->", app.font().family())
print("missing_cjk_font_hint() ->", missing_cjk_font_hint())
PY
  FONTLOG=$(PYTHONPATH="$WORK/repo/src" "$VENV/bin/python" - 2>/dev/null <<'PY'
from PySide6.QtWidgets import QApplication
app = QApplication([])
from eeg_workbench.utils.fonts import ensure_qt_cjk_font
print(ensure_qt_cjk_font(app) or "")
PY
)
  if [ -n "$FONTLOG" ]; then
    record "Qt 中文字体" "PASS" "项目选中了 $FONTLOG"
  else
    record "Qt 中文字体" "FAIL" "ensure_qt_cjk_font 没选到任何 CJK 字体"
  fi
else
  record "Qt 中文字体" "SKIP" "venv 不存在"
fi

# --------------------------------------- 7. 生成 EDF/BDF 并走真实读取路径
step "7. 生成 EDF + BDF，走项目真实读取链路"
if [ -x "$VENV/bin/python" ]; then
  PYTHONPATH="$WORK/repo/src" "$VENV/bin/python" - "$WORK" <<'PY' 2>&1 | sed 's/^/    /'
import sys
from pathlib import Path
import numpy as np, pyedflib

work = Path(sys.argv[1]); work.mkdir(parents=True, exist_ok=True)
SFREQ = 250.0
NSAMP = int(SFREQ * 30)
LABELS = ["Fp1", "Fp2", "Fz", "C3", "C4", "Pz", "O1", "O2"]
rng = np.random.default_rng(42)
t = np.arange(NSAMP) / SFREQ
signals = np.vstack([
    40 * np.sin(2 * np.pi * 10 * t) + rng.normal(0, 8, NSAMP),   # alpha
    25 * np.sin(2 * np.pi * 6 * t) + rng.normal(0, 6, NSAMP),    # theta
    rng.normal(0, 5, NSAMP),
    rng.normal(0, 5, NSAMP),
    20 * np.sin(2 * np.pi * 20 * t) + rng.normal(0, 5, NSAMP),   # beta
    rng.normal(0, 5, NSAMP),
    rng.normal(0, 5, NSAMP),
    rng.normal(0, 3, NSAMP),
])

def make(path, ftype):
    w = pyedflib.EdfWriter(str(path), len(LABELS), file_type=ftype)
    for i, lab in enumerate(LABELS):
        w.setSignalHeader(i, {
            "label": lab, "dimension": "uV",
            # 注意：pyedflib 已废弃 sample_rate（用了会抛 FutureWarning 异常），只能给 sample_frequency
            "sample_frequency": SFREQ,
            "physical_min": -250.0, "physical_max": 250.0,
            "digital_min": -32768, "digital_max": 32767,
            "transducer": "", "prefilter": "",
        })
    # 注意：不要调 setHeader()，它强制要求 patientname/recording_startdate 等完整键，smoke 数据不需要
    w.writeSamples(signals)
    # pyedflib 0.1.42 没有 writeSignalAnnotations，写标注要用 writeAnnotation
    w.writeAnnotation(2.0, 1.0, "smoke_event")
    w.close()
    print(f"已生成 {path.name}  {path.stat().st_size} bytes")

make(work / "smoke.edf", pyedflib.FILETYPE_EDFPLUS)
make(work / "smoke.bdf", pyedflib.FILETYPE_BDFPLUS)

print("--- 项目读取链路 EDFReader / BDFReader ---")
from eeg_workbench.services.io.edf import EDFReader, BDFReader
from eeg_workbench.services.io import ReaderFactory

for name, Reader in (("EDF", EDFReader), ("BDF", BDFReader)):
    p = work / f"smoke.{name.lower()}"
    try:
        res = Reader().read(str(p))
        ds = res.dataset
        print(f"{name}Reader OK -> n_channels={ds.n_channels} sfreq={ds.sfreq} "
              f"n_samples={ds.n_samples} duration={ds.duration:.1f}s events={len(ds.events)} "
              f"ch_names={ds.ch_names}")
    except Exception as e:
        print(f"{name}Reader FAIL -> {type(e).__name__}: {e}")

print("--- ReaderFactory 工厂（按扩展名分发，GUI 真正走的路）---")
for ext in (".edf", ".bdf"):
    p = work / f"smoke{ext}"
    r = ReaderFactory.get_reader(str(p))
    print(f"{ext} -> {type(r).__name__} (FORMAT_NAME={getattr(r, 'FORMAT_NAME', '?')})")
    res = ReaderFactory.load_dataset(str(p))
    ds = res.dataset
    print(f"{ext} load_dataset OK -> n_channels={ds.n_channels} sfreq={ds.sfreq} "
          f"name={ds.name} events={len(ds.events)}")
PY
  if PYTHONPATH="$WORK/repo/src" "$VENV/bin/python" -c "
import sys; sys.path.insert(0,'$WORK/repo/src')
from eeg_workbench.services.io import ReaderFactory
for e in ('.edf','.bdf'):
    ds = ReaderFactory.load_dataset('$WORK/smoke'+e).dataset
    assert ds.n_channels==8, (e, ds.n_channels)
    assert ds.sfreq==250.0, (e, ds.sfreq)
print('BOTH OK')
" 2>"$OUT/edf-read.log"; then
    record "EDF/BDF 读取" "PASS" "EDF 与 BDF 均经 ReaderFactory 读出 8 通道 @250Hz"
  else
    record "EDF/BDF 读取" "FAIL" "读取失败：$(tail -8 "$OUT/edf-read.log")"
  fi
else
  record "EDF/BDF 读取" "SKIP" "venv 不存在"
fi

# ---------------------------------- 8. GUI 真实加载 EDF（走 MainWindow 链路）
step "8. 主窗口真实加载 EDF（offscreen，验证 UI 层能吃下数据）"
if [ -x "$VENV/bin/python" ] && [ -f "$WORK/smoke.edf" ]; then
  if QT_QPA_PLATFORM=offscreen PYTHONPATH="$WORK/repo/src" "$VENV/bin/python" - "$WORK/smoke.edf" >"$OUT/gui-load.log" 2>&1 <<'PY'
import sys, time
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThreadPool
from eeg_workbench.main import MainWindow
from eeg_workbench.utils.fonts import ensure_cjk_font, ensure_qt_cjk_font

app = QApplication([])
ensure_cjk_font(); ensure_qt_cjk_font(app)
w = MainWindow(); w.resize(1400, 900); w.show()
app.processEvents()

vm = w._data_vm
# 注意：has_dataset / dataset_summary / dataset 都是 @property，不是方法
print("加载前 has_dataset:", vm.has_dataset)
vm.load_file(sys.argv[1])
# load_file 是 @async_slot，走 QThreadPool 后台线程，返回时数据还没落定，必须等
deadline = time.time() + 90
while time.time() < deadline:
    QThreadPool.globalInstance().waitForDone(500)
    app.processEvents()
    if vm.has_dataset:
        break
    time.sleep(0.2)
print("加载后 has_dataset:", vm.has_dataset)
print("dataset_summary:", vm.dataset_summary)
ds = vm.dataset
print("通道数:", ds.n_channels)
print("通道名:", ds.ch_names)
print("采样率:", ds.sfreq)
print("样本数:", ds.n_samples, " 时长:", round(ds.duration, 2), "s")
print("事件数:", len(ds.events))
print("窗口标题:", w.windowTitle())

w.grab().save("/out/gui-loaded-edf.png")
print("截图已保存")
assert vm.has_dataset, "GUI 加载后 has_dataset 仍为 False"
print("GUI LOAD OK")
PY
  then
    record "GUI 加载 EDF" "PASS" "MainWindow._data_vm.load_file 成功并刷新视图"
  else
    record "GUI 加载 EDF" "FAIL" "见 $OUT/gui-load.log：$(tail -12 "$OUT/gui-load.log")"
  fi
  tail -14 "$OUT/gui-load.log" | sed 's/^/    /'
else
  record "GUI 加载 EDF" "SKIP" "venv 或 EDF 不存在"
fi

kill "$XVFB_PID" 2>/dev/null

# ------------------------------------------------------------------- 9. 汇总
step "9. 实测汇总"
printf '\n%-22s %-6s %s\n' "检查项" "结果" "说明"
printf '%s\n' "------------------------------------------------------"
for r in "${RESULTS[@]}"; do
  IFS='|' read -r n s d <<< "$r"
  printf '%-22s %-6s %s\n' "$n" "$s" "$d"
done
printf '%s\n' "------------------------------------------------------"
echo "失败项数: $FAILURES"

{
  echo "# Kali 实测报告"
  echo
  echo "- 参考: \`$SHA\`（分支 $REF）"
  echo "- 容器: kalilinux/kali-rolling"
  echo "- 失败项: $FAILURES"
  echo
  echo "| 检查项 | 结果 | 说明 |"
  echo "|---|---|---|"
  for r in "${RESULTS[@]}"; do
    IFS='|' read -r n s d <<< "$r"
    echo "| $n | $s | $d |"
  done
} > "$OUT/REPORT.md"

echo "报告已写入 $OUT/REPORT.md"
exit 0