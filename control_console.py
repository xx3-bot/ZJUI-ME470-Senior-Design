#!/usr/bin/env python3
"""Local-development ME470 desktop control console."""

from __future__ import annotations

from pathlib import Path
import os
import sys
import sysconfig
from typing import Any


ROOT = Path(__file__).resolve().parent
CODE_DIR = ROOT / "主程序代码"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))


def _prime_qt_plugin_paths() -> None:
    """Help local venv launches find the macOS Qt platform plugin."""
    site_paths = [
        Path(sysconfig.get_paths().get("purelib", "")),
        Path(sysconfig.get_paths().get("platlib", "")),
    ]
    for site_path in site_paths:
        plugin_root = site_path / "PySide6" / "Qt" / "plugins"
        platform_root = plugin_root / "platforms"
        if (platform_root / "libqcocoa.dylib").exists():
            os.environ.setdefault("QT_PLUGIN_PATH", str(plugin_root))
            if not os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH"):
                os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platform_root)
            return


_prime_qt_plugin_paths()


try:
    from PySide6.QtCore import QCoreApplication, QLibraryInfo, QObject, QThread, Qt, Signal, Slot
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QFormLayout,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QPushButton,
        QPlainTextEdit,
        QSpinBox,
        QSplitter,
        QTabWidget,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ModuleNotFoundError as exc:
    if exc.name == "PySide6":
        print("PySide6 is not installed in this environment.")
        print("Install it once for the local-development console:")
        print("  .venv/bin/python -m pip install -r requirements-control-console.txt")
        raise SystemExit(1) from exc
    raise

from app_core import ControlConsoleService, OperationResult


DEFAULT_PICK = (220.0, 0.0, 115.0)
DEFAULT_PLACE = (0.0, 250.0, 124.25)


