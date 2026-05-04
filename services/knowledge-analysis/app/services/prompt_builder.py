"""
LLM prompt builder for behavioral analysis.
Constructs analysis prompts for educational code review.
"""

from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class PromptBuilder:
    """
    Builds structured prompts for LLM-based behavioral analysis.
    Acts as a senior programming instructor reviewing student code patterns.
    """

    SYSTEM_CONTEXT = """You are a senior programming instructor with 15+ years of experience in software engineering and computer science education. 

Your role is to analyze a student's GitHub commit history and provide constructive feedback:
1. Identify learning weaknesses and knowledge gaps
2. Detect AI-assisted coding patterns and over-reliance on automation
3. Provide actionable improvement recommendations
4. Assess coding maturity and best practices adoption

Return ONLY valid JSON with no additional text or markdown."""

    def __init__(self):
        """Initialize the prompt builder."""
        self.logger = logger

    def build_prompt(self, summary: Dict[str, Any]) -> str:
        """
        Build analysis prompt from behavior summary.

        Args:
            summary: Dictionary containing behavioral metrics from github_analyzer

        Returns:
            Formatted prompt string for LLM
        """
        prompt = self._construct_prompt(summary)
        return prompt

    def _construct_prompt(self, summary: Dict[str, Any]) -> str:
        """Construct the full analysis prompt."""
        metrics_section = self._format_metrics(summary)
        analysis_tasks = self._format_analysis_tasks(summary)

        prompt = f"""{self.SYSTEM_CONTEXT}

STUDENT CODING BEHAVIOR METRICS:
{metrics_section}

YOUR ANALYSIS TASK:
{analysis_tasks}

REQUIRED JSON OUTPUT FORMAT:
{{
  "weaknesses": ["weakness1", "weakness2", ...],
  "ai_dependency": "Low | Medium | High",
  "reasoning": "explanation of your assessment",
  "recommendations": ["recommendation1", "recommendation2", ...]
}}

ANALYSIS:"""

        return prompt

    def _format_metrics(self, summary: Dict[str, Any]) -> str:
        """Format behavior metrics for the prompt."""
        return f"""- Total commits: {summary.get('commit_count', 0)}
- Average time between commits: {self._format_time_gap(summary.get('avg_time_gap_seconds', 0))}
- Message quality score: {summary.get('message_quality', 0)}/1.0
- Big bang pattern detected: {summary.get('big_bang_detected', False)}
- Total additions: {summary.get('total_additions', 0)} lines
- Total deletions: {summary.get('total_deletions', 0)} lines
- Average commit size: {summary.get('avg_commit_size', 0):.0f} lines/commit
- Repositories involved: {summary.get('repos_count', 0)}"""

    def _format_time_gap(self, seconds: float) -> str:
        """Format time gap in human-readable format."""
        if seconds == 0:
            return "< 1 second"

        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")

        return " ".join(parts) if parts else "< 1m"

    def _format_analysis_tasks(self, summary: Dict[str, Any]) -> str:
        """Format specific analysis tasks based on metrics."""
        tasks = [
            "1. Assess code maturity based on commit frequency and message quality",
            "2. Identify skill gaps (testing, documentation, refactoring, etc.)",
        ]

        # Add specific analysis based on metrics
        if summary.get("big_bang_detected", False):
            tasks.append(
                "3. Flag potential AI usage: big bang pattern suggests rushed/automated commits"
            )
        else:
            tasks.append(
                "3. Evaluate consistency and incremental development approach"
            )

        if summary.get("message_quality", 0) < 0.5:
            tasks.append(
                "4. Address poor commit message quality (impacts collaboration skills)"
            )
        else:
            tasks.append(
                "4. Comment on communication quality through commit messages"
            )

        tasks.append("5. Provide 2-3 specific recommendations for growth areas")

        return "\n".join(tasks)

    @staticmethod
    def validate_analysis_response(response_text: str) -> bool:
        """
        Validate that response contains required JSON fields.

        Args:
            response_text: Raw response from LLM

        Returns:
            True if response appears to have required fields
        """
        required_fields = ["weaknesses", "ai_dependency", "reasoning", "recommendations"]
        return all(field in response_text for field in required_fields)

    @staticmethod
    def extract_json_from_response(response_text: str) -> str:
        """
        Extract JSON from response, removing markdown if present.

        Args:
            response_text: Raw LLM response that may contain markdown

        Returns:
            Cleaned JSON string

        Raises:
            ValueError: If no JSON found in response
        """
        import json as json_module

        text = response_text.strip()

        # Remove markdown code blocks if present
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]

        if text.endswith("```"):
            text = text[:-3]

        text = text.strip()

        # Find JSON object boundaries
        start_idx = text.find("{")
        end_idx = text.rfind("}") + 1

        if start_idx == -1 or end_idx == 0:
            raise ValueError("No JSON object found in response")

        json_str = text[start_idx:end_idx]

        # Validate it's proper JSON
        try:
            json_module.loads(json_str)
        except json_module.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in response: {e}") from e

        return json_str

    @staticmethod
    def parse_analysis_response(response_json: str) -> Dict[str, Any]:
        """
        Parse and validate LLM analysis response.

        Args:
            response_json: JSON string from LLM

        Returns:
            Parsed response dictionary with validated fields

        Raises:
            ValueError: If JSON is invalid or missing required fields
            json.JSONDecodeError: If JSON cannot be parsed
        """
        import json as json_module

        try:
            data = json_module.loads(response_json)
        except json_module.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON response: {e}") from e

        # Validate required fields
        required = ["weaknesses", "ai_dependency", "reasoning", "recommendations"]
        missing = [field for field in required if field not in data]

        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        # Validate field types
        if not isinstance(data.get("weaknesses"), list):
            raise ValueError("'weaknesses' must be a list")

        if not isinstance(data.get("recommendations"), list):
            raise ValueError("'recommendations' must be a list")

        if not isinstance(data.get("reasoning"), str):
            raise ValueError("'reasoning' must be a string")

        ai_dep = str(data.get("ai_dependency", "")).lower()
        if ai_dep not in ["low", "medium", "high"]:
            raise ValueError("'ai_dependency' must be 'low', 'medium', or 'high'")

        return data

    def build_safe_response(
        self, analysis_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build a safe, validated response from analysis data.

        Args:
            analysis_data: Parsed analysis response

        Returns:
            Clean response dictionary
        """
        return {
            "weaknesses": analysis_data.get("weaknesses", []),
            "ai_dependency": analysis_data.get("ai_dependency", "Low").capitalize(),
            "reasoning": analysis_data.get("reasoning", ""),
            "recommendations": analysis_data.get("recommendations", []),
        }
