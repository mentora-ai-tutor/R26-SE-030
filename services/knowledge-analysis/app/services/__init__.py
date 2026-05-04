"""
GitHub Behavioral Analysis Service Package.
Main entry point for importing analysis components.
"""

from app.services.github_analyzer import GitHubAnalyzer, BehaviorSummary
from app.services.ollama_client import OllamaClient
from app.services.prompt_builder import PromptBuilder
from app.services.integration_example import BehaviorAnalysisService
from app.services.github_fetcher import GitHubFetcher

__all__ = [
    "GitHubAnalyzer",
    "BehaviorSummary",
    "OllamaClient",
    "PromptBuilder",
    "BehaviorAnalysisService",
    "GitHubFetcher",
]
