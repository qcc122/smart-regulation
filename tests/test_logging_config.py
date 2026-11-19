import io
import logging
import unittest

from app.core.logging import ColorFormatter, configure_logging


class LoggingConfigTests(unittest.TestCase):
    def test_color_formatter_colors_by_level(self):
        formatter = ColorFormatter("%(levelname)s %(message)s", use_color=True)
        record = logging.LogRecord("test", logging.WARNING, "", 0, "careful", (), None)

        formatted = formatter.format(record)

        self.assertIn("\x1b[33m", formatted)
        self.assertIn("WARNING careful", formatted)
        self.assertTrue(formatted.endswith("\x1b[0m"))

    def test_configured_handler_redacts_credentials(self):
        stream = io.StringIO()
        logger = logging.getLogger("test.settings.redaction")
        old_handlers = logger.handlers[:]
        old_level = logger.level
        try:
            configure_logging(logger=logger, stream=stream, secrets=["api-secret", "db-secret"])
            logger.error("credential=%s password=%s", "api-secret", "db-secret")
        finally:
            for handler in logger.handlers[:]:
                handler.close()
            logger.handlers = old_handlers
            logger.setLevel(old_level)

        output = stream.getvalue()
        self.assertNotIn("api-secret", output)
        self.assertNotIn("db-secret", output)
        self.assertIn("[REDACTED]", output)

    def test_configured_handler_redacts_exception_text(self):
        stream = io.StringIO()
        logger = logging.getLogger("test.settings.exception.redaction")
        old_handlers = logger.handlers[:]
        old_level = logger.level
        try:
            configure_logging(logger=logger, stream=stream, secrets=["api-secret"])
            try:
                raise RuntimeError("api-secret")
            except RuntimeError:
                logger.exception("request failed")
        finally:
            for handler in logger.handlers[:]:
                handler.close()
            logger.handlers = old_handlers
            logger.setLevel(old_level)

        output = stream.getvalue()
        self.assertNotIn("api-secret", output)
        self.assertIn("[REDACTED]", output)


if __name__ == "__main__":
    unittest.main()
