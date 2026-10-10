"""EEG Workbench 启动器：双击即用（无控制台窗口）。

行为：
1. 检查：同目录下 src/eeg_workbench 是否存在；.venv 是否存在且能
   import mne / PySide6 / numpy。两项都满足 → 直接启动。
2. 缺代码 → 尝试从 GitHub 下载源码 zip（需要仓库已公开）并解压。
3. 缺环境 → 找本机 Python(>=3.12) 建 .venv，用 exe 内置的
   requirements-lock.txt 装依赖，然后启动。

第二次及以后点击：检查通过，直接启动，无任何弹窗。
所有提示走 MessageBox（冻结 exe 无控制台，print 看不见）。
"""

import ctypes
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

REPO_ZIP_URL = (
    "https://github.com/da-shan007/EEG-Visualization-Research-Workbench"
    "/archive/refs/heads/master.zip"
)
MIN_PYTHON = (3, 12)
IMPORT_PROBE = "import mne, PySide6, numpy, scipy, pandas"
TITLE = "EEG Workbench"


def _msg(text: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, text, TITLE, 0x40)
    except Exception:
        print(text, flush=True)


def _err(text: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, text, TITLE, 0x10)
    except Exception:
        print(text, flush=True)


def _project_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _bundled_lock() -> str | None:
    """exe 内置的 requirements-lock.txt（PyInstaller --add-data 打入）。"""
    if getattr(sys, "frozen", False):
        p = os.path.join(sys._MEIPASS, "requirements-lock.txt")  # type: ignore[attr-defined]
        if os.path.isfile(p):
            return p
    p = os.path.join(_project_root(), "requirements-lock.txt")
    return p if os.path.isfile(p) else None


def check_code(root: str) -> bool:
    return os.path.isfile(os.path.join(root, "src", "eeg_workbench", "__init__.py"))


def _venv_python(root: str) -> str:
    return os.path.join(root, ".venv", "Scripts", "python.exe")


def check_deps(root: str) -> bool:
    py = _venv_python(root)
    if not os.path.isfile(py):
        return False
    try:
        r = subprocess.run(
            [py, "-c", IMPORT_PROBE],
            capture_output=True,
            timeout=180,
        )
        return r.returncode == 0
    except Exception:
        return False


def check_ready(root: str) -> bool:
    return check_code(root) and check_deps(root)


def _find_base_python() -> str | None:
    """找本机 >=3.12 的 Python（py 启动器优先）。"""
    tried: list[list[str]] = []
    launcher = shutil.which("py")
    if launcher:
        for tag in ("-3.14", "-3.13", "-3.12", "-3"):
            tried.append([launcher, tag])
    for name in ("python3.14", "python3.13", "python3.12", "python3", "python"):
        p = shutil.which(name)
        if p:
            tried.append([p])
    for cmd in tried:
        try:
            r = subprocess.run(
                cmd + ["-c", "import sys; print('.'.join(map(str, sys.version_info[:2])))"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if r.returncode != 0:
                continue
            major, _, minor = r.stdout.strip().partition(".")
            if (int(major), int(minor or 0)) >= MIN_PYTHON:
                return " ".join(cmd) if len(cmd) > 1 else cmd[0]
        except Exception:
            continue
    return None


def _run(cmd: list[str], timeout: int) -> bool:
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return r.returncode == 0
    except Exception:
        return False


def ensure_code(root: str) -> bool:
    """缺 src 时从 GitHub 下载。返回 False 则调用方弹窗报错。"""
    if check_code(root):
        return True
    try:
        zpath = os.path.join(root, "_repo.zip")
        urllib.request.urlretrieve(REPO_ZIP_URL, zpath)
        with zipfile.ZipFile(zpath) as zf:
            top = zf.namelist()[0].split("/")[0]
            zf.extractall(root)
        src_dl = os.path.join(root, top, "src")
        src_dst = os.path.join(root, "src")
        if os.path.isdir(src_dl) and not os.path.isdir(src_dst):
            shutil.move(src_dl, src_dst)
        shutil.rmtree(os.path.join(root, top), ignore_errors=True)
        os.remove(zpath)
    except Exception:
        return check_code(root)
    return check_code(root)


def ensure_env(root: str) -> bool:
    """缺 .venv/依赖时创建并安装。返回 False 则调用方弹窗报错。"""
    if check_deps(root):
        return True
    lock = _bundled_lock()
    if lock is None:
        return False
    base = _find_base_python()
    if base is None:
        return False
    venv_dir = os.path.join(root, ".venv")
    base_cmd = base.split(" ")
    if not os.path.isfile(_venv_python(root)):
        if not _run(base_cmd + ["-m", "venv", venv_dir], 600):
            return False
    vpy = _venv_python(root)
    if not _run([vpy, "-m", "pip", "install", "--upgrade", "pip"], 600):
        return False
    return _run([vpy, "-m", "pip", "install", "-r", lock], 3600)


def launch(root: str) -> int:
    py = _venv_python(root)
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = os.path.join(root, "src") + os.pathsep + env.get("PYTHONPATH", "")
    try:
        subprocess.Popen([py, "-m", "eeg_workbench"], cwd=root, env=env, close_fds=True)
    except Exception:
        return 1
    return 0


def main() -> int:
    root = _project_root()
    if check_ready(root):
        return launch(root)
    _msg("首次运行：正在准备环境（下载代码/安装依赖），需要几分钟，请稍候。")
    if not ensure_code(root):
        _err("缺少程序代码，且无法从 GitHub 下载。\n请确认仓库已公开且网络可用。")
        return 1
    if not ensure_env(root):
        _err(
            "依赖安装失败。请确认：\n"
            "1. 本机装有 Python 3.12+（python.org 版）；\n"
            "2. 网络可用。"
        )
        return 1
    _msg("环境准备完成，正在启动。")
    return launch(root)


if __name__ == "__main__":
    raise SystemExit(main())
