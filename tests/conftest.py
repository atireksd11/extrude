"""Shared pytest hooks."""

import ipaddress
import os
import socket
import urllib.request
from pathlib import Path

import pytest

_CANDIDATES = (
    Path(r"C:\Program Files\OpenSCAD\openscad.exe"),
    Path(r"C:\Program Files (x86)\OpenSCAD\openscad.exe"),
)


def pytest_configure(config) -> None:  # noqa: ANN001
    if not config.getoption("--run-live"):
        env = pytest.MonkeyPatch()
        env.setenv("EXTRUDE_LOAD_ENV", "0")
        config.add_cleanup(env.undo)
    if os.environ.get("OPENSCAD_PATH", "").strip():
        return
    for candidate in _CANDIDATES:
        if candidate.is_file():
            os.environ["OPENSCAD_PATH"] = str(candidate)
            break


def pytest_addoption(parser) -> None:  # noqa: ANN001
    parser.addoption("--run-live", action="store_true", default=False,
                     help="Run tests marked live with real network access")


def pytest_collection_modifyitems(items) -> None:  # noqa: ANN001
    atlas = {"test_project_map_product.py", "test_stabilization.py", "test_github_history.py",
             "test_github_workspace.py", "test_kicad_pcb.py", "test_kicad_audit.py", "test_workspace_phase3.py", "test_workspace_phase4.py"}
    for item in items:
        item.add_marker("atlas" if item.path.name in atlas else "legacy")


@pytest.fixture(autouse=True)
def offline_by_default(request, monkeypatch):  # noqa: ANN001
    """A developer's .env must never turn the offline suite into a paid run."""
    if request.node.get_closest_marker("live"):
        if not request.config.getoption("--run-live"):
            pytest.skip("live test requires --run-live")
        return
    for key in ("EXTRUDE_MODEL_KEY", "OPENAI_API_KEY", "EXTRUDE_ESCALATION_KEY"):
        monkeypatch.setenv(key, "")
    monkeypatch.setenv("EXTRUDE_GITHUB_OFFLINE", "1")
    monkeypatch.setenv("EXTRUDE_GITHUB_TOKEN", "")

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def deny_urlopen(*_args, **_kwargs):
        raise AssertionError("Outbound HTTP is disabled in the offline test suite")

    monkeypatch.setattr(urllib.request, "urlopen", deny_urlopen)

    def local_only(original):
        def guarded(sock, address):
            host = address[0] if isinstance(address, tuple) else ""
            try:
                loopback = ipaddress.ip_address(host).is_loopback
            except ValueError:
                loopback = False
            if not loopback:
                raise AssertionError("External network access is disabled in the offline test suite")
            return original(sock, address)
        return guarded

    monkeypatch.setattr(socket.socket, "connect", local_only(original_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", local_only(original_connect_ex))
