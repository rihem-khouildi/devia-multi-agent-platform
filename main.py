"""
AI-SDLC Multi-Agent Pipeline - Entry Point
==========================================
Accepts a user story at runtime in two forms:

  1. Jira ticket ID  (e.g. SCRUM-7, PROJ-123)
     -> The story is fetched automatically from Jira.

  2. Raw text        (anything that is not a Jira ID)
     -> The story is built directly from the text.
     -> Can be passed inline or read from a file with --file.

Usage:
  # Jira ID
  python main.py SCRUM-7

  # Inline raw text
  python main.py "As a user, I want to reset my password so that I can regain access."

  # Raw text from file
  python main.py --file user_story.txt

  # Dry-run (no GitHub commit, no Jira update)
  python main.py SCRUM-7 --dry-run

  # Point analyzer at a specific local repo
  python main.py SCRUM-7 --repo-path /path/to/cloned/repo
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

from config.settings import Settings
from core.pipeline import SDLCPipeline
from utils.logger import get_logger

logger = get_logger(__name__)

_JIRA_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")


def _is_jira_id(value: str) -> bool:
    return bool(_JIRA_ID_PATTERN.match(value.strip()))


def _looks_like_git_repository(repo_path: str | None) -> bool:
    if not repo_path:
        return False
    repo = Path(repo_path).resolve()
    return (repo / ".git").exists()


async def _command_available(command: str, version_arg: str) -> bool:
    commands_to_try = (command,)
    if sys.platform == "win32" and not command.lower().endswith(".cmd"):
        commands_to_try = (command, f"{command}.cmd")

    for candidate in commands_to_try:
        try:
            proc = await asyncio.create_subprocess_exec(
                candidate,
                version_arg,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            if proc.returncode == 0:
                return True
        except FileNotFoundError:
            continue
        except Exception:
            continue

    return False


async def _validate_startup_prerequisites(
    settings: Settings,
    user_story_input: str,
    dry_run: bool,
    repo_path: str | None = None,
) -> list[str]:
    errors: list[str] = []

    if not await _command_available("java", "-version"):
        errors.append("missing executable: java (required for Java build/test execution)")
    if not await _command_available("mvn", "--version"):
        errors.append("missing executable: mvn (required for Maven build/test execution)")

    if not settings.hf.api_key:
        errors.append("missing credential: HF_TOKEN (required for configured agent/provider flow)")

    if _is_jira_id(user_story_input):
        if not settings.jira.url:
            errors.append("missing credential: JIRA_URL (required for Jira-driven input mode)")
        if not settings.jira.username:
            errors.append("missing credential: JIRA_USERNAME (required for Jira-driven input mode)")
        if not settings.jira.api_token:
            errors.append("missing credential: JIRA_API_TOKEN (required for Jira-driven input mode)")

    if not dry_run:
        if _looks_like_git_repository(repo_path):
            if not await _command_available("git", "--version"):
                errors.append("missing executable: git (required for local git commit mode)")
        else:
            if not settings.github.token:
                errors.append("missing credential: GITHUB_TOKEN (required when dry-run is disabled)")
            if not settings.github.owner:
                errors.append("missing credential: GITHUB_OWNER (required when dry-run is disabled)")
            if not settings.github.repo:
                errors.append("missing credential: GITHUB_REPO (required when dry-run is disabled)")

    return errors


async def main(
    user_story_input: str,
    dry_run: bool = False,
    repo_path: str = None,
    resume: bool = False,
    resume_from: str = None,
):
    logger.info("Starting SDLC pipeline")
    logger.info(f"   Input: {user_story_input[:80]}{'...' if len(user_story_input) > 80 else ''}")
    if resume:
        logger.info(f"   Resume mode: {'from ' + resume_from if resume_from else 'last checkpoint'}")

    settings = Settings()
    startup_errors = await _validate_startup_prerequisites(
        settings,
        user_story_input,
        dry_run,
        repo_path=repo_path,
    )
    if startup_errors:
        print("\nSTARTUP_PREREQUISITE_FAILURE", file=sys.stderr)
        for error in startup_errors:
            print(f"- {error}", file=sys.stderr)
        sys.exit(1)

    pipeline = SDLCPipeline(settings)

    try:
        result = await pipeline.run(
            user_story_input=user_story_input,
            dry_run=dry_run,
            repo_path=repo_path,
            resume=resume,
            resume_from=resume_from,
        )

        print("\n" + "=" * 65)
        print("PIPELINE COMPLETED")
        print("=" * 65)
        us = result["user_story"]
        compile_status = "OK" if result["compile_success"] else f"{result['compile_errors']} erreur(s)"
        review_status = "OK" if result["review_approved"] else "BLOCKED"
        gates_status = "PASSED" if result.get("all_gates_passed") else "BLOCKED"
        print(f"User Story  : [{us['id']}] {us['title']}")
        print(f"Output      : {result['output_path']}")
        print(f"Files       : {result['files_generated']}")
        print(f"Compilation : {compile_status}")
        if result.get("fix_iterations", 0) > 0:
            print(f"Fixer       : {result['fix_iterations']} iteration(s)")
        print(f"Coverage    : {result['test_coverage']}% ({result.get('coverage_source', 'unknown')})")
        print(f"Review      : {result['review_score']}/100 ({review_status})")
        print(f"Quality     : {'OK' if result.get('quality_scan_passed') else 'BLOCKED'}")
        print(f"All gates   : {gates_status}")
        if result.get("commit_sha"):
            print(f"Commit SHA  : {result['commit_sha']}")
        elif dry_run:
            print("Dry-run mode - commit skipped")
        print("=" * 65)

        return result

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AI-SDLC Multi-Agent Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "user_story",
        nargs="?",
        help="Jira ticket ID (e.g. SCRUM-7) or raw user story text.",
    )
    parser.add_argument(
        "--file",
        "-f",
        metavar="PATH",
        help="Read the user story from a text file instead of inline.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the pipeline without committing to GitHub or updating Jira.",
    )
    parser.add_argument(
        "--repo-path",
        metavar="PATH",
        help="Path to the local clone of the target repository (REQUIRED for the Analyzer agent).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from the last checkpoint instead of starting from scratch.",
    )
    parser.add_argument(
        "--resume-from",
        metavar="STEP",
        help=(
            "Resume from a specific step (implies --resume). "
            "Valid steps: resolve_user_story, load_docs, advisor, analyzer, planner, "
            "developer, compile, fixer, tester, run_tests, reviewer, write_files, quality_gate, commit"
        ),
    )

    args = parser.parse_args()

    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        us_input = file_path.read_text(encoding="utf-8").strip()
    elif args.user_story:
        us_input = args.user_story.strip()
    else:
        parser.print_help()
        print("\nError: provide a user story ID, raw text, or --file PATH", file=sys.stderr)
        sys.exit(1)

    if not us_input:
        print("User story input is empty.", file=sys.stderr)
        sys.exit(1)

    resume = args.resume or bool(args.resume_from)

    asyncio.run(
        main(
            user_story_input=us_input,
            dry_run=args.dry_run,
            repo_path=args.repo_path,
            resume=resume,
            resume_from=args.resume_from,
        )
    )
