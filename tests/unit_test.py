import unittest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import os
import sys
from dotenv import load_dotenv

# Get the absolute path of the current file's directory
current_dir = os.path.dirname(os.path.abspath(__file__))

# Get the absolute path of the parent directory
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))

# Add the parent directory to sys.path
sys.path.append(parent_dir)

from client import MCPClient, parse_vector_string, cosine_similarity

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT")

client = MCPClient(DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)

class TestParseVectorString(unittest.TestCase):
    def test_parse_vector_string_valid(self):
        s = "[0.1, 0.2, 0.3]"
        vec = parse_vector_string(s)
        self.assertIsInstance(vec, np.ndarray)
        self.assertEqual(vec.shape, (3,))
        np.testing.assert_allclose(vec, [0.1, 0.2, 0.3])

    def test_parse_vector_string_invalid(self):
        with self.assertRaises(ValueError):
            parse_vector_string("[a, b, c]")


class TestSimilarity(unittest.TestCase):
    def test_cosine_similarity(self):
        a = np.array([1, 0, 0])
        b = np.array([1, 0, 0])
        c = np.array([0, 1, 0])

        self.assertAlmostEqual(cosine_similarity(a, b), 1.0)
        self.assertAlmostEqual(cosine_similarity(a, c), 0.0)

    def test_compare_embedding_threshold(self):
        query_emb = np.array([1.0, 0.0])
        memories = [
            (np.array([0.9, 0.1]), "near"),
            (np.array([-1.0, 0.0]), "opposite"),
        ]
        result = client.compare_embedding(query_emb, memories)
        self.assertIn("near", result)
        self.assertNotIn("opposite", result)

    def test_insert_stm_trims_memory(self):
        emb = np.zeros(768)
        for i in range(10):
            client.insert_stm(emb, f"text-{i}")
        self.assertLessEqual(len(client.memory), 5)


class TestAsyncProcessQuery(unittest.IsolatedAsyncioTestCase):
    @patch("client.MCPClient.embed_result", new_callable=AsyncMock, return_value=np.zeros(768))
    @patch("client.MCPClient.fetch_ltm", new_callable=AsyncMock, return_value=["past workout summary"])
    @patch("client.genai.Client")
    async def test_process_query_basic(self, mock_genai_client, mock_embed, mock_fetch):
        # Mock Gemini’s response
        mock_model = MagicMock()
        mock_model.models.generate_content.return_value.text = "Do 10 pushups daily"
        mock_genai_client.return_value = mock_model

        client.genai_client = mock_model

        result = await client.process_query("best arm exercise", channel_id="test")
        self.assertIsInstance(result, str)
        self.assertIn("pushups", result.lower())


if __name__ == "__main__":
    unittest.main()

