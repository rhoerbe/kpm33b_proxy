#!/usr/bin/env python3
"""433 MHz RF Bridge MQTT Proxy — Portisch/Tasmota AA B1 Frame Decoder.

Subscribes to the internal broker for raw RF data from a Sonoff RF Bridge
running Tasmota + Portisch firmware, decodes PDM bucket frames, maps sensor
IDs to friendly names, and republishes structured JSON to the central broker.
"""

import logging
import signal
import sys
import time
from pathlib import Path

import yaml

from src.rfbridge.bridge import RfBridgeConfig, RfBridgeMqttBridge

PROJECT_ROOT = Path(__file__).resolve().parent


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )


def load_config(config_path: Path) -> RfBridgeConfig:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open() as f:
        raw = yaml.safe_load(f)
    return RfBridgeConfig(raw)


def main() -> None:
    config_path = PROJECT_ROOT / "config.yaml"
    config = load_config(config_path)
    setup_logging(config.logging_level)
    logger = logging.getLogger(__name__)

    sensors_path = PROJECT_ROOT / "sensors.yaml"
    bridge = RfBridgeMqttBridge(config, sensors_path)

    def shutdown(signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info("Received %s, shutting down", sig_name)
        bridge.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    bridge.connect()
    bridge.start()
    logger.info("433rfbridge_proxy running — waiting for messages")

    maintenance_interval = 60  # seconds
    while True:
        time.sleep(maintenance_interval)
        bridge.run_maintenance()


if __name__ == "__main__":
    main()
