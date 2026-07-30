#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


HERE = Path(__file__).resolve().parent
COMPOSE_FILE = HERE / "docker-compose.yml"
MANIFEST_FILE = HERE / "fixture-manifest.json"
DISPOSABLE_MARKER = "datalox-elabftw-reference-v0"
REFERENCE_TITLE = "Datalox AMR analysis handoff"
REFERENCE_BODY = "<p>Reference AMR analysis handoff for isolate AMR-ISO-001.</p>"
REFERENCE_METADATA = {
    "extra_fields": {
        "isolate_id": {
            "type": "text",
            "value": "AMR-ISO-001",
            "description": "Stable isolate identifier used across the analysis handoff",
        }
    }
}
RUNTIME_ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "HOME",
        "TMPDIR",
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_CONFIG",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    }
)


class FixtureError(RuntimeError):
    pass


@dataclass(frozen=True)
class FixtureCredentials:
    database_password: str
    root_password: str
    secret_key: str
    api_key: str

    @classmethod
    def generate(cls) -> "FixtureCredentials":
        return cls(
            database_password=secrets.token_urlsafe(32),
            root_password=secrets.token_urlsafe(32),
            secret_key=secrets.token_hex(64),
            api_key=secrets.token_hex(48),
        )

    def compose_environment(
        self,
        port: int,
        *,
        source_environment: Mapping[str, str] | None = None,
    ) -> dict[str, str]:
        source = os.environ if source_environment is None else source_environment
        return {
            **{
                key: source[key]
                for key in RUNTIME_ENV_ALLOWLIST
                if key in source
            },
            "ELABFTW_FIXTURE_DB_PASSWORD": self.database_password,
            "ELABFTW_FIXTURE_ROOT_PASSWORD": self.root_password,
            "ELABFTW_FIXTURE_SECRET_KEY": self.secret_key,
            "ELABFTW_FIXTURE_PORT": str(port),
        }

    def redact(self, value: str) -> str:
        redacted = value
        for secret in (
            self.database_password,
            self.root_password,
            self.secret_key,
            self.api_key,
        ):
            redacted = redacted.replace(secret, "[REDACTED]")
        return redacted


@dataclass(frozen=True)
class HttpResult:
    status: int
    headers: dict[str, str]
    body: Any


def require_loopback_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme != "http":
        raise FixtureError("eLabFTW reference fixture requires a loopback HTTP URL")
    if parsed.username or parsed.password or not parsed.hostname:
        raise FixtureError("eLabFTW reference fixture URL must not contain user info")
    hostname = parsed.hostname
    if hostname == "localhost":
        return base_url.rstrip("/")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError as exc:
        raise FixtureError("eLabFTW reference fixture refuses non-loopback hostnames") from exc
    if not address.is_loopback:
        raise FixtureError("eLabFTW reference fixture refuses non-loopback addresses")
    return base_url.rstrip("/")


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _compose_command(project: str, *args: str) -> list[str]:
    return [
        "docker-compose",
        "--project-name",
        project,
        "--file",
        str(COMPOSE_FILE),
        *args,
    ]