def _register_qt_library_paths() -> None:
    paths = []
    try:
        paths.append(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
    except Exception:
        pass
    env_plugin_path = os.environ.get("QT_PLUGIN_PATH")
    if env_plugin_path:
        paths.extend(env_plugin_path.split(os.pathsep))
    platform_path = os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH")
    if platform_path:
        paths.append(str(Path(platform_path).parent))
    for path in paths:
        if path and Path(path).exists():
            QCoreApplication.addLibraryPath(path)


class Worker(QObject):
    finished = Signal(object)

    def __init__(self, fn, *args, **kwargs) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    @Slot()
    def run(self) -> None:
        self.finished.emit(self.fn(*self.args, **self.kwargs))


class ControlConsoleWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.service = ControlConsoleService()
        self.worker_thread: QThread | None = None
        self.worker: Worker | None = None

        self.setWindowTitle("ME470 Control Console - Local Development")
        self.resize(1280, 820)

        self.status_label = QLabel("Ready")
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)

        tabs = QTabWidget()
        tabs.addTab(self._build_dashboard_tab(), "Dashboard")
        tabs.addTab(self._build_camera_tab(), "Camera")
        tabs.addTab(self._build_decision_tab(), "Decision")
        tabs.addTab(self._build_path_tab(), "Path / Commands")
        tabs.addTab(self._build_parameters_tab(), "Parameters")
        tabs.addTab(self._build_console_tab(), "Run Console")

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(tabs)
        layout.addWidget(self.status_label)
        self.setCentralWidget(root)

        self._apply_style()
        self.refresh_all()

    def _build_dashboard_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.project_status = QPlainTextEdit()
        self.project_status.setReadOnly(True)

        controls = QHBoxLayout()
        refresh = QPushButton("Refresh Status")
        refresh.clicked.connect(self.refresh_all)
        prepare = QPushButton("Dry-Run Auto Demo")
        prepare.clicked.connect(self.prepare_detected_books_run)
        controls.addWidget(refresh)
        controls.addWidget(prepare)
        controls.addStretch(1)

        layout.addLayout(controls)
        layout.addWidget(self.project_status)
        return tab

    def _build_camera_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        controls = QHBoxLayout()
        scan = QPushButton("Scan One Frame")
        scan.clicked.connect(self.scan_books)
        reload_images = QPushButton("Reload Latest Overlays")
        reload_images.clicked.connect(self.refresh_images)
        controls.addWidget(scan)
        controls.addWidget(reload_images)
        controls.addStretch(1)

        self.scan_result = QPlainTextEdit()
        self.scan_result.setReadOnly(True)
        self.image_grid = QGridLayout()

        layout.addLayout(controls)
        layout.addLayout(self.image_grid)
        layout.addWidget(self.scan_result)
        return tab

    def _build_decision_tab(self) -> QWidget:
        tab = QWidget()
        splitter = QSplitter(Qt.Orientation.Vertical)

        self.task_table = QTableWidget(0, 6)
        self.task_table.setHorizontalHeaderLabels(["#", "Title", "Pick", "Place", "Commands", "Human Place"])
        self.decision_report = QPlainTextEdit()
        self.decision_report.setReadOnly(True)

        splitter.addWidget(self.task_table)
        splitter.addWidget(self.decision_report)
        splitter.setSizes([280, 520])

        layout = QVBoxLayout(tab)
        controls = QHBoxLayout()
        refresh = QPushButton("Reload Latest Decision")
        refresh.clicked.connect(self.refresh_decision)
        dry = QPushButton("Dry-Run Auto Demo")
        dry.clicked.connect(self.prepare_detected_books_run)
        controls.addWidget(refresh)
        controls.addWidget(dry)
        controls.addStretch(1)
        layout.addLayout(controls)
        layout.addWidget(splitter)
        return tab

    def _build_path_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        form_box = QGroupBox("Target Sequence Dry-Run")
        form = QFormLayout(form_box)
        self.pick_input = QLineEdit(" ".join(str(value) for value in DEFAULT_PICK))
        self.place_input = QLineEdit(" ".join(str(value) for value in DEFAULT_PLACE))
        dry = QPushButton("Generate Target Sequence")
        dry.clicked.connect(self.run_target_sequence_dry)
        form.addRow("Pick X Y Z", self.pick_input)
        form.addRow("Place X Y Z", self.place_input)
        form.addRow("", dry)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.command_text = QPlainTextEdit()
        self.command_text.setReadOnly(True)
        self.summary_text = QPlainTextEdit()
        self.summary_text.setReadOnly(True)
        splitter.addWidget(self.command_text)
        splitter.addWidget(self.summary_text)
        splitter.setSizes([480, 760])

        refresh = QPushButton("Reload Latest Commands / Summary")
        refresh.clicked.connect(self.refresh_paths)

        layout.addWidget(form_box)
        layout.addWidget(refresh)
        layout.addWidget(splitter)
        return tab

    def _build_parameters_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        controls = QHBoxLayout()
        refresh = QPushButton("Reload Parameter Snapshot")
        refresh.clicked.connect(self.refresh_parameters)
        self.write_profiles_hint = QCheckBox("Profile editing will be added after constants are migrated")
        self.write_profiles_hint.setEnabled(False)
        controls.addWidget(refresh)
        controls.addWidget(self.write_profiles_hint)
        controls.addStretch(1)
        self.parameter_text = QPlainTextEdit()
        self.parameter_text.setReadOnly(True)
        layout.addLayout(controls)
        layout.addWidget(self.parameter_text)
        return tab

    def _build_console_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        controls = QHBoxLayout()
        clear = QPushButton("Clear")
        clear.clicked.connect(self.log_box.clear)
        controls.addWidget(clear)
        controls.addStretch(1)
        layout.addLayout(controls)
        layout.addWidget(self.log_box)
        return tab

    def refresh_all(self) -> None:
        self.refresh_status()
        self.refresh_decision()
        self.refresh_paths()
        self.refresh_parameters()
        self.refresh_images()

    def refresh_status(self) -> None:
        status = self.service.project_status()
        self.project_status.setPlainText(_format_json(status))
        self.status_label.setText("Status refreshed")

    def refresh_decision(self) -> None:
        snapshot = self.service.latest_snapshot()
        tasks = list(snapshot.get("tasks", []))
        self.task_table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            values = [
                task.get("index", ""),
                task.get("title", ""),
                _format_vec(task.get("pick")),
                _format_vec(task.get("place")),
                task.get("command_count", ""),
                task.get("human_place", ""),
            ]
            for col, value in enumerate(values):
                self.task_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.task_table.resizeColumnsToContents()
        self.decision_report.setPlainText(self.service.latest_decision_report())

    def refresh_paths(self) -> None:
        self.command_text.setPlainText(self.service.latest_command_text())
        self.summary_text.setPlainText(self.service.latest_summary_text())

    def refresh_parameters(self) -> None:
        self.parameter_text.setPlainText(_format_json(self.service.parameter_snapshot()))

    def refresh_images(self) -> None:
        _clear_layout(self.image_grid)
        paths = self.service.latest_visual_paths()
        if not paths:
            self.image_grid.addWidget(QLabel("No visual overlays found yet."), 0, 0)
            return
        for index, path in enumerate(paths[:4]):
            box = QGroupBox(path.name)
            layout = QVBoxLayout(box)
            label = QLabel()
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                label.setText(str(path))
            else:
                label.setPixmap(pixmap.scaled(560, 300, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            layout.addWidget(label)
            self.image_grid.addWidget(box, index // 2, index % 2)

    def scan_books(self) -> None:
        self._run_background(self.service.scan_books, self._handle_scan_result, "Scanning one camera frame...")

    def prepare_detected_books_run(self) -> None:
        self._run_background(
            self.service.prepare_detected_books_run,
            self._handle_run_result,
            "Preparing detected-books dry-run...",
        )

    def run_target_sequence_dry(self) -> None:
        try:
            pick = _parse_vec3(self.pick_input.text())
            place = _parse_vec3(self.place_input.text())
        except ValueError as exc:
            self._append_log(f"[INPUT] {exc}")
            return
        self._run_background(
            self.service.run_target_sequence_dry,
            self._handle_run_result,
            "Generating target sequence...",
            pick,
            place,
        )

    def _run_background(self, fn, handler, status: str, *args, **kwargs) -> None:
        if self.worker_thread is not None:
            self._append_log("[UI] Another operation is still running.")
            return
        self.status_label.setText(status)
        self.worker_thread = QThread()
        self.worker = Worker(fn, *args, **kwargs)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(handler)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        self.worker_thread.finished.connect(self._clear_worker)
        self.worker_thread.start()

    @Slot(object)
    def _handle_scan_result(self, result: OperationResult) -> None:
        self.status_label.setText(result.message)
        self.scan_result.setPlainText(_format_json(result.payload))
        self._append_operation_result(result)
        self.refresh_status()

    @Slot(object)
    def _handle_run_result(self, result: OperationResult) -> None:
        self.status_label.setText(result.message)
        self._append_operation_result(result)
        self.refresh_status()
        self.refresh_decision()
        self.refresh_paths()
        self.refresh_images()

    @Slot()
    def _clear_worker(self) -> None:
        self.worker_thread = None
        self.worker = None

    def _append_operation_result(self, result: OperationResult) -> None:
        self._append_log(f"[RESULT] {result.message}")
        if result.stdout:
            self._append_log(result.stdout.rstrip())
        if not result.ok:
            self._append_log(_format_json(result.payload))

    def _append_log(self, text: str) -> None:
        if not text:
            return
        self.log_box.appendPlainText(text)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f6f7f8; color: #17202a; font-size: 13px; }
            QTabWidget::pane, QGroupBox { border: 1px solid #ccd2d8; border-radius: 6px; }
            QGroupBox { margin-top: 10px; padding: 10px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QPushButton { background: #ffffff; border: 1px solid #aeb7c1; border-radius: 5px; padding: 7px 11px; }
            QPushButton:hover { background: #eaf2ff; border-color: #6b95d8; }
            QPlainTextEdit, QLineEdit, QTableWidget { background: #ffffff; border: 1px solid #ccd2d8; border-radius: 5px; }
            QLabel { padding: 2px; }
            """
        )


def _parse_vec3(text: str) -> tuple[float, float, float]:
    parts = text.replace(",", " ").split()
    if len(parts) != 3:
        raise ValueError("Please enter exactly three values: X Y Z.")
    return (float(parts[0]), float(parts[1]), float(parts[2]))


def _format_vec(value: Any) -> str:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return ""
    return f"({float(value[0]):.1f}, {float(value[1]):.1f}, {float(value[2]):.1f})"


def _format_json(value: Any) -> str:
    return json_dumps(value)


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        if child_layout is not None:
            _clear_layout(child_layout)


def main() -> int:
    _register_qt_library_paths()
    app = QApplication(sys.argv)
    window = ControlConsoleWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
