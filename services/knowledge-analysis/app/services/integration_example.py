"""
Example integration of GitHub analysis with Ollama LLM.
Demonstrates complete workflow for analyzing student coding behavior.
"""

import asyncio
import json
import logging
from typing import Dict, Any, List

from app.core.github_analysis_config import OLLAMA_MODEL, OLLAMA_URL
from app.services.github_analyzer import GitHubAnalyzer
from app.services.ollama_client import OllamaClient
from app.services.prompt_builder import PromptBuilder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BehaviorAnalysisService:
    """
    Complete service for analyzing student GitHub behavior using Ollama.
    Orchestrates analyzer, prompt builder, and LLM client.
    """

    def __init__(
        self,
        ollama_url: str = OLLAMA_URL,
        model: str = OLLAMA_MODEL,
    ):
        """
        Initialize the behavior analysis service.

        Args:
            ollama_url: Ollama server URL
            model: Model to use
        """
        self.analyzer = GitHubAnalyzer()
        self.llm_client = OllamaClient(base_url=ollama_url, model=model)
        self.prompt_builder = PromptBuilder()
        self.logger = logger

    async def analyze_student_behavior(
        self, commits: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Complete analysis pipeline: extract metrics → build prompt → call LLM → parse response.

        Args:
            commits: List of commit dictionaries with repo, message, timestamp, 
                    additions, deletions

        Returns:
            Complete analysis result with metrics and AI assessment

        Example:
            commits = [
                {
                    "repo": "learning-project",
                    "message": "Fix authentication bug in login flow",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "additions": 45,
                    "deletions": 12
                },
                {...}
            ]
            result = await service.analyze_student_behavior(commits)
        """
        try:
            # Step 1: Analyze commits and extract behavioral metrics
            behavior_summary = self.analyzer.analyze_commits(commits)
            summary_dict = self.analyzer.to_dict(behavior_summary)
            self.logger.info(f"Computed behavior summary: {summary_dict}")

            # Step 2: Build prompt for LLM
            prompt = self.prompt_builder.build_prompt(summary_dict)
            self.logger.info("Generated analysis prompt")

            # Step 3: Call Ollama for analysis
            llm_response = await self.llm_client.generate(
                prompt=prompt,
                stream=False,
                temperature=0.3,  # Lower temperature for more consistent analysis
            )
            response_text = self.llm_client.extract_text(llm_response)
            self.logger.info("Received LLM response")

            # Step 4: Parse and validate response
            json_str = self.prompt_builder.extract_json_from_response(response_text)
            analysis_data = self.prompt_builder.parse_analysis_response(json_str)
            safe_response = self.prompt_builder.build_safe_response(analysis_data)

            self.logger.info("Successfully parsed analysis response")

            # Step 5: Combine results
            result = {
                "status": "success",
                "metrics": summary_dict,
                "ai_analysis": safe_response,
                "raw_response": response_text,
            }

            return result

        except ValueError as e:
            self.logger.error(f"Validation error: {e}")
            return {
                "status": "error",
                "error": f"Validation error: {str(e)}",
                "type": "validation_error",
            }
        except Exception as e:
            self.logger.error(f"Analysis failed: {e}", exc_info=True)
            return {
                "status": "error",
                "error": f"Analysis failed: {str(e)}",
                "type": "analysis_error",
            }

    def analyze_student_behavior_sync(
        self, commits: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Synchronous version of analyze_student_behavior.
        Use when async context is unavailable.
        """
        try:
            # Step 1: Analyze commits
            behavior_summary = self.analyzer.analyze_commits(commits)
            summary_dict = self.analyzer.to_dict(behavior_summary)
            self.logger.info(f"Computed behavior summary: {summary_dict}")

            # Step 2: Build prompt
            prompt = self.prompt_builder.build_prompt(summary_dict)
            self.logger.info("Generated analysis prompt")

            # Step 3: Call Ollama (sync)
            llm_response = self.llm_client.generate_sync(
                prompt=prompt,
                stream=False,
                temperature=0.3,
            )
            response_text = self.llm_client.extract_text(llm_response)
            self.logger.info("Received LLM response")

            # Step 4: Parse response
            json_str = self.prompt_builder.extract_json_from_response(response_text)
            analysis_data = self.prompt_builder.parse_analysis_response(json_str)
            safe_response = self.prompt_builder.build_safe_response(analysis_data)

            self.logger.info("Successfully parsed analysis response")

            # Step 5: Combine results
            result = {
                "status": "success",
                "metrics": summary_dict,
                "ai_analysis": safe_response,
                "raw_response": response_text,
            }

            return result

        except ValueError as e:
            self.logger.error(f"Validation error: {e}")
            return {
                "status": "error",
                "error": f"Validation error: {str(e)}",
                "type": "validation_error",
            }
        except Exception as e:
            self.logger.error(f"Analysis failed: {e}", exc_info=True)
            return {
                "status": "error",
                "error": f"Analysis failed: {str(e)}",
                "type": "analysis_error",
            }

    async def check_ollama_available(self) -> bool:
        """Check if Ollama server is available."""
        return await self.llm_client.check_health()


# ============================================================================
# EXAMPLE USAGE
# ============================================================================


async def main():
    """Example: Analyze a student's GitHub behavior."""

    # Sample commit data
    sample_commits = [
        {
            "repo": "my-first-project",
            "message": "Add user authentication module",
            "timestamp": "2024-01-10T09:30:00Z",
            "additions": 150,
            "deletions": 5,
        },
        {
            "repo": "my-first-project",
            "message": "Fix login endpoint validation",
            "timestamp": "2024-01-11T14:20:00Z",
            "additions": 35,
            "deletions": 12,
        },
        {
            "repo": "my-first-project",
            "message": "Refactor database connection logic for better performance",
            "timestamp": "2024-01-15T10:45:00Z",
            "additions": 78,
            "deletions": 45,
        },
        {
            "repo": "api-project",
            "message": "Initialize FastAPI project",
            "timestamp": "2024-02-01T08:00:00Z",
            "additions": 250,
            "deletions": 0,
        },
        {
            "repo": "api-project",
            "message": "Add request validation and error handling",
            "timestamp": "2024-02-05T16:30:00Z",
            "additions": 180,
            "deletions": 25,
        },
    ]

    # Create service
    service = BehaviorAnalysisService(
        ollama_url="http://localhost:11434",
        model="llama3",
    )

    # Check if Ollama is available
    available = await service.check_ollama_available()
    if not available:
        print("⚠️  Ollama server not available at http://localhost:11434")
        print("   Make sure Ollama is running: ollama serve")
        return

    print("✓ Ollama server available")
    print("\nAnalyzing student behavior...")
    print("-" * 60)

    # Run analysis
    result = await service.analyze_student_behavior(sample_commits)

    # Display results
    if result["status"] == "success":
        metrics = result["metrics"]
        analysis = result["ai_analysis"]

        print("\n📊 BEHAVIOR METRICS:")
        print(f"  Commits: {metrics['commit_count']}")
        print(f"  Avg time between commits: {metrics['avg_time_gap_seconds']} seconds")
        print(f"  Message quality: {metrics['message_quality']}/1.0")
        print(f"  Big bang pattern: {metrics['big_bang_detected']}")
        print(f"  Total code: +{metrics['total_additions']} -{metrics['total_deletions']} lines")

        print("\n🤖 AI ANALYSIS:")
        print(f"  AI Dependency: {analysis['ai_dependency']}")
        print(f"  Reasoning: {analysis['reasoning']}")
        print(f"\n  Weaknesses:")
        for weakness in analysis["weaknesses"]:
            print(f"    - {weakness}")
        print(f"\n  Recommendations:")
        for rec in analysis["recommendations"]:
            print(f"    - {rec}")
    else:
        print(f"❌ Analysis failed: {result.get('error')}")


if __name__ == "__main__":
    asyncio.run(main())
