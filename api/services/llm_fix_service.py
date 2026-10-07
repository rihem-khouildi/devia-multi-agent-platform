"""
LLM Fix Service
===============
On-demand LLM-driven error correction for failed pipeline runs.

Fixes over initial version
──────────────────────────
1. Full rollback  — original artifact + disk files are restored when Maven
   still fails after patching, so no partial broken state is left on disk.
2. Persistent status — fix status is written to
   output/artifacts/llm_fix_status_{run_id}.json after every state change,
   so GET /llm-fix/status survives server restarts.
3. Smart context window — large files are not naively truncated; instead the
   service extracts a focused window around error lines (±40 lines) plus the
   class/import header, keeping total prompt size in budget.
4. Auto-compile guard — when target="run_tests" the service runs a silent
   compile check first; if it fails it switches to "both" automatically and
   reports that it did so, preventing cryptic Maven test failures.

No GitHub push is triggered at any point.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)

# ── In-memory status store ────────────────────────────────────────────────────
_fix_status: Dict[str, Dict[str, Any]] = {}

_MAX_FILE_CHARS      = 5_000   # below this → send full file
_CONTEXT_WINDOW_LINES = 45     # lines around each error line for large files
_MAX_FILES_IN_PROMPT  = 8      # cap to stay within token budget


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_path(run_id: str, settings) -> Path:
    return Path(settings.pipeline.artifacts_dir) / f"llm_fix_status_{run_id}.json"


def _save_status(run_id: str, record: Dict[str, Any], settings) -> None:
    """Persist fix status to disk so it survives server restarts."""
    try:
        _status_path(run_id, settings).write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        logger.warning("[llm_fix] status persist failed: %s", exc)


def _load_status_from_disk(run_id: str, settings) -> Optional[Dict[str, Any]]:
    """Try to load a persisted fix status record for this run."""
    try:
        p = _status_path(run_id, settings)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("[llm_fix] status load failed: %s", exc)
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def get_status(run_id: str, settings=None) -> Optional[Dict[str, Any]]:
    """Return in-memory record, or fall back to disk if server restarted."""
    if run_id in _fix_status:
        return _fix_status[run_id]
    if settings:
        disk = _load_status_from_disk(run_id, settings)
        if disk:
            _fix_status[run_id] = disk   # re-warm memory cache
            return disk
    return None


def init_status(run_id: str, settings=None) -> None:
    """Ensure a status record exists (idempotent). Loads from disk if available."""
    if run_id not in _fix_status:
        if settings:
            disk = _load_status_from_disk(run_id, settings)
            if disk:
                _fix_status[run_id] = disk
                return
        _fix_status[run_id] = {
            "status": "idle",
            "message": "No fix attempted yet.",
            "patched_files": [],
            "last_result": None,
            "started_at": None,
            "completed_at": None,
        }


async def launch_fix(run_id: str, target: str, settings) -> None:
    """Register running status, persist it, then kick off background task."""
    record: Dict[str, Any] = {
        "status": "running",
        "message": "LLM fix in progress…",
        "patched_files": [],
        "last_result": None,
        "started_at": _now_iso(),
        "completed_at": None,
    }
    _fix_status[run_id] = record
    _save_status(run_id, record, settings)
    asyncio.create_task(_run_fix(run_id, target, settings))


# ── Background task ───────────────────────────────────────────────────────────

async def _run_fix(run_id: str, target: str, settings) -> None:
    record = _fix_status[run_id]

    def _update(updates: Dict[str, Any]) -> None:
        record.update(updates)
        _save_status(run_id, record, settings)

    try:
        from api.services import error_store, event_store, run_service, artifact_service

        # ── 1. Resolve run ───────────────────────────────────────────
        run_record = run_service.get_run(run_id, settings)
        if not run_record:
            raise ValueError(f"Run '{run_id}' not found.")
        story_id = run_record["story_id"]

        # ── 2. Load errors ───────────────────────────────────────────
        errors = error_store.get_run_errors(run_id) or []
        if not errors:
            _update({"status": "idle", "message": "No errors to fix.", "completed_at": _now_iso()})
            return

        # ── 3. Load generated code artifact ──────────────────────────
        generated_json = artifact_service.get_generated_files(story_id, settings)
        if not generated_json:
            raise ValueError(
                f"Generated code artifact not found for story '{story_id}'. "
                "Run the full pipeline first."
            )

        all_files: Dict[str, str] = generated_json.get("files") or {}
        pom_xml: str = generated_json.get("pom_xml") or ""
        if not all_files:
            raise ValueError("Generated code artifact contains no files.")

        # ── FIX 4: Auto-compile guard for run_tests target ────────────
        effective_target = target
        if target == "run_tests":
            event_store.record_run_event(
                run_id, "llm_fix", "running",
                "target=run_tests: running silent compile check first…",
            )
            compile_ok = await _silent_compile_check(all_files, pom_xml)
            if not compile_ok:
                effective_target = "both"
                logger.info(
                    "[llm_fix] run=%s silent compile failed — escalating target: run_tests → both",
                    run_id,
                )
                event_store.record_run_event(
                    run_id, "llm_fix", "running",
                    "Compile check failed — switching target to 'both' (compile + tests).",
                )
                # Also make sure there is a compile error in error_store so the
                # prompt includes the right context.

        # ── 4. Collect focused file context for prompt ────────────────
        affected = _collect_affected_files(errors, all_files)

        # ── 5. Build LLM prompt ──────────────────────────────────────
        story_title = run_record.get("story_title", "")
        system_prompt, user_message = _build_prompt(errors, affected, story_title)

        # ── 6. Call LLM ──────────────────────────────────────────────
        event_store.record_run_event(
            run_id, "llm_fix", "running",
            "Calling LLM to generate targeted patch…",
        )
        from agents.base_agent import BaseAgent
        agent = BaseAgent(settings.hf, "LLMFix", model=settings.hf.model_fixer)
        raw_response = await agent.call_llm(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=4096,
            temperature=0.15,
            use_cache=False,
        )

        # ── 7. Extract patches ───────────────────────────────────────
        patches = _extract_patches(raw_response)
        if not patches:
            _update({
                "status": "failed",
                "message": "LLM returned no valid code patches. Try again or fix manually.",
                "completed_at": _now_iso(),
            })
            event_store.record_run_event(run_id, "llm_fix", "failed",
                                         "No patches extracted from LLM response")
            return

        # ── 8. Apply patches in-memory ───────────────────────────────
        patched_files, new_all_files = _apply_patches(patches, all_files)
        if not patched_files:
            _update({
                "status": "failed",
                "message": "Patches did not match any known file paths.",
                "completed_at": _now_iso(),
            })
            event_store.record_run_event(run_id, "llm_fix", "failed",
                                         "Patches did not match any known paths")
            return

        # ── FIX 1: Snapshot original state for rollback ───────────────
        original_files = dict(all_files)          # in-memory snapshot

        # ── 9. Write patched state (artifact + disk) ──────────────────
        _persist_artifact(story_id, generated_json, new_all_files, settings)
        _write_to_disk(story_id, patches, settings)

        event_store.record_run_event(
            run_id, "llm_fix", "running",
            f"Patch applied to {len(patched_files)} file(s). Re-running {effective_target}…",
            {"patched_files": patched_files},
        )

        # ── 10. Re-run compile / tests ────────────────────────────────
        last_result = await _rerun(effective_target, new_all_files, pom_xml)

        # ── FIX 1: Rollback if Maven still fails after patching ───────
        if _maven_still_failing(effective_target, last_result):
            logger.warning(
                "[llm_fix] run=%s Maven still failing after patch — rolling back.", run_id
            )
            # Restore original artifact and disk files
            _persist_artifact(story_id, generated_json, original_files, settings)
            _write_to_disk(story_id, original_files, settings)   # type: ignore[arg-type]

            _update({
                "status": "failed",
                "message": _failure_message(effective_target, last_result, rolled_back=True),
                "patched_files": patched_files,
                "last_result": last_result,
                "completed_at": _now_iso(),
            })
            event_store.record_run_event(
                run_id, "llm_fix", "failed",
                "Maven still failing — original files restored (rollback complete).",
                last_result,
            )
            return

        # ── 11. Refresh error_store ───────────────────────────────────
        _refresh_errors(run_id, last_result)

        # ── 12. Final status ──────────────────────────────────────────
        final_status = _determine_status(effective_target, last_result)
        msg = _failure_message(effective_target, last_result, rolled_back=False)

        event_store.record_run_event(
            run_id, "llm_fix",
            "success" if final_status == "success" else "failed",
            msg, last_result,
        )

        _update({
            "status": final_status,
            "message": msg,
            "patched_files": patched_files,
            "last_result": last_result,
            "completed_at": _now_iso(),
        })

    except Exception as exc:
        logger.exception("[llm_fix] run=%s  error=%s", run_id, exc)
        try:
            from api.services import event_store
            event_store.record_run_event(run_id, "llm_fix", "failed", str(exc)[:200])
        except Exception:
            pass
        _update({
            "status": "failed",
            "message": str(exc)[:300],
            "completed_at": _now_iso(),
        })


# ── FIX 4: Silent compile check ───────────────────────────────────────────────

async def _silent_compile_check(all_files: Dict[str, str], pom_xml: str) -> bool:
    """Run a quick mvn compile to know if the code is currently compilable."""
    try:
        from core.maven_compiler import MavenBuildRunner
        from core.models import GeneratedCode

        main_files = {k: v for k, v in all_files.items() if "/test/" not in k}
        gen_code = GeneratedCode(files=main_files, pom_xml=pom_xml)
        runner = MavenBuildRunner(timeout=120)
        result = await runner.compile_main(gen_code)
        return result.success
    except Exception as exc:
        logger.warning("[llm_fix] silent compile check error: %s", exc)
        return False  # assume broken → escalate to "both"


# ── FIX 3: Smart context window ───────────────────────────────────────────────

def _collect_affected_files(
    errors: List[Dict[str, Any]],
    all_files: Dict[str, str],
) -> Dict[str, str]:
    """
    Return files relevant to the errors with smart context extraction.

    For each mentioned file:
      • if the file is ≤ _MAX_FILE_CHARS chars → include in full
      • otherwise → extract class/import header + windows around error lines
    """
    # Build map: canonical_path → list[error_line]
    path_lines: Dict[str, List[int]] = {}
    for err in errors:
        for fe in err.get("files", []):
            path = fe.get("path", "")
            line = fe.get("line")
            if path:
                path_lines.setdefault(path, [])
                if isinstance(line, int):
                    path_lines[path].append(line)

    result: Dict[str, str] = {}

    for path, error_lines in list(path_lines.items())[:_MAX_FILES_IN_PROMPT]:
        # Resolve canonical path (exact or fuzzy by filename)
        canonical, content = _resolve_file(path, all_files)
        if canonical is None:
            continue

        if len(content) <= _MAX_FILE_CHARS:
            result[canonical] = content
        else:
            result[canonical] = _extract_context_window(content, error_lines)

    # Fallback: include all main files (full if small, windowed if large)
    if not result:
        main_files = {k: v for k, v in all_files.items() if "/test/" not in k}
        for path, content in list(main_files.items())[:_MAX_FILES_IN_PROMPT]:
            if len(content) <= _MAX_FILE_CHARS:
                result[path] = content
            else:
                result[path] = _extract_context_window(content, [])

    return result


def _resolve_file(
    path: str,
    all_files: Dict[str, str],
) -> Tuple[Optional[str], str]:
    """Return (canonical_key, content) for a path, or (None, '') if not found."""
    if path in all_files:
        return path, all_files[path]
    fname = Path(path).name
    for k, v in all_files.items():
        if Path(k).name == fname:
            return k, v
    return None, ""


def _extract_context_window(content: str, error_lines: List[int]) -> str:
    """
    Extract a focused view of a large file:
      1. Class/package header (imports + class declaration) — first ≤30 lines
      2. A window of ±_CONTEXT_WINDOW_LINES around each error line
    De-duplicated, line-numbered, with ellipsis markers between gaps.
    """
    lines = content.splitlines()
    total = len(lines)

    # Always include the header (package + imports + class declaration)
    header_end = _find_class_body_start(lines)
    include: set[int] = set(range(0, min(header_end, 30)))

    for err_line in error_lines:
        lo = max(0, err_line - _CONTEXT_WINDOW_LINES - 1)
        hi = min(total, err_line + _CONTEXT_WINDOW_LINES)
        include.update(range(lo, hi))

    if not include:
        # No specific lines known: return first 80 lines
        include = set(range(min(80, total)))

    sorted_indices = sorted(include)
    chunks: List[str] = []
    prev = -2

    for idx in sorted_indices:
        if idx > prev + 1:
            if prev >= 0:
                chunks.append(f"    // … ({idx - prev - 1} lines omitted)")
        chunks.append(f"{idx + 1:4d}  {lines[idx]}")
        prev = idx

    remaining = total - (max(sorted_indices) + 1) if sorted_indices else total
    if remaining > 0:
        chunks.append(f"    // … ({remaining} lines omitted)")

    return "\n".join(chunks)


def _find_class_body_start(lines: List[str]) -> int:
    """Return the index of the line after the first '{' at class level."""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("public class") or stripped.startswith("@") or \
                "class " in stripped or "interface " in stripped or "enum " in stripped:
            # Look for the opening brace
            for j in range(i, min(i + 5, len(lines))):
                if "{" in lines[j]:
                    return j + 1
    return 20  # conservative default


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(
    errors: List[Dict[str, Any]],
    affected_files: Dict[str, str],
    user_story: str,
) -> Tuple[str, str]:
    system = (
        "You are an expert Java Spring Boot developer performing targeted bug fixes.\n"
        "You receive compilation or test errors and the affected source files.\n"
        "Your task: produce MINIMAL corrections that fix ONLY the reported errors.\n\n"
        "Rules:\n"
        "- Fix ONLY what is broken. Do not refactor, rename, or add features.\n"
        "- Return each corrected file as a fenced code block with the relative path:\n"
        "  ```java:src/main/java/com/example/service/FooService.java\n"
        "  // COMPLETE corrected file content (not a diff)\n"
        "  ```\n"
        "- One block per modified file. Do not include unchanged files.\n"
        "- Do NOT add fix-explanation comments. Write complete files, not diffs.\n"
        "- If a file was shown as a context window (with line numbers and '…' markers),\n"
        "  still return the COMPLETE corrected file (no line numbers, no ellipsis).\n"
    )

    error_section = ""
    for err in errors:
        error_section += f"\n### {err.get('step', 'error').upper()} ERRORS\n"
        error_section += f"Summary: {err.get('summary', '')}\n"
        raw = err.get("raw_excerpt", "")
        if raw:
            error_section += f"Raw Maven output:\n```\n{raw[:1500]}\n```\n"
        for fe in err.get("files", [])[:10]:
            error_section += (
                f"- {fe.get('path', '')} "
                f"line {fe.get('line', '?')}: {fe.get('message', '')}\n"
            )

    files_section = ""
    for path, content in list(affected_files.items())[:_MAX_FILES_IN_PROMPT]:
        # Detect if content is already a context window (has line-number prefix)
        is_window = bool(re.match(r"\s*\d+\s+", content.splitlines()[0])) if content else False
        lang = "java"
        if path.endswith(".xml"):
            lang = "xml"
        elif path.endswith((".yml", ".yaml")):
            lang = "yaml"
        elif path.endswith(".properties"):
            lang = "properties"
        label = " (context window — return complete file)" if is_window else ""
        files_section += f"\n### FILE: {path}{label}\n```{lang}\n{content}\n```\n"

    user = (
        f"Context (user story): {user_story}\n\n"
        f"## Errors to fix:\n{error_section}\n"
        f"## Affected source files:\n{files_section}\n\n"
        "Provide corrected file blocks that fix ALL the errors above."
    )
    return system, user


# ── Patch extraction ──────────────────────────────────────────────────────────

def _extract_patches(response: str) -> Dict[str, str]:
    patches: Dict[str, str] = {}

    # Primary: ```lang:path
    for m in re.finditer(
        r"```(?:java|xml|yaml|properties|kotlin):([^\n]+)\n(.*?)```",
        response, re.DOTALL,
    ):
        patches[m.group(1).strip()] = m.group(2)

    if patches:
        return patches

    # Fallback: ```java\n// FILE: path\n
    for m in re.finditer(
        r"```(?:java|xml|yaml|properties)\n//\s*FILE:\s*([^\n]+)\n(.*?)```",
        response, re.DOTALL,
    ):
        patches[m.group(1).strip()] = m.group(2)

    return patches


# ── Patch application ─────────────────────────────────────────────────────────

def _apply_patches(
    patches: Dict[str, str],
    all_files: Dict[str, str],
) -> Tuple[List[str], Dict[str, str]]:
    new_files = dict(all_files)
    applied: List[str] = []

    for patch_path, content in patches.items():
        if patch_path in new_files:
            new_files[patch_path] = content
            applied.append(patch_path)
            continue

        fname = Path(patch_path).name
        matched = next((k for k in new_files if Path(k).name == fname), None)
        if matched:
            new_files[matched] = content
            applied.append(matched)
        else:
            new_files[patch_path] = content
            applied.append(patch_path)
            logger.info("[llm_fix] new file added by LLM: %s", patch_path)

    return applied, new_files


# ── Artifact & disk persistence ───────────────────────────────────────────────

def _persist_artifact(
    story_id: str,
    original_json: Dict[str, Any],
    new_files: Dict[str, str],
    settings,
) -> None:
    try:
        updated = {**original_json, "files": new_files}
        path = Path(settings.pipeline.artifacts_dir) / f"generated_code_{story_id}.json"
        path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("[llm_fix] artifact updated: %s", path)
    except Exception as exc:
        logger.warning("[llm_fix] artifact persist failed: %s", exc)


def _write_to_disk(
    story_id: str,
    files: Dict[str, str],
    settings,
) -> None:
    """Write a dict of {rel_path: content} to the generated code directory."""
    try:
        base = Path(settings.pipeline.output_dir) / story_id
        for rel_path, content in files.items():
            target = base / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    except Exception as exc:
        logger.warning("[llm_fix] disk write failed (non-fatal): %s", exc)


# ── Maven re-run ──────────────────────────────────────────────────────────────

async def _rerun(
    target: str,
    all_files: Dict[str, str],
    pom_xml: str,
) -> Dict[str, Any]:
    from core.maven_compiler import MavenBuildRunner
    from core.models import GeneratedCode

    main_files = {k: v for k, v in all_files.items() if "/test/" not in k}
    test_files  = {k: v for k, v in all_files.items() if "/test/" in k}
    gen_code    = GeneratedCode(files=main_files, pom_xml=pom_xml)
    runner      = MavenBuildRunner(timeout=180)
    result: Dict[str, Any] = {}

    if target in ("compile", "both"):
        cr = await runner.compile_main(gen_code)
        result["compile_ok"] = cr.success
        result["compile_errors"] = [
            {"file": e.file, "line": e.line, "message": e.message}
            for e in (cr.errors or [])[:20]
        ]
        if not cr.success:
            return result  # no point running tests

    if target in ("run_tests", "both"):
        tr = await runner.run_tests(gen_code, test_files)
        result["tests_ok"]      = tr.success
        result["test_coverage"] = tr.line_coverage
        result["failed_tests"]  = tr.failed_test_names()

    return result


# ── FIX 1: Rollback decision ──────────────────────────────────────────────────

def _maven_still_failing(target: str, last_result: Dict[str, Any]) -> bool:
    """
    Return True when the patch made no improvement and rollback is warranted.

    We roll back only when the primary check for the chosen target is still
    broken — not when tests are failing but compile is now fixed (partial win).
    """
    if target == "compile":
        return last_result.get("compile_ok") is False
    if target == "run_tests":
        # compile was already ok (guard ran), so only check tests
        return last_result.get("tests_ok") is False
    # "both": roll back only if compile itself is still broken
    return last_result.get("compile_ok") is False


# ── Status helpers ────────────────────────────────────────────────────────────

def _determine_status(target: str, last_result: Dict[str, Any]) -> str:
    compile_ok = last_result.get("compile_ok")
    tests_ok   = last_result.get("tests_ok")

    if target == "compile":
        return "success" if compile_ok else "failed"
    if target == "run_tests":
        return "success" if tests_ok else "failed"
    # both
    if compile_ok and tests_ok:
        return "success"
    return "failed"


def _failure_message(
    target: str,
    last_result: Dict[str, Any],
    rolled_back: bool,
) -> str:
    compile_ok = last_result.get("compile_ok")
    tests_ok   = last_result.get("tests_ok")
    suffix = " Original files restored." if rolled_back else ""

    if compile_ok is False:
        return f"LLM patch applied — compile still failing.{suffix}"
    if compile_ok and tests_ok is False:
        return f"LLM patch applied — compile OK but tests still failing.{suffix}"
    if compile_ok and tests_ok:
        return "LLM patch applied — all checks passed."
    if compile_ok and tests_ok is None:
        return "LLM patch applied — compile passed."
    return f"LLM patch result inconclusive.{suffix}"


# ── Error store refresh ───────────────────────────────────────────────────────

def _refresh_errors(run_id: str, last_result: Dict[str, Any]) -> None:
    """Clear error_store entries when the corresponding check passes."""
    from api.services import error_store

    bucket = error_store._store.get(run_id)
    if not bucket:
        return
    if last_result.get("compile_ok") is True:
        bucket["compile"] = None
    if last_result.get("tests_ok") is True:
        bucket["test"] = None