def _run(
    command: list[str],
    *,
    credentials: FixtureCredentials,
    port: int,
    input_text: str | None = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        env=credentials.compose_environment(port),
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        output = credentials.redact("\n".join((result.stdout, result.stderr)).strip())
        raise FixtureError(f"command failed ({result.returncode}): {command[0]}\n{output}")
    return result


def start_fixture(project: str, port: int, credentials: FixtureCredentials) -> None:
    _run(
        _compose_command(project, "up", "--detach", "--remove-orphans"),
        credentials=credentials,
        port=port,
        timeout=900,
    )
    _wait_for_mysql(project, port, credentials)
    _wait_for_loopback_port(port)
    verify_disposable_fixture(project, port, credentials)


def _wait_for_mysql(
    project: str,
    port: int,
    credentials: FixtureCredentials,
    *,
    timeout_seconds: int = 240,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = _run(
            _compose_command(project, "ps", "--quiet", "mysql"),
            credentials=credentials,
            port=port,
        )
        container_id = result.stdout.strip()
        if container_id:
            inspect = _run(
                ["docker", "inspect", container_id],
                credentials=credentials,
                port=port,
            )
            state = json.loads(inspect.stdout)[0]["State"]
            if state.get("Health", {}).get("Status") == "healthy":
                return
            if state.get("Status") == "exited":
                raise FixtureError("eLabFTW fixture database exited during startup")
        time.sleep(2)
    raise FixtureError("timed out waiting for the eLabFTW fixture database")


def _wait_for_loopback_port(port: int, *, timeout_seconds: int = 120) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return
        except OSError:
            pass
        time.sleep(2)
    raise FixtureError("timed out waiting for the eLabFTW fixture loopback port")


def verify_disposable_fixture(
    project: str,
    port: int,
    credentials: FixtureCredentials,
) -> None:
    result = _run(
        _compose_command(project, "ps", "--quiet", "web"),
        credentials=credentials,
        port=port,
    )
    container_id = result.stdout.strip()
    if not container_id:
        raise FixtureError("eLabFTW fixture web container is not running")
    inspect = _run(
        ["docker", "inspect", container_id],
        credentials=credentials,
        port=port,
    )
    container = json.loads(inspect.stdout)[0]
    image_id = container.get("Image")
    if not image_id:
        raise FixtureError("eLabFTW fixture web container has no inspectable image ID")
    image_inspect = _run(
        ["docker", "image", "inspect", image_id],
        credentials=credentials,
        port=port,
    )
    image = json.loads(image_inspect.stdout)[0]
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    _verify_inspected_web_container(
        container,
        image,
        project=project,
        port=port,
        expected_digest=manifest["images"]["web"]["digest"],
    )


def inspect_fixture_receipt(
    project: str,
    port: int,
    credentials: FixtureCredentials,
) -> dict[str, Any]:
    """Return stable, non-secret evidence derived from the running fixture."""
    verify_disposable_fixture(project, port, credentials)
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    services: dict[str, dict[str, Any]] = {}
    for service in ("web", "mysql"):
        container_id = _run(
            _compose_command(project, "ps", "--quiet", service),
            credentials=credentials,
            port=port,
        ).stdout.strip()
        if not container_id:
            raise FixtureError(f"eLabFTW fixture {service} container is not running")
        container = json.loads(
            _run(
                ["docker", "inspect", container_id],
                credentials=credentials,
                port=port,
            ).stdout
        )[0]
        image = json.loads(
            _run(
                ["docker", "image", "inspect", container["Image"]],
                credentials=credentials,
                port=port,
            ).stdout
        )[0]
        expected = manifest["images"][service]
        configured_image = container["Config"].get("Image", "")
        repo_digests = sorted(image.get("RepoDigests") or [])
        if configured_image != expected["reference"]:
            raise FixtureError(
                f"eLabFTW fixture {service} configured image does not match the manifest"
            )
        if not any(
            item.rpartition("@")[2] == expected["digest"] for item in repo_digests
        ):
            raise FixtureError(
                f"eLabFTW fixture {service} image digest does not match the manifest"
            )
        services[service] = {
            "configured_image": configured_image,
            "content_id": image["Id"],
            "content_digest": expected["digest"],
            "disposable_marker": container["Config"]
            .get("Labels", {})
            .get("org.datalox.fixture.disposable"),
        }

    return {
        "schema_id": "api_gym.elabftw_fixture_inspection.v1",
        "provider": "elabftw",
        "provider_version": manifest["provider_version"],
        "origin": f"http://127.0.0.1:{port}",
        "loopback_only": True,
        "services": services,
    }


def _verify_inspected_web_container(
    container: dict[str, Any],
    image: dict[str, Any],
    *,
    project: str,
    port: int,
    expected_digest: str,
) -> None:
    labels = container["Config"].get("Labels", {})
    if labels.get("org.datalox.fixture.disposable") != DISPOSABLE_MARKER:
        raise FixtureError("eLabFTW fixture is missing the expected disposable marker")
    if labels.get("com.docker.compose.project") != project:
        raise FixtureError("eLabFTW fixture Compose project does not match the owner")
    configured_image = container["Config"].get("Image", "")
    if configured_image.rpartition("@")[2] != expected_digest:
        raise FixtureError("eLabFTW fixture was not configured with the pinned web digest")
    if image.get("Id") != container.get("Image"):
        raise FixtureError("eLabFTW fixture image inspection does not match the running container")
    repo_digests = {
        reference.rpartition("@")[2]
        for reference in image.get("RepoDigests") or []
        if "@" in reference
    }
    if expected_digest not in repo_digests:
        raise FixtureError("eLabFTW fixture web image content digest does not match the manifest")
    bindings = container["NetworkSettings"]["Ports"].get("443/tcp") or []
    if not any(
        binding.get("HostIp") in {"127.0.0.1", "::1"}
        and binding.get("HostPort") == str(port)
        for binding in bindings
    ):
        raise FixtureError("eLabFTW fixture is not bound to the expected loopback port")


def bootstrap_fixture(
    project: str,
    port: int,
    credentials: FixtureCredentials,
) -> None:
    verify_disposable_fixture(project, port, credentials)
    populate_config = "\n".join(
        (
            "skip_confirm: true",
            "generate_random_experiments: false",
            "generate_random_resources: false",
            "config:",
            "  admin_validate: 0",
            "teams:",
            "  - name: Datalox Disposable Reference",
            "    random_users: 0",
            "    users:",
            "      - email: datalox-bootstrap@example.invalid",
            "        firstname: Datalox",
            "        lastname: Bootstrap",
            "      - email: datalox-fixture@example.invalid",
            "        firstname: Datalox",
            "        lastname: Fixture",
            f"        api_key: {credentials.api_key}",
            "",
        )
    )
    command = _compose_command(
        project,
        "exec",
        "--no-TTY",
        "web",
        "sh",
        "-c",
        (
            "umask 077; "
            "config=/tmp/datalox-reference-populate.yml; "
            "cat > \"$config\"; "
            "bin/init db:populate \"$config\" --yes; "
            "status=$?; "
            "rm -f \"$config\"; "
            "exit $status"
        ),
    )
    _run(
        command,
        credentials=credentials,
        port=port,
        input_text=populate_config,
        timeout=600,
    )
    wait_for_http(f"http://127.0.0.1:{port}")


def wait_for_http(base_url: str, *, timeout_seconds: int = 120) -> None:
    base_url = require_loopback_base_url(base_url)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{base_url}/", timeout=5) as response:
                if response.status < 500:
                    return
        except HTTPError as exc:
            if exc.code < 500:
                return
        except URLError:
            pass
        time.sleep(2)
    raise FixtureError("timed out waiting for the eLabFTW fixture HTTP service")


def destroy_fixture(
    project: str,
    port: int,
    credentials: FixtureCredentials,
) -> None:
    _run(
        _compose_command(
            project,
            "down",
            "--volumes",
            "--remove-orphans",
            "--timeout",
            "10",
        ),
        credentials=credentials,
        port=port,
        timeout=180,
    )


def _request_json(
    base_url: str,
    api_key: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> HttpResult:
    url = f"{require_loopback_base_url(base_url)}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Authorization": api_key,
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            headers = {key.lower(): value for key, value in response.headers.items()}
            return HttpResult(
                status=response.status,
                headers=headers,
                body=_decode_body(raw, headers.get("content-type", "")),
            )
    except HTTPError as exc:
        raw = exc.read()
        headers = {key.lower(): value for key, value in exc.headers.items()}
        error_body = _decode_body(raw, headers.get("content-type", ""))
        raise FixtureError(
            f"eLabFTW API returned HTTP {exc.code} for {method} {path}: {error_body!r}"
        ) from exc


def _decode_body(raw: bytes, content_type: str) -> Any:
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace")
    if "json" in content_type:
        return json.loads(text)
    return text


def _selected_headers(result: HttpResult, *, experiment_id: int | None = None) -> dict[str, str]:
    selected: dict[str, str] = {}
    if "content-type" in result.headers:
        selected["content-type"] = result.headers["content-type"]
    if "location" in result.headers:
        location = result.headers["location"]
        if experiment_id is not None:
            path = urlparse(location).path
            suffix = f"/{experiment_id}"
            if not path.endswith(suffix):
                raise FixtureError("eLabFTW create Location did not end with the experiment ID")
            location = f"{path[:-len(suffix)]}/{{experiment_id}}"
        selected["location"] = location
    return selected


def _normalise_metadata(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _selected_experiment(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "{experiment_id}",
        "title": entity.get("title"),
        "body": entity.get("body"),
        "metadata": _normalise_metadata(entity.get("metadata")),
    }


def capture_reference_sequence(
    project: str,
    port: int,
    credentials: FixtureCredentials,
) -> dict[str, Any]:
    base_url = require_loopback_base_url(f"http://127.0.0.1:{port}")
    verify_disposable_fixture(project, port, credentials)

    info = _request_json(base_url, credentials.api_key, "GET", "/api/v2/info")
    before = _request_json(base_url, credentials.api_key, "GET", "/api/v2/experiments")
    if info.status != 200 or not isinstance(info.body, dict):
        raise FixtureError("eLabFTW info observation did not return an object")
    if before.status != 200 or not isinstance(before.body, list):
        raise FixtureError("eLabFTW pre-observation did not return an experiment list")

    create = _request_json(
        base_url,
        credentials.api_key,
        "POST",
        "/api/v2/experiments",
        {},
    )
    location = create.headers.get("location", "")
    try:
        experiment_id = int(urlparse(location).path.rstrip("/").rsplit("/", 1)[1])
    except (IndexError, ValueError) as exc:
        raise FixtureError("eLabFTW create response did not contain a usable Location") from exc
    if create.status != 201:
        raise FixtureError(f"expected create status 201, got {create.status}")

    patch_body = {
        "title": REFERENCE_TITLE,
        "body": REFERENCE_BODY,
        "metadata": json.dumps(REFERENCE_METADATA, separators=(",", ":"), sort_keys=True),
    }
    patch = _request_json(
        base_url,
        credentials.api_key,
        "PATCH",
        f"/api/v2/experiments/{experiment_id}",
        patch_body,
    )
    read = _request_json(
        base_url,
        credentials.api_key,
        "GET",
        f"/api/v2/experiments/{experiment_id}",
    )
    after = _request_json(base_url, credentials.api_key, "GET", "/api/v2/experiments")
    if patch.status != 200 or not isinstance(patch.body, dict):
        raise FixtureError("eLabFTW patch did not return the updated experiment")
    if read.status != 200 or not isinstance(read.body, dict):
        raise FixtureError("eLabFTW read did not return the updated experiment")
    if after.status != 200 or not isinstance(after.body, list):
        raise FixtureError("eLabFTW post-observation did not return an experiment list")

    selected_read = _selected_experiment(read.body)
    if selected_read["title"] != REFERENCE_TITLE:
        raise FixtureError("eLabFTW GET did not preserve the patched title")
    if selected_read["body"] != REFERENCE_BODY:
        raise FixtureError("eLabFTW GET did not preserve the patched body")
    if selected_read["metadata"] != REFERENCE_METADATA:
        raise FixtureError("eLabFTW GET did not preserve the patched metadata")

    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    return {
        "schema_version": "api_gym.provider_reference_sequence.v0",
        "provider": {
            "id": "elabftw",
            "version": info.body.get("elabftw_version"),
            "image": manifest["images"]["web"],
        },
        "sequence_id": "experiments_create_patch_get_v0",
        "fixture": {
            "disposable_marker": DISPOSABLE_MARKER,
            "loopback_only": True,
            "volumes_destroyed_after_capture": True,
        },
        "evidence_sources": manifest["evidence_sources"],
        "observations": {
            "pre": {
                "accessible_experiment_count": len(before.body),
                "reference_title_present": any(
                    entry.get("title") == REFERENCE_TITLE
                    for entry in before.body
                    if isinstance(entry, dict)
                ),
            },
            "post": {
                "accessible_experiment_count": len(after.body),
                "experiment_count_delta": len(after.body) - len(before.body),
                "experiment": selected_read,
            },
        },
        "steps": [
            {
                "operation": "POST /api/v2/experiments",
                "request": {
                    "headers": {
                        "accept": "application/json",
                        "content-type": "application/json",
                    },
                    "body": {},
                },
                "response": {
                    "status": create.status,
                    "headers": _selected_headers(create, experiment_id=experiment_id),
                    "body": create.body,
                },
            },
            {
                "operation": "PATCH /api/v2/experiments/{experiment_id}",
                "request": {
                    "headers": {
                        "accept": "application/json",
                        "content-type": "application/json",
                    },
                    "body": patch_body,
                },
                "response": {
                    "status": patch.status,
                    "headers": _selected_headers(patch),
                    "body": _selected_experiment(patch.body),
                },
            },
            {
                "operation": "GET /api/v2/experiments/{experiment_id}",
                "request": {
                    "headers": {"accept": "application/json"},
                    "body": None,
                },
                "response": {
                    "status": read.status,
                    "headers": _selected_headers(read),
                    "body": selected_read,
                },
            },
        ],
    }


def exercise_fixture(output_path: Path | None = None) -> dict[str, Any]:
    project = f"datalox-elabftw-{secrets.token_hex(5)}"
    port = _free_loopback_port()
    credentials = FixtureCredentials.generate()
    owned = True
    try:
        start_fixture(project, port, credentials)
        bootstrap_fixture(project, port, credentials)
        capture = capture_reference_sequence(project, port, credentials)
    finally:
        if owned:
            destroy_fixture(project, port, credentials)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(capture, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return capture


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Exercise a disposable, loopback-only eLabFTW reference fixture."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    exercise = subparsers.add_parser(
        "exercise",
        help="Start, bootstrap, capture, and destroy one disposable fixture.",
    )
    exercise.add_argument(
        "--output",
        type=Path,
        help="Optional path for the sanitized reference sequence.",
    )
    subparsers.add_parser("manifest", help="Print the non-secret fixture manifest.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "manifest":
            print(MANIFEST_FILE.read_text(encoding="utf-8"), end="")
            return 0
        capture = exercise_fixture(args.output)
        print(
            json.dumps(
                {
                    "ok": True,
                    "provider": capture["provider"],
                    "sequence_id": capture["sequence_id"],
                    "operations": [
                        step["operation"] for step in capture["steps"]
                    ],
                    "output": str(args.output) if args.output else None,
                },
                sort_keys=True,
            )
        )
        return 0
    except FixtureError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
