"""基类：可观察模型、ViewModel 基类、命令封装。"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar, Generic
from weakref import WeakSet
import uuid
from threading import Lock
from PySide6.QtCore import QObject, Signal, Slot, QThreadPool, QRunnable, QTimer
from PySide6.QtWidgets import QApplication


T = TypeVar("T")


class ObservableModel:
    """可观察模型基类：属性变更自动通知订阅者（用于 MVVM 绑定）"""

    def __init__(self):
        self._observers: WeakSet[Callable[[str, Any, Any], None]] = WeakSet()
        self._lock = Lock()
        self._dirty = False

    def _lazy_init(self) -> None:
        """惰性初始化观察者容器。

        dataclass 子类的字段在 ``__init__`` 期间就会走 ``__setattr__``,
        早于 ``__init__``/``__post_init__`` 赋值 ``_lock``, 因此必须惰性补齐。
        """
        d = self.__dict__
        if "_lock" not in d:
            super(ObservableModel, self).__setattr__("_observers", WeakSet())
            super(ObservableModel, self).__setattr__("_lock", Lock())
            super(ObservableModel, self).__setattr__("_dirty", False)

    def add_observer(self, callback: Callable[[str, Any, Any], None]) -> None:
        self._lazy_init()
        self._observers.add(callback)

    def remove_observer(self, callback: Callable[[str, Any, Any], None]) -> None:
        self._lazy_init()
        self._observers.discard(callback)

    def _notify(self, prop: str, old: Any, new: Any) -> None:
        self._lazy_init()
        with self._lock:
            self._dirty = True
            for cb in list(self._observers):
                try:
                    cb(prop, old, new)
                except Exception as e:
                    print(f"[ObservableModel] Observer error: {e}")

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_") or name in {"_observers", "_lock", "_dirty"}:
            super().__setattr__(name, value)
            return
        old = getattr(self, name, object())
        if old is not object():
            try:
                if old == value:
                    return
            except Exception:
                pass  # ndarray 等不可直接比较的值：照常通知
        super().__setattr__(name, value)
        self._lazy_init()
        self._notify(name, old, value)

    @property
    def is_dirty(self) -> bool:
        return self.__dict__.get("_dirty", False)

    def mark_clean(self) -> None:
        self._lazy_init()
        self._dirty = False


class Command(QObject):
    """异步命令封装：可取消、进度汇报、错误处理"""
    started = Signal()
    finished = Signal(object)  # result
    failed = Signal(str)       # error message
    progress = Signal(int, int, str)  # current, total, message

    def __init__(self, func: Callable[..., Any], *args, **kwargs):
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._cancelled = False
        self._result = None
        self._error = None

    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def execute(self) -> None:
        try:
            self.started.emit()
        except RuntimeError:
            return  # 信号宿主（窗口/VM）已销毁，放弃执行
        try:
            # 支持生成器风格进度汇报
            result = self._func(*self._args, **self._kwargs)
            if self._cancelled:
                return
            self._result = result
            try:
                self.finished.emit(result)
            except RuntimeError:
                pass  # 接收方已随窗口销毁，静默丢弃
        except Exception as e:
            self._error = str(e)
            try:
                self.failed.emit(self._error)
            except RuntimeError:
                pass  # 接收方已销毁，静默丢弃

    @property
    def result(self) -> Any:
        return self._result

    @property
    def error(self) -> str | None:
        return self._error


class ViewModelBase(QObject):
    """ViewModel 基类：命令管理、忙碌状态、错误聚合"""

    # 通用状态信号
    busy_changed = Signal(bool)
    error_occurred = Signal(str)
    status_message = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._busy_count = 0
        self._thread_pool = QThreadPool.globalInstance()
        self._active_commands: List[Command] = []

    @property
    def is_busy(self) -> bool:
        return self._busy_count > 0

    def _set_busy(self, busy: bool) -> None:
        if busy:
            self._busy_count += 1
        else:
            self._busy_count = max(0, self._busy_count - 1)
        self.busy_changed.emit(self.is_busy)

    def run_command(self, cmd: Command) -> None:
        """在线程池中运行命令，自动管理忙碌状态"""
        self._active_commands.append(cmd)
        self._set_busy(True)

        def on_finished(result):
            self._active_commands.remove(cmd)
            self._set_busy(False)

        def on_failed(err):
            self._active_commands.remove(cmd)
            self._set_busy(False)
            self.error_occurred.emit(err)

        cmd.finished.connect(on_finished)
        cmd.failed.connect(on_failed)
        self._thread_pool.start(cmd.execute)

    def cancel_all_commands(self) -> None:
        for cmd in self._active_commands:
            cmd.cancel()
        self._active_commands.clear()
        self._set_busy(False)

    def show_status(self, msg: str, timeout: int = 3000) -> None:
        self.status_message.emit(msg)
        if timeout > 0:
            QTimer.singleShot(timeout, lambda: self.status_message.emit(""))


# 便捷装饰器
def async_slot(func: Callable) -> Callable:
    """将同步槽函数包装为异步执行（不阻塞 UI）"""
    from functools import wraps

    @wraps(func)
    def wrapper(self: ViewModelBase, *args, **kwargs):
        cmd = Command(func, self, *args, **kwargs)
        self.run_command(cmd)
        return cmd

    return wrapper