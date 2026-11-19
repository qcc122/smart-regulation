import unittest
from unittest.mock import Mock, patch

from pydantic import SecretStr

from app.core.config import DbSettings
from app.core.database import create_database


class DatabaseFactoryTests(unittest.TestCase):
    def test_engine_uses_secret_safe_url_and_bounded_pool(self):
        settings = DbSettings(
            host="postgres",
            port=5432,
            name="insurance",
            user="insurance",
            password=SecretStr("p@ss:word"),
        )
        fake_engine = object()
        fake_factory = object()

        with patch("app.core.database.create_async_engine", return_value=fake_engine) as create_engine, patch(
            "app.core.database.async_sessionmaker", return_value=fake_factory
        ) as make_session_factory:
            database = create_database(settings)

        url = create_engine.call_args.args[0]
        self.assertEqual(url.drivername, "postgresql+asyncpg")
        self.assertEqual(url.password, "p@ss:word")
        self.assertEqual(url.host, "postgres")
        self.assertEqual(create_engine.call_args.kwargs["pool_size"], 5)
        self.assertEqual(create_engine.call_args.kwargs["max_overflow"], 5)
        self.assertIs(make_session_factory.call_args.args[0], fake_engine)
        self.assertIs(database.engine, fake_engine)
        self.assertIs(database.session_factory, fake_factory)


if __name__ == "__main__":
    unittest.main()
