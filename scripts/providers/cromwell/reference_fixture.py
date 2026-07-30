#!/usr/bin/env python3
"""Disposable loopback Cromwell 92 fixture for provider behavior capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from api_gym.provider_components.cromwell.success_behavior import (
    CROMWELL_JAR_SHA256,
    CROMWELL_JAR_SIZE,
    DISPOSABLE_ROOT,
    ORIGIN,
    PORT,
    PROVIDER_VERSION,
    build_fixture_receipt,
)

OWNERSHIP_MARKER = b"datalox-cromwell-92-workflow-success-v1\n"
STARTUP_TIMEOUT_SECONDS = 240
SHUTDOWN_TIMEOUT_SECONDS = 45
RUNTIME_ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "LANG",
        "LC_ALL",
        "TZ",
    }
)


class FixtureError(RuntimeError):
    pass


@dataclass
class RunningFixture:
    process: subprocess.Popen[bytes]
    root: Path
    port: int
    stdout_handle: BinaryIO
    stderr_handle: BinaryIO
    ownership_marker: bytes
    fixture_receipt: dict[str, Any]


def validate_cromwell_jar(jar_path: Path) -> None:
    if not jar_path.is_file():
        raise FixtureError("Cromwell JAR must be an explicit regular file")
    size = jar_path.stat().st_size
    if size != CROMWELL_JAR_SIZE:
        raise FixtureError(
            f"Cromwell JAR size must be exactly {CROMWELL_JAR_SIZE} bytes, got {size}"
        )
    digest = hashlib.sha256()
    with jar_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    observed = f"sha256:{digest.hexdigest()}"
    if observed != CROMWELL_JAR_SHA256:
        raise FixtureError(
            "Cromwell JAR SHA-256 does not match the pinned official release asset"
        )


def validate_java_17(java_bin: Path) -> None:
    if not java_bin.is_file() or not os.access(java_bin, os.X_OK):
        raise FixtureError("Java executable must be an explicit executable file")
    try:
        result = subprocess.run(
            [str(java_bin), "-version"],
            capture_output=True,
            check=False,
            timeout=15,
            env=_validation_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise FixtureError("failed to execute the explicit Java binary") from error
    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    if result.returncode != 0:
        raise FixtureError("explicit Java binary returned a nonzero version result")
    match = re.search(r'(?:java|openjdk) version "([^"]+)"', output)
    if match is None:
        raise FixtureError("explicit Java binary did not report a parseable version")
    version = match.group(1)
    first = version.split(".", 1)[0]
    major_text = version.split(".", 2)[1] if first == "1" else first
    if not major_text.isascii() or not major_text.isdigit() or int(major_text) != 17:
        raise FixtureError(f"Cromwell 92 fixture requires Java major 17, got {version}")


def assert_fixture_available(*, root: Path, port: int) -> None:
    if root.exists() or root.is_symlink():
        raise FixtureError(f"fixture root already exists: {root}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as error:
            raise FixtureError(f"fixed loopback port {port} is already occupied") from error


def cromwell_config(root: Path, port: int) -> str:
    return "\n".join(
        (
            'include required(classpath("application"))',
            "",
            "webservice {",
            '  interface = "127.0.0.1"',
            f"  port = {port}",
            "}",
            "",
            (
                'database.db.url = "jdbc:hsqldb:file:'
                f"{root}/db/cromwell;shutdown=false;hsqldb.tx=mvcc"
                '"'
            ),
            'backend.default = "Local"',
            f'backend.providers.Local.config.root = "{root}/executions"',
            f'workflow-options.workflow-log-dir = "{root}/workflow-logs"',
            "system.abort-jobs-on-terminate = true",
            "",
        )
    )


def inspect_fixture_receipt(fixture: RunningFixture) -> dict[str, Any]:
    if fixture.process.poll() is not None:
        raise FixtureError("Cromwell fixture process is not running")
    _verify_owned_root(fixture.root, fixture.ownership_marker)
    _assert_exact_readiness(fixture.port)
    return fixture.fixture_receipt


@contextmanager
def disposable_cromwell_fixture(
    *,
    jar_path: Path,
    java_bin: Path,
    root: Path = DISPOSABLE_ROOT,
    port: int = PORT,
    ownership_marker: bytes = OWNERSHIP_MARKER,
    fixture_receipt: dict[str, Any] | None = None,
) -> Iterator[RunningFixture]:
    validate_cromwell_jar(jar_path)
    validate_java_17(java_bin)
    receipt = build_fixture_receipt() if fixture_receipt is None else fixture_receipt
    _validate_fixture_parameters(
        root=root,
        port=port,
        ownership_marker=ownership_marker,
        fixture_receipt=receipt,
    )
    assert_fixture_available(root=root, port=port)

    fixture: RunningFixture | None = None
    owned_root = False
    try:
        _create_owned_root(root, ownership_marker)
        owned_root = True
        config_path = root / "cromwell.conf"
        config_path.write_text(cromwell_config(root, port), encoding="ascii")
        stdout_handle = (root / "server.stdout.log").open("xb")
        stderr_handle = (root / "server.stderr.log").open("xb")
        try:
            process = subprocess.Popen(
                [
                    str(java_bin),
                    f"-Djava.io.tmpdir={root}/tmp",
                    f"-Dconfig.file={config_path}",
                    "-jar",
                    str(jar_path),
                    "server",
                ],
                cwd=root,
                env=_runtime_environment(root),
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
            )
        except Exception:
            stdout_handle.close()
            stderr_handle.close()
            raise
        fixture = RunningFixture(
            process=process,
            root=root,
            port=port,
            stdout_handle=stdout_handle,
            stderr_handle=stderr_handle,
            ownership_marker=ownership_marker,
            fixture_receipt=receipt,
        )
        _wait_for_exact_readiness(fixture)
        yield fixture
    finally:
        if fixture is not None:
            destroy_fixture(fixture)
        elif owned_root:
            _delete_owned_root(root, ownership_marker)


def destroy_fixture(fixture: RunningFixture) -> None:
    process = fixture.process
    try:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=10)
    finally:
        fixture.stdout_handle.close()
        fixture.stderr_handle.close()
    _wait_for_port_release(fixture.port)
    _delete_owned_root(fixture.root, fixture.ownership_marker)


def _validation_environment() -> dict[str, str]:
    return {
        key: os.environ[key]
        for key in RUNTIME_ENV_ALLOWLIST
        if key in os.environ
    }


def _runtime_environment(root: Path) -> dict[str, str]:
    return {
        **_validation_environment(),
        "HOME": f"{root}/home",
        "TMPDIR": f"{root}/tmp",
    }


def _validate_fixture_parameters(
    *,
    root: Path,
    port: int,
    ownership_marker: bytes,
    fixture_receipt: dict[str, Any],
) -> None:
    if not root.is_absolute() or root.parent != Path("/tmp"):
        raise FixtureError("fixture root must be a direct absolute child of /tmp")
    if not root.name.startswith("datalox-cromwell-92-workflow-"):
        raise FixtureError("fixture root must use the Cromwell 92 Datalox prefix")
    if type(port) is not int or not 1024 <= port <= 65_535:
        raise FixtureError("fixture port must be a fixed non-privileged TCP port")
    if (
        type(ownership_marker) is not bytes
        or not ownership_marker.startswith(b"datalox-cromwell-92-workflow-")
        or not ownership_marker.endswith(b"\n")
    ):
        raise FixtureError("fixture ownership marker is invalid")
    expected_origin = f"http://127.0.0.1:{port}"
    if fixture_receipt.get("origin") != expected_origin:
        raise FixtureError("fixture receipt origin does not match the fixed loopback port")
    paths = fixture_receipt.get("paths")
    database = fixture_receipt.get("database")
    if not isinstance(paths, dict) or not isinstance(database, dict):
        raise FixtureError("fixture receipt must declare paths and database")
    if paths.get("disposable_root") != str(root):
        raise FixtureError("fixture receipt root does not match the disposable root")
    if paths.get("execution_root") != f"{root}/executions":
        raise FixtureError("fixture receipt execution root does not match")
    if paths.get("workflow_log_root") != f"{root}/workflow-logs":
        raise FixtureError("fixture receipt workflow log root does not match")
    if database.get("path_prefix") != f"{root}/db/":
        raise FixtureError("fixture receipt database root does not match")


def _create_owned_root(root: Path, ownership_marker: bytes) -> None:
    try:
        root.mkdir(mode=0o700)
    except FileExistsError as error:
        raise FixtureError(f"fixture root already exists: {root}") from error
    (root / ".datalox-fixture-owner").write_bytes(ownership_marker)
    for name in ("db", "executions", "workflow-logs", "tmp", "home"):
        (root / name).mkdir(mode=0o700)


def _verify_owned_root(root: Path, ownership_marker: bytes) -> None:
    marker = root / ".datalox-fixture-owner"
    if not root.is_dir() or marker.read_bytes() != ownership_marker:
        raise FixtureError("refusing to operate on a root without the exact ownership marker")


def _delete_owned_root(root: Path, ownership_marker: bytes) -> None:
    _verify_owned_root(root, ownership_marker)
    shutil.rmtree(root)


def _wait_for_exact_readiness(fixture: RunningFixture) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if fixture.process.poll() is not None:
            raise FixtureError(
                "Cromwell exited during startup\n"
                f"stdout:\n{_tail(fixture.root / 'server.stdout.log')}\n"
                f"stderr:\n{_tail(fixture.root / 'server.stderr.log')}"
            )
        try:
            _assert_exact_readiness(fixture.port)
            return
        except (ConnectionError, TimeoutError, URLError):
            time.sleep(1)
        except HTTPError as error:
            if error.code >= 500:
                time.sleep(1)
                continue
            raise FixtureError(
                f"Cromwell readiness returned unexpected HTTP {error.code}"
            ) from error
    raise FixtureError("timed out waiting for exact Cromwell 92 version/status readiness")


def _assert_exact_readiness(port: int) -> None:
    version = _read_json(port, "/engine/v1/version")
    if version != {"cromwell": PROVIDER_VERSION}:
        raise FixtureError(f"Cromwell version readiness was not exactly {PROVIDER_VERSION}")
    status = _read_json(port, "/engine/v1/status")
    if status != {}:
        raise FixtureError("Cromwell engine status readiness was not exactly an empty object")


def _read_json(port: int, path: str) -> Any:
    request = Request(
        f"http://127.0.0.1:{port}{path}",
        method="GET",
        headers={"Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=5) as response:
            raw = response.read(1 << 20)
            if response.status != 200:
                raise FixtureError(f"readiness path {path} returned {response.status}")
    except HTTPError:
        raise
    except (OSError, URLError) as error:
        raise ConnectionError(path) from error
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FixtureError(f"readiness path {path} did not return exact JSON") from error


def _wait_for_port_release(port: int) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return
        time.sleep(0.25)
    raise FixtureError(f"fixed loopback port {port} remained occupied after shutdown")


def _tail(path: Path, max_bytes: int = 4096) -> str:
    if not path.is_file():
        return "<missing>"
    with path.open("rb") as handle:
        handle.seek(max(0, path.stat().st_size - max_bytes))
        return handle.read(max_bytes).decode("utf-8", errors="replace")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and exercise the disposable Cromwell 92 fixture."
    )
    parser.add_argument("--jar", type=Path)
    parser.add_argument("--java-bin", type=Path)
    return parser


def _explicit_path(argument: Path | None, environment_name: str) -> Path:
    if argument is not None:
        return argument
    value = os.environ.get(environment_name)
    if not value:
        raise FixtureError(
            f"provide --{environment_name.lower().replace('_', '-')} "
            f"or set {environment_name}"
        )
    return Path(value)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        jar_path = _explicit_path(args.jar, "CROMWELL_92_JAR")
        java_bin = _explicit_path(args.java_bin, "CROMWELL_JAVA_BIN")
        with disposable_cromwell_fixture(
            jar_path=jar_path,
            java_bin=java_bin,
        ) as fixture:
            receipt = inspect_fixture_receipt(fixture)
    except FixtureError as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "origin": ORIGIN, "receipt": receipt}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
