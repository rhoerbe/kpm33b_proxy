#!/usr/bin/env python3
"""KPM33B MQTT Proxy — Data and Discovery Flow.

Subscribes to the internal broker for raw meter data,
transforms it, and publishes simplified data to the central broker.
"""

import logging
import signal
import sys

from src.bridge import MqttBridge
from src.config import load_config


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

    bridge = MqttBridge(config)

    def shutdown(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info("Received %s, shutting down", sig_name)
        bridge.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    bridge.connect()
    bridge.start()
    logger.info("kpm33b_proxy running — waiting for messages")

    # Block main thread; MQTT loops run in background threads
    signal.pause()


if __name__ == "__main__":
    main()
