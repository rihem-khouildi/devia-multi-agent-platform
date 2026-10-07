import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree

from config.settings import Settings
from utils.logger import get_logger

logger = get_logger(__name__)

_raw_timeout = os.getenv("TARGET_VALIDATION_TIMEOUT_SECONDS", "120")
try:
    MAVEN_TIMEOUT_SECONDS = int(_raw_timeout)
except ValueError:
    logger.warning(
        "TARGET_VALIDATION_TIMEOUT_SECONDS='%s' is not a valid integer, using 120",
        _raw_timeout,
    )
    MAVEN_TIMEOUT_SECONDS = 120
POM_NS = {"m": "http://maven.apache.org/POM/4.0.0"}


def resolve_target_repo_path(settings: Settings, override_path: Optional[str] = None) -> Path:
    candidate = Path((override_path or "").strip()) if override_path else Path(settings.pipeline.target_repo_path)
    if not candidate.is_absolute():
        candidate = settings.pipeline.resolve_path(candidate)
    return candidate.resolve()


def is_generated_output_path(path: str | Path) -> bool:
    normalized = str(path).replace("/", "\\").lower()
    return "\\output\\generated" in normalized


def _bases_dir(settings: Settings) -> Path:
    """Root directory where incremental base snapshots are stored (output/bases/)."""
    return Path(settings.pipeline.output_dir).parent / "bases"


def get_incremental_base_path(story_id: str, settings: Settings) -> Optional[Path]:
    """Return the path to a ready incremental base snapshot, or None if not available."""
    candidate = _bases_dir(settings) / story_id
    if candidate.exists() and (candidate / "pom.xml").exists():
        return candidate
    return None


def create_incremental_base(story_id: str, settings: Settings) -> Path:
    """
    Build an incremental base project for story_id by merging:
      1. base-spring-project (full Maven structure)
      2. output/generated/{story_id}/ (generated Java sources overlay)

    Result stored at output/bases/{story_id}/ — valid as repo_path for the next run.
    Idempotent: if the snapshot already exists it is returned as-is.
    """
    bases = _bases_dir(settings)
    bases.mkdir(parents=True, exist_ok=True)
    snapshot = bases / story_id

    if snapshot.exists() and (snapshot / "pom.xml").exists():
        logger.info("Incremental base already exists — skipping creation: %s", snapshot)
        return snapshot

    base_source = resolve_target_repo_path(settings)
    if not base_source.exists():
        raise FileNotFoundError(f"Base project not found at {base_source}")

    if snapshot.exists():
        shutil.rmtree(snapshot)

    shutil.copytree(
        str(base_source),
        str(snapshot),
        ignore=shutil.ignore_patterns("target", ".git", "*.class"),
    )
    logger.info("Incremental base: copied base project %s → %s", base_source.name, snapshot)

    generated = Path(settings.pipeline.output_dir) / story_id
    if generated.exists():
        overlay_count = 0
        for src in generated.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(generated)
            dst = snapshot / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            overlay_count += 1
        logger.info("Incremental base: overlaid %d generated file(s) from %s", overlay_count, story_id)
    else:
        logger.warning("Incremental base: no generated output found for %s — using base project only", story_id)

    logger.info(
        "base_project_type=incremental selected_base_project=%s resolved_base_project_path=%s",
        story_id, snapshot,
    )
    return snapshot


def safe_source_repo_path(settings: Settings, requested_path: Optional[str] = None) -> Path:
    fallback = resolve_target_repo_path(settings)
    if not requested_path:
        logger.info("base_project_type=base resolved_base_project_path=%s", fallback)
        return fallback

    candidate = resolve_target_repo_path(settings, requested_path)

    if not is_generated_output_path(candidate):
        logger.info("base_project_type=custom resolved_base_project_path=%s", candidate)
        return candidate

    # Path points to output/generated/{story_id} — redirect to output/bases/{story_id}
    story_id = candidate.name
    logger.info("selected_base_project=%s — resolving incremental base", story_id)

    existing = get_incremental_base_path(story_id, settings)
    if existing:
        logger.info(
            "base_project_type=incremental resolved_base_project_path=%s (pre-built)", existing
        )
        return existing

    try:
        built = create_incremental_base(story_id, settings)
        return built
    except Exception as exc:
        logger.warning(
            "Could not build incremental base for %s (%s) — falling back to base project",
            story_id, exc,
        )
        return fallback


