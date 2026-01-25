# Plan: KPM33B MQTT Proxy/Bridge

This document outlines the implementation, testing, and deployment plan for the KPM33B MQTT Proxy/Bridge.

## Phase 1a: Core Implementation of data flow

-   [ ] Review the Two-Broker Bridge architecture described in ARCHITECTURE.md and layout a plan for implementation.
-   [ ] Configuration: draft `config.yaml` provided.
-   [ ] Plan Unit Testing: Mock and validate the two-broker architecture.

## Phase 1b: Implementation of config flow
-   [ ] Set device configuration: Read config.yaml and send upload frequency to devices, then log ack or timeout.

## Phase 2: Integration Testing and Deployment

This phase focuses on setting up the required broker infrastructure and preparing the application for production use.

### 1. Integration Test Environment Setup

-   Objective: Create a local environment that mimics the two-broker production setup to allow for end-to-end testing.
-   Tasks:
    -   [ ] Create `scripts/` directory: A new directory to hold helper scripts for testing and deployment.
    -   [ ] Develop `scripts/start_kpm33b_broker.sh`:
        *   Create a shell script to start a local Mosquitto instance that will act as the KPM33B Broker.
        *   This script will use a dedicated configuration file (`scripts/kpm33b_broker.conf`). It can run on localhost, whereas the central broker is on a different host.
    -   [ ] Develop `scripts/start_central_broker.sh`:
        *   Create a shell script to start a local Mosquitto instance that will mock the Central Broker.
        *   This script will use a dedicated configuration file (`scripts/central_broker.conf`) to run on a different port (e.g., 1884) and can be configured with data persistence.
    -   [ ] Create Broker Configuration Files:
        *   `scripts/kpm33b_broker.conf`: Basic Mosquitto configuration for the KPM33B Broker.
        *   `scripts/central_broker.conf`: Basic Mosquitto configuration for the central broker.
    -   [ ] Update `README.md`: Add a section explaining how to use these scripts to set up the integration test environment.

### 2. Production Deployment Preparation
-   Objective: Package the `kpm33b_proxy` application and its dependencies as systemd unit for easy and reliable deployment in a production environment.