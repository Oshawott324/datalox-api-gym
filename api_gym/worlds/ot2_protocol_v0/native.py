"""Run the official OT-2 protocol analyzer in a separate interpreter.

Opentrons 9.x and later refuse OT-2 protocols in ``opentrons analyze`` and
``opentrons simulate``; the OT-2 line moved to the opentrons-ot2 releases.
8.8.2 is the newest PyPI release whose analyzer still accepts OT-2 protocols,
so the analyzer interpreter is configured separately from the motion worker.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ANALYZER_ENV = "DATALOX_OT2_ANALYSIS_PYTHON"
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ANALYZER = REPO_ROOT / "runs" / "ot2-analysis-8.8.2" / "bin" / "python"
SLOT3_LABWARE = REPO_ROOT / "worlds" / "ot2_protocol_v0" / "labware" / (
    "custom_24_tuberack_eppendorf_2ml_slot3_pitch19p69.json"
)
_KEPT_PARAMS = ("labwareId", "wellName", "wellLocation", "minimumZHeight", "forceDirect", "location", "loadName",
                "namespace", "pipetteName", "mount", "pipetteId", "addressableAreaName")


@dataclass(frozen=True)
class AnalyzedCommand:
    command_type: str
    status: str
    params: dict[str, Any]
    error_detail: str | None = None


@dataclass(frozen=True)
class AnalysisResult:
    """The parts of an official analysis that tasks and checks read."""

    result: str
    errors: tuple[str, ...]
    commands: tuple[AnalyzedCommand, ...]
    labware_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    pipettes_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    analyzer_version: str | None = None

    @property
    def ok(self) -> bool:
        return self.result == "ok" and not self.errors

    def public_summary(self) -> dict[str, Any]:
        """What a person running ``opentrons analyze`` would see."""
        return {
            "result": self.result,
            "errors": list(self.errors),
            "command_count": len(self.commands),
            "failed_commands": [
                {"commandType": c.command_type, "error": c.error_detail}
                for c in self.commands
                if c.status == "failed"
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "errors": list(self.errors),
            "analyzer_version": self.analyzer_version,
            "commands": [
                {"commandType": c.command_type, "status": c.status, "params": c.params, "error": c.error_detail}
                for c in self.commands
            ],
            "labware_by_id": self.labware_by_id,
            "pipettes_by_id": self.pipettes_by_id,
        }


def analysis_from_json(raw: dict[str, Any], analyzer_version: str | None = None) -> AnalysisResult:
    commands = []
    labware_by_id: dict[str, dict[str, Any]] = {}
    pipettes_by_id: dict[str, dict[str, Any]] = {}
    for item in raw.get("commands", []):
        params = {key: item.get("params", {}).get(key) for key in _KEPT_PARAMS if key in item.get("params", {})}
        error = item.get("error") or {}
        commands.append(
            AnalyzedCommand(
                command_type=item["commandType"],
                status=item.get("status", "unknown"),
                params=params,
                error_detail=error.get("detail") if error else None,
            )
        )
        if item["commandType"] == "loadLabware" and item.get("status") == "succeeded":
            labware_id = (item.get("result") or {}).get("labwareId")
            if labware_id:
                location = item.get("params", {}).get("location") or {}
                labware_by_id[labware_id] = {
                    "slot": str(location.get("slotName")) if isinstance(location, dict) else None,
                    "load_name": item["params"].get("loadName"),
                    "namespace": item["params"].get("namespace"),
                }
        if item["commandType"] == "loadPipette" and item.get("status") == "succeeded":
            pipette_id = (item.get("result") or {}).get("pipetteId")
            if pipette_id:
                pipettes_by_id[pipette_id] = {
                    "name": item["params"].get("pipetteName"),
                    "mount": item["params"].get("mount"),
                }
    errors = tuple(str(error.get("detail", "")) for error in raw.get("errors", []))
    return AnalysisResult(
        result=str(raw.get("result", "unknown")),
        errors=errors,
        commands=tuple(commands),
        labware_by_id=labware_by_id,
        pipettes_by_id=pipettes_by_id,
        analyzer_version=analyzer_version,
    )


class OfficialAnalyzer:
    """Runs ``python -m opentrons.cli analyze`` in the pinned OT-2 interpreter."""

    def __init__(self, python: str | Path | None = None, timeout_s: float = 120.0) -> None:
        configured = python or os.environ.get(ANALYZER_ENV) or DEFAULT_ANALYZER
        self.python = Path(configured)
        self.timeout_s = timeout_s
        self._version: str | None = None

    @classmethod
    def available(cls, python: str | Path | None = None) -> bool:
        analyzer = cls(python)
        return analyzer.python.is_file() and os.access(analyzer.python, os.X_OK)

    def version(self) -> str:
        if self._version is None:
            completed = subprocess.run(
                [str(self.python), "-c", "import opentrons; print(opentrons.__version__)"],
                capture_output=True, text=True, timeout=self.timeout_s, check=True,
                env=self._env(tempfile.mkdtemp(prefix="ot2-analyzer-home-")),
            )
            self._version = completed.stdout.strip()
        return self._version

    def analyze(self, source: str, extra_labware: tuple[Path, ...] = (SLOT3_LABWARE,)) -> AnalysisResult:
        with tempfile.TemporaryDirectory(prefix="ot2-analysis-") as work:
            protocol = Path(work) / "protocol.py"
            protocol.write_text(source)
            output = Path(work) / "analysis.json"
            command = [str(self.python), "-m", "opentrons.cli", "analyze", "--json-output", str(output),
                       str(protocol), *[str(path) for path in extra_labware]]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=self.timeout_s,
                                       env=self._env(work), cwd=work)
            if not output.exists():
                detail = (completed.stderr or completed.stdout).strip().splitlines()
                message = detail[-1] if detail else f"analyzer exited with {completed.returncode}"
                return AnalysisResult(result="not-ok", errors=(message,), commands=(),
                                      analyzer_version=self.version())
            return analysis_from_json(json.loads(output.read_text()), self.version())

    @staticmethod
    def _env(home: str) -> dict[str, str]:
        config_dir = Path(home) / "opentrons-config"
        config_dir.mkdir(parents=True, exist_ok=True)
        return {"HOME": home, "OT_API_CONFIG_DIR": str(config_dir), "PATH": os.environ.get("PATH", "")}
