# GammaMarkets Qualification Report

- Generated (UTC): 2026-09-20T06:50:10.683724+00:00
- Verify command: `make verify`
- Profile: Python 3.12.13 (CPython), arm64/darwin, database dialect: sqlite
- Pins: nostr-sdk 0.44.8, LNbits v1.6.2-rc1 at e336fe14b841
- Tested binary: libnostr_sdk_ffi.dylib (sha256 49b779657adfc809..., 4970368 bytes)
- Result: 25/25 passed (0 failed, 0 errors, 0 skipped), exit status 0

Rerun policy: Single run only (D-10 clean-pass policy): the tooling performs one run per verify command and has no retry loop; a rerun does not flip a recorded outcome.

## P0 Coverage Map

| P0 | Status | Tests |
| --- | --- | --- |
| P0-01 | pass | 17 |
| P0-02 | pass | 5 |
| P0-03 | pending | 0 |
| P0-04 | pending | 0 |
| P0-05 | pending | 0 |
| P0-06 | pass | 3 |
| P0-07 | pending | 0 |
| P0-08 | pending | 0 |
| P0-09 | pending | 0 |
| P0-10 | pending | 0 |
| P0-11 | pending | 0 |
| P0-12 | pending | 0 |
| P0-13 | pending | 0 |
| P0-14 | pending | 0 |

## Results

| Test | P0 | Markers | Outcome | Duration (s) |
| --- | --- | --- | --- | --- |
| `tests/qualification/test_p0_01_pins.py::test_host_checkout_head_is_pinned_commit` | P0-01 | fast | passed | 0.020 |
| `tests/qualification/test_p0_01_pins.py::test_installed_nostr_sdk_is_exactly_pinned` | P0-01 | fast | passed | 0.001 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[0.44.8-nostr-sdk candidate pin]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[5dc79c5-GammaMarkets market-spec pin]` | P0-01 | fast, parametrize | passed | 0.001 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[Linux ARM64-blocking platform (ARM64)]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[Linux x86_64-blocking platform (x86_64)]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[PENDING-approval section (D-11)]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[PostgreSQL-blocking database]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[Python 3.12 only-Python 3.12-only claim (D-02)]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[SQLite-blocking database]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[a2494f4f81d46684e5814a9bf35e2b1df978f955-Nostr NIPs pin]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[e336fe14b841d6f0c940e75b3d343e3ab5cf8433-LNbits commit pin]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[macOS ARM64-advisory smoke profile]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[v1.6.2-rc1-LNbits tag]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[v2 payload only-NIP-44 v2-only pin]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_requires_python_is_3_12_only` | P0-01 | fast | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_running_interpreter_is_3_12` | P0-01 | fast | passed | 0.000 |
| `tests/qualification/test_p0_02_sdk_security.py::test_build_sign_and_verify_event` | P0-02 | asyncio, sdk | passed | 0.005 |
| `tests/qualification/test_p0_02_sdk_security.py::test_ffi_import_and_keypair_generation` | P0-02 | asyncio, sdk | passed | 0.007 |
| `tests/qualification/test_p0_02_sdk_security.py::test_nip44_encrypt_decrypt_roundtrip` | P0-02 | asyncio, sdk | passed | 0.001 |
| `tests/qualification/test_p0_02_sdk_security.py::test_tampered_event_fails_verification` | P0-02 | asyncio, sdk | passed | 0.002 |
| `tests/qualification/test_p0_02_sdk_security.py::test_tested_binary_identity_recorded_into_evidence_pins` | P0-02 | asyncio, sdk | passed | 0.021 |
| `tests/qualification/test_p0_06_transactions.py::test_lost_cas_rolls_back_the_entire_transaction` | P0-06 | asyncio, db | passed | 0.005 |
| `tests/qualification/test_p0_06_transactions.py::test_orphan_reservation_insert_violates_fk` | P0-06 | asyncio, db | passed | 0.004 |
| `tests/qualification/test_p0_06_transactions.py::test_winning_cas_leaves_one_held_reservation` | P0-06 | asyncio, db | passed | 0.011 |

## Failures

None.

## D-16 Disclosure — Subcheck Attribution

P0-02 subchecks are attributed as `sdk-internal` (blocking under D-13/D-16: an SDK-internal regression cannot be waived) or `admission-modeled` (extension-side defense in depth only).

_No attributed subchecks in this run._

