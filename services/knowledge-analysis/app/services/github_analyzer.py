"""
GitHub commits behavioral analysis module.
Computes metrics from commit data for learning pattern detection.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
import statistics
import logging

logger = logging.getLogger(__name__)


@dataclass
class CommitData:
    """Represents a single GitHub commit."""
    repo: str
    message: str
    timestamp: str  # ISO format or Unix timestamp
    additions: int
    deletions: int


@dataclass
class BehaviorSummary:
    """Aggregated behavioral metrics from commits."""
    commit_count: int
    avg_time_gap: float  # seconds
    message_quality: float  # 0-1 score
    big_bang_detected: bool
    total_additions: int
    total_deletions: int
    avg_commit_size: float
    repos_count: int


class GitHubAnalyzer:
    """
    Analyzes GitHub commit data to extract learning behavior patterns.
    """

    MIN_MESSAGE_LENGTH = 10
    MAX_MESSAGE_LENGTH = 500
    BIG_BANG_THRESHOLD_ADDITIONS = 500
    BIG_BANG_THRESHOLD_FREQUENCY = 7  # days

    def __init__(self):
        """Initialize the GitHub analyzer."""
        self.logger = logger

    def analyze_commits(self, commits: List[Dict[str, Any]]) -> BehaviorSummary:
        """
        Analyze a list of GitHub commits and generate behavior summary.

        Args:
            commits: List of commit dictionaries containing repo, message, 
                    timestamp, additions, deletions

        Returns:
            BehaviorSummary: Aggregated behavioral metrics

        Raises:
            ValueError: If commits list is empty or invalid
        """
        if not commits:
            raise ValueError("Commits list cannot be empty")

        # Validate and convert commits
        validated_commits = self._validate_commits(commits)

        if not validated_commits:
            raise ValueError("No valid commits after validation")

        # Calculate metrics
        commit_count = len(validated_commits)
        avg_time_gap = self._calculate_avg_time_gap(validated_commits)
        message_quality = self._calculate_message_quality(validated_commits)
        big_bang = self._detect_big_bang(validated_commits, avg_time_gap)
        total_additions = sum(c.additions for c in validated_commits)
        total_deletions = sum(c.deletions for c in validated_commits)
        avg_commit_size = (total_additions + total_deletions) / commit_count
        repos_count = len(set(c.repo for c in validated_commits))

        summary = BehaviorSummary(
            commit_count=commit_count,
            avg_time_gap=avg_time_gap,
            message_quality=message_quality,
            big_bang_detected=big_bang,
            total_additions=total_additions,
            total_deletions=total_deletions,
            avg_commit_size=avg_commit_size,
            repos_count=repos_count,
        )

        return summary

    def _validate_commits(self, commits: List[Dict[str, Any]]) -> List[CommitData]:
        """Validate and convert raw commit dicts to CommitData objects."""
        validated = []
        required_fields = {"repo", "message", "timestamp", "additions", "deletions"}

        for i, commit in enumerate(commits):
            try:
                if not isinstance(commit, dict):
                    self.logger.warning(f"Commit {i} is not a dict, skipping")
                    continue

                missing = required_fields - set(commit.keys())
                if missing:
                    self.logger.warning(
                        f"Commit {i} missing fields {missing}, skipping"
                    )
                    continue

                commit_obj = CommitData(
                    repo=str(commit["repo"]).strip(),
                    message=str(commit["message"]).strip(),
                    timestamp=str(commit["timestamp"]).strip(),
                    additions=int(commit["additions"]),
                    deletions=int(commit["deletions"]),
                )

                if not commit_obj.repo or not commit_obj.message:
                    self.logger.warning(f"Commit {i} has empty repo or message")
                    continue

                validated.append(commit_obj)
            except (ValueError, TypeError) as e:
                self.logger.warning(f"Error processing commit {i}: {e}")
                continue

        return validated

    def _calculate_avg_time_gap(self, commits: List[CommitData]) -> float:
        """
        Calculate average time gap between commits in seconds.
        """
        if len(commits) < 2:
            return 0.0

        timestamps = self._parse_timestamps(commits)
        if len(timestamps) < 2:
            return 0.0

        timestamps.sort()
        gaps = []

        for i in range(1, len(timestamps)):
            gap = (timestamps[i] - timestamps[i - 1]).total_seconds()
            gaps.append(gap)

        return statistics.mean(gaps) if gaps else 0.0

    def _parse_timestamps(
        self, commits: List[CommitData]
    ) -> List[datetime]:
        """Parse timestamp strings to datetime objects."""
        timestamps = []

        for commit in commits:
            try:
                # Try ISO format first
                ts = datetime.fromisoformat(commit.timestamp.replace("Z", "+00:00"))
                timestamps.append(ts)
            except (ValueError, AttributeError):
                try:
                    # Try Unix timestamp
                    ts = datetime.fromtimestamp(float(commit.timestamp))
                    timestamps.append(ts)
                except (ValueError, OSError):
                    self.logger.warning(
                        f"Could not parse timestamp: {commit.timestamp}"
                    )
                    continue

        return timestamps

    def _calculate_message_quality(self, commits: List[CommitData]) -> float:
        """
        Calculate average message quality (0-1 scale).
        Based on message length and clarity heuristics.
        """
        if not commits:
            return 0.0

        scores = []

        for commit in commits:
            msg = commit.message
            length = len(msg)

            # Length score: 0-1 based on optimal range
            if length < self.MIN_MESSAGE_LENGTH:
                length_score = length / self.MIN_MESSAGE_LENGTH * 0.5
            elif length > self.MAX_MESSAGE_LENGTH:
                length_score = max(0, 1 - (length - self.MAX_MESSAGE_LENGTH) / 500)
            else:
                length_score = min(1.0, length / (self.MAX_MESSAGE_LENGTH * 0.7))

            # Clarity score: check for common quality indicators
            clarity_score = 0.5
            if any(
                keyword in msg.lower()
                for keyword in ["fix", "add", "refactor", "improve", "update"]
            ):
                clarity_score = 0.7

            if any(
                keyword in msg.lower()
                for keyword in ["fix bug", "refactor", "improve performance"]
            ):
                clarity_score = 0.9

            # Avoid vague messages
            if any(
                msg.lower().startswith(word)
                for word in ["update", "changes", "work", "stuff", "asdf"]
            ):
                clarity_score = 0.3

            # Combined score
            score = (length_score * 0.6) + (clarity_score * 0.4)
            scores.append(min(1.0, score))

        return statistics.mean(scores) if scores else 0.0

    def _detect_big_bang(
        self, commits: List[CommitData], avg_time_gap: float
    ) -> bool:
        """
        Detect 'big bang' pattern: large commits with low frequency.
        Indicates rushed work or AI-assisted coding.
        """
        if not commits:
            return False

        # Check if average commit size is large
        avg_size = sum(c.additions + c.deletions for c in commits) / len(commits)
        large_commits = avg_size > self.BIG_BANG_THRESHOLD_ADDITIONS

        # Check if commits are infrequent (gaps > 7 days)
        # Convert seconds to days
        gap_days = avg_time_gap / (60 * 60 * 24) if avg_time_gap > 0 else 0
        infrequent = gap_days > self.BIG_BANG_THRESHOLD_FREQUENCY

        # Also check if there are very large single commits
        has_massive_commit = any(
            (c.additions + c.deletions) > self.BIG_BANG_THRESHOLD_ADDITIONS * 2
            for c in commits
        )

        return (large_commits and infrequent) or has_massive_commit

    def to_dict(self, summary: BehaviorSummary) -> Dict[str, Any]:
        """Convert BehaviorSummary to dictionary for JSON serialization."""
        return {
            "commit_count": summary.commit_count,
            "avg_time_gap_seconds": round(summary.avg_time_gap, 2),
            "message_quality": round(summary.message_quality, 2),
            "big_bang_detected": summary.big_bang_detected,
            "total_additions": summary.total_additions,
            "total_deletions": summary.total_deletions,
            "avg_commit_size": round(summary.avg_commit_size, 2),
            "repos_count": summary.repos_count,
        }