def get_target_project(settings: Settings) -> Dict[str, Any]:
    target_path = resolve_target_repo_path(settings)
    pom_path = target_path / "pom.xml"
    pom_info = _parse_pom_info(pom_path) if pom_path.exists() else {}
    exists = target_path.exists()
    has_pom = pom_path.exists()

    return {
        "id": pom_info.get("artifact_id") or target_path.name,
        "name": pom_info.get("display_name") or "Base Spring Boot Project",
        "description": pom_info.get("description") or "Clean Spring Boot project used as stable source repository for AI-SDLC generation",
        "path": str(target_path),
        "exists": exists,
        "type": "spring-boot" if has_pom else "unknown",
        "java": pom_info.get("java_version") or settings.pipeline.java_version,
        "spring_boot": pom_info.get("spring_boot_version") or "unknown",
        "build_tool": "Maven" if has_pom else "Unknown",
        "jacoco": "Configured" if pom_info.get("jacoco_configured") else "Unavailable",
        "status": "ready" if exists and has_pom else "missing",
    }


def validate_target_project(settings: Settings) -> Dict[str, Any]:
    project = get_target_project(settings)
    project_path = Path(project["path"])
    pom_path = project_path / "pom.xml"

    logger.info("Starting target project validation — path=%s timeout=%ds", project_path, MAVEN_TIMEOUT_SECONDS)
    logger.info("pom.xml exists=%s  project_dir_exists=%s", pom_path.exists(), project_path.exists())

    if not project_path.exists():
        return {
            "project_id": project["id"],
            "path": project["path"],
            "compile": {"status": "FAIL", "errors": ["Target project directory does not exist."]},
            "tests": {"status": "SKIPPED", "errors": ["Tests skipped because target project directory is missing."]},
            "jacoco": {"status": "UNAVAILABLE"},
            "overall_status": "FAILED",
        }

    if not pom_path.exists():
        return {
            "project_id": project["id"],
            "path": project["path"],
            "compile": {"status": "FAIL", "errors": ["pom.xml not found in target project."]},
            "tests": {"status": "SKIPPED", "errors": ["Tests skipped because pom.xml is missing."]},
            "jacoco": {"status": "UNAVAILABLE"},
            "overall_status": "FAILED",
        }

    maven_cmd = _resolve_maven_command(settings)
    logger.info("Using Maven command: %s", maven_cmd)

    # Log Java/Maven versions for diagnostics
    _log_tool_version(["java", "-version"])
    _log_tool_version([maven_cmd, "--version"])

    logger.info("Running compile phase...")
    compile_result = _run_maven(project_path, maven_cmd, ["clean", "compile", "-DskipTests"])
    logger.info("Compile phase finished — status=%s duration=%.1fs", compile_result["status"], compile_result.get("duration_seconds", 0))

    jacoco = _jacoco_status(project_path)
    overall_status = "VALIDATED" if compile_result["status"] == "PASS" else "FAILED"
    logger.info("Validation complete — overall=%s", overall_status)
    return {
        "project_id": project["id"],
        "path": project["path"],
        "compile": compile_result,
        "tests": {"status": "SKIPPED", "errors": []},
        "jacoco": jacoco,
        "overall_status": overall_status,
    }


def _resolve_maven_command(settings: Settings) -> str:
    maven_root = settings.pipeline.get_project_root() / ".tools" / "maven"
    pattern = "mvn.cmd" if shutil.which("cmd") else "mvn"
    embedded = sorted(maven_root.glob(f"apache-maven-*/bin/{pattern}"))
    if embedded:
        return str(embedded[-1])

    if shutil.which("mvn.cmd"):
        return "mvn.cmd"
    if shutil.which("mvn"):
        return "mvn"

    return "mvn.cmd"


def _log_tool_version(cmd: List[str]) -> None:
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
        output = result.stdout.decode("utf-8", errors="replace").strip().splitlines()
        logger.info("%s: %s", cmd[0], output[0] if output else "(no output)")
    except Exception as exc:
        logger.warning("Could not get version for %s: %s", cmd[0], exc)


