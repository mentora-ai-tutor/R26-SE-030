"""
Ollama LLM client for remote API calls.
Handles communication with Ollama server for text generation.
"""

import httpx
import json
import logging
from typing import Dict, Any, Optional
from datetime import timedelta

logger = logging.getLogger(__name__)


class OllamaClientError(Exception):
    """Base exception for Ollama client errors."""
    pass


class OllamaConnectionError(OllamaClientError):
    """Raised when unable to connect to Ollama server."""
    pass


class OllamaParseError(OllamaClientError):
    """Raised when unable to parse Ollama response."""
    pass


class OllamaClient:
    """
    Client for communicating with Ollama LLM API.
    Handles request/response and error handling.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
        timeout: int = 300,
    ):
        """
        Initialize Ollama client.

        Args:
            base_url: Ollama API base URL
            model: Model name to use (e.g., 'llama3', 'mistral')
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.logger = logger

    async def generate(
        self,
        prompt: str,
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate text using Ollama.

        Args:
            prompt: Input prompt for the model
            stream: Whether to stream response
            temperature: Model temperature (0-2)
            top_p: Nucleus sampling parameter
            top_k: Top-k sampling parameter

        Returns:
            Dictionary containing model response

        Raises:
            OllamaConnectionError: If unable to connect
            OllamaParseError: If response is invalid
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
        }

        # Add optional parameters if provided
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if top_k is not None:
            payload["top_k"] = top_k

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                )
                response.raise_for_status()
                return response.json()

        except httpx.ConnectError as e:
            msg = f"Failed to connect to Ollama at {self.base_url}: {e}"
            self.logger.error(msg)
            raise OllamaConnectionError(msg) from e
        except httpx.HTTPStatusError as e:
            msg = f"Ollama API error: {e.response.status_code} - {e.response.text}"
            self.logger.error(msg)
            raise OllamaClientError(msg) from e
        except httpx.RequestError as e:
            msg = f"Request error to Ollama: {e}"
            self.logger.error(msg)
            raise OllamaConnectionError(msg) from e
        except json.JSONDecodeError as e:
            msg = f"Invalid JSON response from Ollama: {e}"
            self.logger.error(msg)
            raise OllamaParseError(msg) from e

    def generate_sync(
        self,
        prompt: str,
        stream: bool = False,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Synchronous version of generate.
        Use when async context is not available.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
        }

        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
        if top_k is not None:
            payload["top_k"] = top_k

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                )
                response.raise_for_status()
                return response.json()

        except httpx.ConnectError as e:
            msg = f"Failed to connect to Ollama at {self.base_url}: {e}"
            self.logger.error(msg)
            raise OllamaConnectionError(msg) from e
        except httpx.HTTPStatusError as e:
            msg = f"Ollama API error: {e.response.status_code} - {e.response.text}"
            self.logger.error(msg)
            raise OllamaClientError(msg) from e
        except httpx.RequestError as e:
            msg = f"Request error to Ollama: {e}"
            self.logger.error(msg)
            raise OllamaConnectionError(msg) from e
        except json.JSONDecodeError as e:
            msg = f"Invalid JSON response from Ollama: {e}"
            self.logger.error(msg)
            raise OllamaParseError(msg) from e

    @staticmethod
    def extract_text(response: Dict[str, Any]) -> str:
        """
        Extract generated text from Ollama response.

        Args:
            response: Response dictionary from Ollama

        Returns:
            Generated text string

        Raises:
            OllamaParseError: If response structure is invalid
        """
        try:
            return response.get("response", "")
        except (AttributeError, TypeError) as e:
            msg = f"Invalid response structure: {e}"
            logger.error(msg)
            raise OllamaParseError(msg) from e

    async def check_health(self) -> bool:
        """
        Check if Ollama server is available.

        Returns:
            True if server is reachable, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception as e:
            self.logger.warning(f"Health check failed: {e}")
            return False

    def check_health_sync(self) -> bool:
        """
        Synchronous health check for Ollama server.
        """
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception as e:
            self.logger.warning(f"Health check failed: {e}")
            return False
