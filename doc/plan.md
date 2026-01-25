# Plan: KPM33B MQTT Proxy/Bridge

This document outlines the implementation, testing, and deployment plan for the KPM33B MQTT Proxy/Bridge.

## Phase 1a: Core Implementation (completed)

-   [x] **Architectural Decision:** Approved the **Two-Broker Bridge** architecture to isolate raw device traffic.
-   [x] **Configuration:** Refactored `config.yaml` to support a `kpm33b_broker` and a `central_broker`.
-   [x] **Proxy/Bridge Logic:** Refactored `kpm33b_proxy.py` to:
    -   Connect to two MQTT brokers simultaneously.
    -   Subscribe to raw device topics (`MQTT_RT_DATA`, `MQTT_ENY_NOW`) on the `kpm33b_broker`.
    -   Transform the data, extracting key metrics and handling missing data.
    -   Publish simplified, structured data to the `central_broker` under a new topic hierarchy (`kpm33b/<device_id>/<seconds|minutes>`).
    -   Periodically send configuration to devices via the `kpm33b_broker`.
-   [x] **Unit Testing:** Refactored `test_kpm33b_proxy.py` to mock and validate the two-broker architecture.

## Phase 1b: Reverse Communication
-   [ ] **Set device configuration:** Read config.yaml and send messages to devices to set system time and reporting intervals.
-   [ ] **Integration test**

## Phase 2: Integration Testing and Deployment

This phase focuses on setting up the required broker infrastructure and preparing the application for production use.

### 1. Integration Test Environment Setup

-   **Objective:** Create a local environment that mimics the two-broker production setup to allow for end-to-end testing.
-   **Tasks:**
    -   [ ] **Create `scripts/` directory:** A new directory to hold helper scripts for testing and deployment.
    -   [ ] **Develop `scripts/start_kpm33b_broker.sh`:**
        *   Create a shell script to start a local Mosquitto instance that will act as the **KPM33B Broker**.
        *   This script will use a dedicated configuration file (`scripts/kpm33b_broker.conf`) to ensure it runs on a different port (e.g., 1883) from the central broker and does not persist data.
    -   [ ] **Develop `scripts/start_central_broker.sh`:**
        *   Create a shell script to start a local Mosquitto instance that will act as the **Central Broker**.
        *   This script will use a dedicated configuration file (`scripts/central_broker.conf`) to run on a different port (e.g., 1884) and can be configured with data persistence.
    -   [ ] **Create Broker Configuration Files:**
        *   `scripts/kpm33b_broker.conf`: Basic Mosquitto configuration for the KPM33B Broker.
        *   `scripts/central_broker.conf`: Basic Mosquitto configuration for the central broker.
    -   [ ] **Update `README.md`:** Add a section explaining how to use these scripts to set up the integration test environment.

### 2. Production Deployment Preparation

-   **Objective:** Package the `kpm33b_proxy` application and its dependencies into a container for easy and reliable deployment in a production environment.
-   **Tasks:**
    -   [ ] **Create `Dockerfile`:**
        *   Develop a `Dockerfile` in the `KPM33B/mqtt_proxy/` directory.
        *   The `Dockerfile` will:
            *   Use a lightweight Python base image (e.g., `python:3.11-slim`).
            *   Copy the application files (`kpm33b_proxy.py`, `config_loader.py`, etc.).
            *   Install dependencies from `requirements.txt`.
            *   Set the `kpm33b_proxy.py` script as the container's entrypoint.
    -   [ ] **Create `docker-compose.yml` for Production:**
        *   Develop a `docker-compose.yml` file to orchestrate the production environment.
        *   This will define three services:
            1.  `kpm33b-broker`: A Mosquitto container for the raw device data.
            2.  `central-broker`: A Mosquitto container for the central broker, with data persistence configured.
            3.  `kpm33b-proxy`: The container built from our `Dockerfile`.
        *   The `docker-compose.yml` will also manage networking between the containers.
    -   [ ] **Update `README.md`:** Add a section on "Production Deployment" explaining how to use Docker and `docker-compose` to run the entire system.