def _run_maven(project_path: Path, maven_cmd: str, goals: List[str]) -> Dict[str, Any]:
    started_at = time.perf_counter()
    command = [maven_cmd, *goals, "--no-transfer-progress"]

    try:
        completed = subprocess.run(
            command,
            cwd=str(project_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=MAVEN_TIMEOUT_SECONDS,
        )
        duration = round(time.perf_counter() - started_at, 1)
        output = (completed.stdout + completed.stderr).decode("utf-8", errors="replace")
        success = completed.returncode == 0
        result = {
            "status": "PASS" if success else "FAIL",
            "duration_seconds": duration,
        }
        if not success:
            result["errors"] = _extract_maven_errors(output)
            result["stdout"] = _trim_output(output)
            result["return_code"] = completed.returncode
        return result
    except subprocess.TimeoutExpired as exc:
        duration = round(time.perf_counter() - started_at, 1)
        output = ((exc.stdout or b"") + (exc.stderr or b"")).decode("utf-8", errors="replace")
        return {
            "status": "FAIL",
            "duration_seconds": duration,
            "errors": [f"Maven command timed out after {MAVEN_TIMEOUT_SECONDS} seconds."],
            "stdout": _trim_output(output),
            "return_code": -1,
        }
    except FileNotFoundError:
        return {
            "status": "FAIL",
            "duration_seconds": round(time.perf_counter() - started_at, 1),
            "errors": [f"Maven executable not found: {maven_cmd}"],
            "return_code": -1,
        }


def _build_test_status(project_path: Path, tests_result: Dict[str, Any]) -> Dict[str, Any]:
    summary = _parse_surefire_summary(project_path / "target" / "surefire-reports")
    result = {
        "status": tests_result["status"],
        "total": summary["total"],
        "failures": summary["failures"],
        "errors": summary["errors"],
        "skipped": summary["skipped"],
        "duration_seconds": tests_result.get("duration_seconds", 0.0),
    }
    if tests_result["status"] != "PASS":
        result["errors"] = tests_result.get("errors", [])
        if tests_result.get("stdout"):
            result["stdout"] = tests_result["stdout"]
    return result


def _jacoco_status(project_path: Path) -> Dict[str, Any]:
    xml_path = project_path / "target" / "site" / "jacoco" / "jacoco.xml"
    exec_path = project_path / "target" / "jacoco.exec"
    available = xml_path.exists() or exec_path.exists()
    payload: Dict[str, Any] = {
        "status": "AVAILABLE" if available else "UNAVAILABLE",
    }
    if xml_path.exists():
        payload["xml_path"] = str(xml_path.relative_to(project_path))
    if exec_path.exists():
        payload["exec_path"] = str(exec_path.relative_to(project_path))
    return payload


def _parse_pom_info(pom_path: Path) -> Dict[str, Any]:
    try:
        root = ElementTree.fromstring(pom_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}

    artifact_id = _xml_text(root, "./m:artifactId")
    description = _xml_text(root, "./m:description")
    display_name = _xml_text(root, "./m:name")
    java_version = _xml_text(root, "./m:properties/m:java.version")
    spring_boot_version = _xml_text(root, "./m:parent/m:version")
    jacoco_configured = "jacoco-maven-plugin" in pom_path.read_text(encoding="utf-8", errors="replace")

    return {
        "artifact_id": artifact_id,
        "description": description,
        "display_name": _titleize_name(display_name or artifact_id),
        "java_version": java_version,
        "spring_boot_version": spring_boot_version,
        "jacoco_configured": jacoco_configured,
    }


def _parse_surefire_summary(surefire_dir: Path) -> Dict[str, int]:
    summary = {"total": 0, "failures": 0, "errors": 0, "skipped": 0}
    if not surefire_dir.exists():
        return summary

    for xml_file in surefire_dir.glob("TEST-*.xml"):
        try:
            root = ElementTree.parse(xml_file).getroot()
        except Exception:
            continue
        summary["total"] += int(root.attrib.get("tests", "0") or 0)
        summary["failures"] += int(root.attrib.get("failures", "0") or 0)
        summary["errors"] += int(root.attrib.get("errors", "0") or 0)
        summary["skipped"] += int(root.attrib.get("skipped", "0") or 0)
    return summary


def _extract_maven_errors(output: str) -> List[str]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    error_lines = [line for line in lines if "[ERROR]" in line or "BUILD FAILURE" in line or "COMPILATION ERROR" in line]
    if error_lines:
        return error_lines[:12]
    return lines[-12:]


def _trim_output(output: str, max_lines: int = 40) -> str:
    lines = [line for line in output.splitlines() if line.strip()]
    return "\n".join(lines[-max_lines:])


def _xml_text(root: ElementTree.Element, path: str) -> Optional[str]:
    node = root.find(path, POM_NS)
    if node is None or node.text is None:
        return None
    return node.text.strip()


def _titleize_name(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return value.replace("-", " ").title()
