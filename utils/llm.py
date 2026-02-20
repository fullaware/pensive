# LLM and Embedding utilities
"""LLM and embedding model utilities."""
import httpx
import time
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
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> Optional[str]:
        """Generate a response from the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt to set context
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            tokens_in: Number of input tokens (for TPS calculation)
            tokens_out: Number of output tokens (for TPS calculation)

        Returns:
            Generated response string or None if error
        """
        start_time = time.time()
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
            elapsed = time.time() - start_time

            # Calculate tokens per second
            total_tokens = tokens_in + tokens_out
            tps = round(total_tokens / elapsed, 2) if elapsed > 0 else 0

            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"[LLM] elapsed={elapsed:.3f}s | tps={tps} | tokens_in={tokens_in} | tokens_out={tokens_out}")
            
            return content

        except Exception as e:
            elapsed = time.time() - start_time
            print(f"[LLM] error elapsed={elapsed:.3f}s | {e}")
            return None

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()


class EmbeddingClient:
    """Client for generating embeddings."""

    def __init__(self):
        self.base_url = Config.LLM_EMBEDDING_URI
        self.model = Config.LLM_EMBEDDING_MODEL
        self.dimensions = Config.EMBEDDING_DIMENSIONS
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
                f"{self.base_url}/v1/embeddings",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

            result = response.json()

            # Handle different response formats
            embedding = None

            # Format 1: OpenAI-compatible {"data": [{"embedding": [...]}}]
            if isinstance(result, dict):
                data = result.get("data")
                if isinstance(data, list) and len(data) > 0:
                    if isinstance(data[0], dict):
                        embedding = data[0].get("embedding")
                    elif isinstance(data[0], list):
                        # Data is a list of lists (embedding directly)
                        embedding = data[0]
            elif isinstance(result, list):
                # Result is a list - check for dict with embedding
                if len(result) > 0 and isinstance(result[0], dict):
                    # vLLM format: [{'index': 0, 'embedding': [[...]]}]
                    embedding_data = result[0].get('embedding')
                    if isinstance(embedding_data, list) and len(embedding_data) > 0:
                        # Handle both [[...]] and [...] formats
                        if isinstance(embedding_data[0], list):
                            # Nested list format - use first element
                            embedding = embedding_data[0]
                        else:
                            # Direct list format
                            embedding = embedding_data
                if len(result) > 0 and isinstance(result[0], list):
                    # Embedding might be the first element directly
                    embedding = result[0]

            # Validate embedding
            if embedding:
                if len(embedding) == self.dimensions:
                    return embedding
                print(f"Warning: Embedding has {len(embedding)} dims, expected {self.dimensions}")

            print(f"Warning: Could not extract embedding from response: {type(result)}")
            return None

        except Exception as e:
            print(f"Error generating embedding: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
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