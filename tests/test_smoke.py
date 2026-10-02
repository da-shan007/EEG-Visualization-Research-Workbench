"""Smoke tests for a delivery-ready startup path."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from eeg_workbench.main import MainWindow


def test_main_window_boots():
    """The primary app window should be constructible without startup crashes."""
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    assert window.objectName() == "MainWindow"
    assert window.windowTitle() == "EEG Visualization Research Workbench"

    window.close()
    app.processEvents()
