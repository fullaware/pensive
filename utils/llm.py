# LLM and Embedding utilities
"""LLM and embedding model utilities."""
import httpx
from typing import List, Dict, Any, Optional
from memory_system.config import Config


class LLMClient:
    """Client for interacting with the LLM API."""

    def __init__(self):
        self.base_url = Config.LLM_URI
        self.model = Config.LLM_MODEL
        self._client = httpx.AsyncClient(timeout=60.0)

    async def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> Optional[str]:
        """Generate a response from the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt to set context
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Generated response string or None if error
        """
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            if system_prompt:
                payload["system"] = system_prompt

            response = await self._client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

            result = response.json()
            return result.get("choices", [{}])[0].get("message", {}).get("content", "")

        except Exception as e:
            print(f"Error generating LLM response: {e}")
            return None

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()


class EmbeddingClient:
    """Client for generating embeddings."""

    def __init__(self):
        self.base_url = Config.LLM_EMBEDDING_URI
        self.model = Config.LLM_EMBEDDING_MODEL
        self._client = httpx.AsyncClient(timeout=60.0)

    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate an embedding for the given text.

        Args:
            text: Input text to embed

        Returns:
            List of floats representing the embedding, or None if error
        """
        try:
            payload = {
                "model": self.model,
                "input": text,
            }

            response = await self._client.post(
                f"{self.base_url}/embeddings",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

            result = response.json()
            return result.get("data", [{}])[0].get("embedding", [])

        except Exception as e:
            print(f"Error generating embedding: {e}")
            return None

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of input texts to embed

        Returns:
            List of embeddings (list of floats)
        """
        embeddings = []
        for text in texts:
            embedding = await self.generate_embedding(text)
            if embedding:
                embeddings.append(embedding)
        return embeddings

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()


# Convenience functions
async def generate_llm_response(messages: List[Dict[str, str]], system_prompt: Optional[str] = None) -> Optional[str]:
    """Convenience function to generate an LLM response."""
    client = LLMClient()
    try:
        return await client.generate(messages, system_prompt)
    finally:
        await client.close()


async def generate_embedding(text: str) -> Optional[List[float]]:
    """Convenience function to generate an embedding."""
    client = EmbeddingClient()
    try:
        return await client.generate_embedding(text)
    finally:
        await client.close()