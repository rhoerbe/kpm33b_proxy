#!/usr/bin/env python3
"""KPM33B Config Sender — Configuration Flow.

Discovers meters via the central broker, sends upload frequency
settings to meters via the internal broker, and monitors config changes.
"""

import logging
import signal
import sys
from pathlib import Path

from src.config import load_config
from src.config_sender import ConfigSender


def setup_logging(level: str, log_file: str) -> None:
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(log_path),
    ]
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def main() -> None:
    config = load_config()
    setup_logging(config.logging.level, config.logging.file)
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
