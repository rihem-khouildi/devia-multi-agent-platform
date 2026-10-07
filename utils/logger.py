"""Utilitaire de logging centralise."""

import logging
import sys
from pathlib import Path
from typing import Optional


class SafeStreamHandler(logging.StreamHandler):
    """Console handler resilient to Windows code pages that reject Unicode."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except UnicodeEncodeError:
            try:
                message = self.format(record)
                encoding = getattr(self.stream, "encoding", None) or "utf-8"
                safe_message = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
                self.stream.write(safe_message + self.terminator)
                self.flush()
            except Exception:
                self.handleError(record)


def get_logger(name: str, log_dir: Optional[Path] = None) -> logging.Logger:
    """
    Configure et retourne un logger.

    Args:
        name: Nom du logger
        log_dir: Repertoire pour les fichiers de log. Si None, utilise un repertoire par defaut.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(logging.DEBUG)

        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

        # Handler console
        handler = SafeStreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # Handler fichier
        if log_dir is None:
            project_root = Path(__file__).parent.parent.resolve()
            log_dir = project_root / "output" / "logs"

        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
