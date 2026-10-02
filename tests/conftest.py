"""测试配置"""
import importlib.util as _ilu
import sys
from pathlib import Path

# 确保 src 在路径中
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

# legacy 根包 eeg_workbench/ 与 src/eeg_workbench 同名冲突；
# 以别名 eeg_workbench_legacy 注册，供 test_eeg_core / test_research 针对 legacy API 的测试使用
_legacy_dir = Path(__file__).parent.parent / "eeg_workbench"
if (_legacy_dir / "__init__.py").exists() and "eeg_workbench_legacy" not in sys.modules:
    _spec = _ilu.spec_from_file_location(
        "eeg_workbench_legacy",
        _legacy_dir / "__init__.py",
        submodule_search_locations=[str(_legacy_dir)],
    )
    _legacy = _ilu.module_from_spec(_spec)
    sys.modules["eeg_workbench_legacy"] = _legacy
    _spec.loader.exec_module(_legacy)


@pytest.fixture(scope="session")
def qapp():
    """提供 QApplication 实例"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


# 共享测试数据路径
TEST_DATA_DIR = Path(__file__).parent / "test_data"
TEST_DATA_DIR.mkdir(exist_ok=True)