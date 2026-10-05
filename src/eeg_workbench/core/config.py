"""Application configuration management (singleton, YAML-based)."""
from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
import yaml
from threading import Lock


@dataclass
class AppConfig:
    """全局配置，自动持久化到 ~/.config/eeg-workbench/config.yaml"""
    # 最近打开的文件列表
    recent_files: list[str] = field(default_factory=list)
    # 最大最近文件数
    max_recent_files: int = 10
    # 默认滤波参数
    default_filter: dict[str, Any] = field(default_factory=lambda: {
        "l_freq": 0.1,
        "h_freq": 40.0,
        "notch_freq": 50.0,
    })
    # 默认参考电极
    default_reference: str = "average"
    # UI 主题
    theme: str = "system"  # system, light, dark
    # 语言
    language: str = "zh_CN"
    # GPU 加速开关
    use_gpu: bool = False
    # 并行作业数
    n_jobs: int = -1
    # 缓存目录
    cache_dir: str = str(Path.home() / ".cache" / "eeg-workbench")
    # 自定义频段定义
    custom_bands: dict[str, tuple[float, float]] = field(default_factory=lambda: {
        "Delta": (0.5, 4),
        "Theta": (4, 8),
        "Alpha": (8, 13),
        "Beta": (13, 30),
        "Gamma": (30, 45),
    })

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> AppConfig:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class _ConfigManager:
    """线程安全的配置单例管理器"""
    _instance: Optional[_ConfigManager] = None
    _lock = Lock()
    _initialized: bool = False

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._config_path = self._get_config_path()
        self._config = self._load()
        self._initialized = True

    def _get_config_path(self) -> Path:
        if os.name == "nt":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        cfg_dir = base / "eeg-workbench"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        return cfg_dir / "config.yaml"

    def _load(self) -> AppConfig:
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                return AppConfig.from_dict(data)
            except Exception:
                pass
        return AppConfig()

    def save(self) -> None:
        with open(self._config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self._config.to_dict(), f, allow_unicode=True)

    @property
    def config(self) -> AppConfig:
        return self._config

    def update(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self._config, k):
                setattr(self._config, k, v)
        self.save()

    def add_recent_file(self, path: str) -> None:
        path = str(Path(path).resolve())
        if path in self._config.recent_files:
            self._config.recent_files.remove(path)
        self._config.recent_files.insert(0, path)
        self._config.recent_files = self._config.recent_files[: self._config.max_recent_files]
        self.save()


# 全局访问入口
_config_manager: Optional[_ConfigManager] = None


def get_config() -> AppConfig:
    global _config_manager
    if _config_manager is None:
        _config_manager = _ConfigManager()
    return _config_manager.config


def get_config_manager() -> _ConfigManager:
    global _config_manager
    if _config_manager is None:
        _config_manager = _ConfigManager()
    return _config_manager