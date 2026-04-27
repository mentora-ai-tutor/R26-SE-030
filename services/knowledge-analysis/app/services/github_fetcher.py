"""
GitHub API client for fetching commit data.
Retrieves commits from GitHub repositories using REST API.
"""

import httpx
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class GitHubFetcherError(Exception):
    """Base exception for GitHub fetcher errors."""
    pass


class GitHubAuthenticationError(GitHubFetcherError):
    """Raised when authentication fails."""
    pass


class GitHubRateLimitError(GitHubFetcherError):
    """Raised when rate limit is exceeded."""
    pass


class GitHubAPIError(GitHubFetcherError):
    """Raised when API call fails."""
    pass


class GitHubFetcher:
    """
    Client for fetching commit data from GitHub repositories.
    Uses GitHub REST API with personal access token authentication.
    """

    BASE_URL = "https://api.github.com"
    COMMITS_ENDPOINT = "/repos/{owner}/{repo}/commits"

    def __init__(
        self,
        token: str,
        base_url: str = BASE_URL,
        timeout: int = 30,
    ):
        """
        Initialize GitHub fetcher.

        Args:
            token: GitHub personal access token (PAT)
            base_url: GitHub API base URL
            timeout: Request timeout in seconds

        Raises:
            ValueError: If token is empty
        """
        if not token or not token.strip():
            raise ValueError("GitHub token cannot be empty")

        self.token = token.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.logger = logger

        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }

    async def get_commits(
        self,
        repo: str,
        days: int = 30,
        per_page: int = 100,
        author: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch commits from a GitHub repository.

        Args:
            repo: Repository in format "owner/repo" or full URL
            days: Number of days to look back (default: 30)
            per_page: Commits per page for pagination (default: 100, max: 100)
            author: Optional filter by author username

        Returns:
            List of commits in standardized format

        Raises:
            GitHubAuthenticationError: If token is invalid
            GitHubRateLimitError: If rate limit exceeded
            GitHubAPIError: If API call fails
            ValueError: If repo format is invalid
        """
        repo = repo.strip()

        # Parse repo URL or owner/repo format
        owner, repo_name = self._parse_repo(repo)

        if not owner or not repo_name:
            raise ValueError(f"Invalid repository format: {repo}")

        # Calculate date range
        since_date = (datetime.now() - timedelta(days=days)).isoformat()

        # Build query parameters
        params = {
            "since": since_date,
            "per_page": min(per_page, 100),  # GitHub max is 100
        }

        if author:
            params["author"] = author.strip()

        try:
            endpoint = self.COMMITS_ENDPOINT.format(owner=owner, repo=repo_name)
            url = urljoin(self.base_url, endpoint)

            self.logger.info(
                f"Fetching commits from {owner}/{repo_name} (last {days} days)"
            )

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self.headers, params=params)

                # Handle specific errors
                if response.status_code == 401:
                    msg = "GitHub authentication failed: Invalid token"
                    self.logger.error(msg)
                    raise GitHubAuthenticationError(msg)

                elif response.status_code == 403:
                    # Check for rate limiting
                    if "API rate limit exceeded" in response.text:
                        msg = "GitHub API rate limit exceeded"
                        self.logger.error(msg)
                        raise GitHubRateLimitError(msg)
                    msg = f"GitHub API forbidden: {response.text}"
                    self.logger.error(msg)
                    raise GitHubAPIError(msg)

                elif response.status_code == 404:
                    msg = f"Repository not found: {owner}/{repo_name}"
                    self.logger.error(msg)
                    raise GitHubAPIError(msg)

                response.raise_for_status()

                commits = response.json()
                self.logger.info(f"Fetched {len(commits)} commits")

                return self._normalize_commits(commits, owner, repo_name)

        except httpx.HTTPError as e:
            msg = f"GitHub API request failed: {e}"
            self.logger.error(msg)
            raise GitHubAPIError(msg) from e
        except ValueError as e:
            self.logger.error(f"Error processing commits: {e}")
            raise

    def get_commits_sync(
        self,
        repo: str,
        days: int = 30,
        per_page: int = 100,
        author: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Synchronous version of get_commits.
        Use when async context is not available.
        """
        repo = repo.strip()
        owner, repo_name = self._parse_repo(repo)

        if not owner or not repo_name:
            raise ValueError(f"Invalid repository format: {repo}")

        since_date = (datetime.now() - timedelta(days=days)).isoformat()

        params = {
            "since": since_date,
            "per_page": min(per_page, 100),
        }

        if author:
            params["author"] = author.strip()

        try:
            endpoint = self.COMMITS_ENDPOINT.format(owner=owner, repo=repo_name)
            url = urljoin(self.base_url, endpoint)

            self.logger.info(
                f"Fetching commits from {owner}/{repo_name} (last {days} days)"
            )

            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers=self.headers, params=params)

                if response.status_code == 401:
                    msg = "GitHub authentication failed: Invalid token"
                    self.logger.error(msg)
                    raise GitHubAuthenticationError(msg)

                elif response.status_code == 403:
                    if "API rate limit exceeded" in response.text:
                        msg = "GitHub API rate limit exceeded"
                        self.logger.error(msg)
                        raise GitHubRateLimitError(msg)
                    msg = f"GitHub API forbidden: {response.text}"
                    self.logger.error(msg)
                    raise GitHubAPIError(msg)

                elif response.status_code == 404:
                    msg = f"Repository not found: {owner}/{repo_name}"
                    self.logger.error(msg)
                    raise GitHubAPIError(msg)

                response.raise_for_status()

                commits = response.json()
                self.logger.info(f"Fetched {len(commits)} commits")

                return self._normalize_commits(commits, owner, repo_name)

        except httpx.HTTPError as e:
            msg = f"GitHub API request failed: {e}"
            self.logger.error(msg)
            raise GitHubAPIError(msg) from e
        except ValueError as e:
            self.logger.error(f"Error processing commits: {e}")
            raise

    @staticmethod
    def _parse_repo(repo: str) -> tuple[str, str]:
        """
        Parse repository in various formats.

        Accepts:
        - owner/repo
        - https://github.com/owner/repo
        - https://github.com/owner/repo.git

        Returns:
            Tuple of (owner, repo_name)
        """
        repo = repo.strip()

        # Handle full URL
        if repo.startswith("http"):
            # Remove .git suffix if present
            if repo.endswith(".git"):
                repo = repo[:-4]
            # Extract owner/repo from URL
            parts = repo.split("/")
            if len(parts) >= 2:
                return parts[-2], parts[-1]
            return "", ""

        # Handle owner/repo format
        if "/" in repo:
            parts = repo.split("/")
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip()

        return "", ""

    @staticmethod
    def _normalize_commits(
        commits: List[Dict[str, Any]], owner: str, repo: str
    ) -> List[Dict[str, Any]]:
        """
        Convert GitHub API commits to standardized format.

        Args:
            commits: Raw commits from GitHub API
            owner: Repository owner
            repo: Repository name

        Returns:
            Normalized commit list
        """
        normalized = []

        for commit_data in commits:
            try:
                commit = commit_data.get("commit", {})
                author = commit.get("author", {})

                normalized_commit = {
                    "repo": f"{owner}/{repo}",
                    "message": commit.get("message", "").strip(),
                    "timestamp": author.get("date", ""),
                    "additions": 0,  # Available in commits endpoint
                    "deletions": 0,  # Available in commits endpoint
                    "author": commit_data.get("author", {}).get("login", ""),
                    "sha": commit_data.get("sha", ""),
                }

                # Only add if message exists
                if normalized_commit["message"]:
                    normalized.append(normalized_commit)

            except (KeyError, AttributeError, TypeError) as e:
                logger.warning(f"Error normalizing commit: {e}")
                continue

        return normalized

    async def check_auth(self) -> bool:
        """
        Check if authentication is valid.

        Returns:
            True if authenticated, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    urljoin(self.base_url, "/user"),
                    headers=self.headers,
                )
                return response.status_code == 200
        except Exception as e:
            self.logger.warning(f"Authentication check failed: {e}")
            return False

    def check_auth_sync(self) -> bool:
        """
        Synchronous authentication check.
        """
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    urljoin(self.base_url, "/user"),
                    headers=self.headers,
                )
                return response.status_code == 200
        except Exception as e:
            self.logger.warning(f"Authentication check failed: {e}")
            return False

    async def get_rate_limit(self) -> Dict[str, Any]:
        """
        Get current rate limit status.

        Returns:
            Rate limit information
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    urljoin(self.base_url, "/rate_limit"),
                    headers=self.headers,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            self.logger.error(f"Failed to get rate limit: {e}")
            return {}
