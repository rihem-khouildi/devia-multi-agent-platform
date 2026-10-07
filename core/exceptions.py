"""
Exceptions personnalisées pour le pipeline SDLC.
"""


class SDLCPipelineError(Exception):
    """Exception de base pour le pipeline SDLC."""
    pass


class CompilationError(SDLCPipelineError):
    """Échec de compilation après toutes les tentatives."""

    def __init__(self, message: str, error_count: int = 0, errors: list = None):
        super().__init__(message)
        self.error_count = error_count
        self.errors = errors or []


class ReviewParseError(SDLCPipelineError):
    """Le reviewer n'a pas retourné un JSON valide."""
    pass


class TestGenerationError(SDLCPipelineError):
    """Échec de génération des tests."""
    pass


class BlueprintParseError(SDLCPipelineError):
    """Erreur lors du parsing du blueprint JSON."""
    pass


class LLMResponseError(SDLCPipelineError):
    """Le LLM n'a pas retourné une réponse valide."""
    pass
