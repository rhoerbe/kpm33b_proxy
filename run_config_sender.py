#!/usr/bin/env python3
"""KPM33B Config Sender — Configuration Flow.

Discovers meters via the central broker, sends upload frequency
settings to meters via the internal broker, and monitors config changes.
"""

import logging
import signal
import sys

from src.config import load_config
from src.config_sender import ConfigSender


def setup_logging(level: str) -> None:
    """Configure logging to stdout for journalctl management."""
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )


def main() -> None:
    config = load_config()
    setup_logging(config.logging.level)
    logger = logging.getLogger(__name__)

    sender = ConfigSender(config)

    def shutdown(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info("Received %s, shutting down", sig_name)
        sender.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    sender.connect()
    sender.start()
    logger.info("config_sender running — waiting for meter discovery")

    signal.pause()


if __name__ == "__main__":
    main()
