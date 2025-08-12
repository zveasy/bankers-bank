# Changelog

All notable changes to this project will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/) and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.2] - 2025-07-06

### Added

* `/ltv/calculate` endpoint to the mock FastAPI server, with OpenAPI spec and error handling for edge cases.
* Integration and edge-case tests for LTV calculation, including test isolation via `/collateral/reset`.
* Documentation and request/response examples for `/ltv/calculate` and `/collateral/reset` in `docs/mock_api_endpoints.md`.

### Changed

* `BankersBankClient.calculate_ltv` now calls the mock API endpoint instead of local calculation.
* Improved test reliability and isolation for all collateral/LTV-related tests.

## [0.2.1] - 2025-07-03

### Added

* Python SDK helper `calculate_ltv` with accompanying unit and integration tests.
* Documentation for LTV calculation in `docs/mock_api_endpoints.md`.

## [0.2.2] - 2025-07-04

### Added

* OAuth2 token helper and `FinastraAPIClient`.
* Mock endpoints and fixtures for Account & Collateral APIs.
* Documentation in `docs/finastra_api.md`.

## \[0.2.0] - 2025‑05‑28

### Added

* **OpenAPI spec v0.2** with `/accounts`, `/transactions`, and `/sweeps` endpoints.
* **Auto‑generated SDKs**

  * Python client in `sdk/python`.
  * TypeScript‐Fetch client in `sdk/typescript`.
* **Makefile target `gen-sdk`** leveraging `openapi-generator-cli:v7.5.0`.
* **Smoke tests** (`tests/unit/test_clients.py`) ensuring the Python SDK imports and exposes `create_account`.

### Changed

- N/A

### Fixed

- N/A

---

## \[0.1.0] - 2025‑05‑27

### Added

* Initial repository scaffold, CI skeleton, directory layout.

