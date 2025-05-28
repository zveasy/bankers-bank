# Changelog

All notable changes to this project will be documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/) and this project adheres to [Semantic Versioning](https://semver.org/).

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

