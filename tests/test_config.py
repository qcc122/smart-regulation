import os
import unittest
from unittest.mock import patch

from pydantic import SecretStr

from app.core.config import ConfigurationError, Settings


class SettingsTests(unittest.TestCase):
    def test_loads_environment_and_exposes_grouped_settings(self):
        values = {
            "ZHIPU_API_KEY": "zhipu-secret",
            "POSTGRES_PASSWORD": "postgres-secret",
            "MINERU_TOKEN": "mineru-secret",
            "POSTGRES_HOST": "postgres",
            "MILVUS_URI": "http://milvus:19530",
            "MAX_UPLOAD_MB": "32",
        }
        with patch.dict(os.environ, values, clear=True):
            settings = Settings(_env_file=None)

        self.assertEqual(settings.rag.milvus_uri, "http://milvus:19530")
        self.assertEqual(settings.db.host, "postgres")
        self.assertEqual(settings.max_upload_mb, 32)
        self.assertEqual(settings.rag.mineru_token.get_secret_value(), "mineru-secret")

    def test_required_credentials_are_reported_without_values(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)

        with self.assertRaises(ConfigurationError) as raised:
            settings.validate_required()

        message = str(raised.exception)
        self.assertIn("ZHIPU_API_KEY", message)
        self.assertIn("POSTGRES_PASSWORD", message)
        self.assertIn("MINERU_TOKEN", message)
        self.assertIn("SILICONFLOW_API_KEY", message)
        self.assertNotIn("secret", message)

    def test_secrets_are_masked_in_settings_repr(self):
        with patch.dict(os.environ, {
            "ZHIPU_API_KEY": "zhipu-secret",
            "POSTGRES_PASSWORD": "postgres-secret",
            "MINERU_TOKEN": "mineru-secret",
        }, clear=True):
            settings = Settings(_env_file=None)

        self.assertIsInstance(settings.zhipu_api_key, SecretStr)
        self.assertIsInstance(settings.postgres_password, SecretStr)
        self.assertIsInstance(settings.mineru_token, SecretStr)
        self.assertNotIn("zhipu-secret", repr(settings))
        self.assertNotIn("postgres-secret", repr(settings))
        self.assertNotIn("mineru-secret", repr(settings))


if __name__ == "__main__":
    unittest.main()
