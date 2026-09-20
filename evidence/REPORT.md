# GammaMarkets Qualification Report

- Generated (UTC): 2026-09-20T07:30:01.040260+00:00
- Verify command: `make verify`
- Profile: Python 3.12.13 (CPython), arm64/darwin, database dialect: postgres
- Pins: nostr-sdk 0.44.8, LNbits v1.6.2-rc1 at e336fe14b841
- Tested binary: libnostr_sdk_ffi.dylib (sha256 49b779657adfc809..., 4970368 bytes)
- Result: 106/106 passed (0 failed, 0 errors, 0 skipped), exit status 0

Rerun policy: Single run only (D-10 clean-pass policy): the tooling performs one run per verify command and has no retry loop; a rerun does not flip a recorded outcome.

## P0 Coverage Map

| P0 | Status | Tests |
| --- | --- | --- |
| P0-01 | pass | 33 |
| P0-02 | pass | 10 |
| P0-03 | pass | 3 |
| P0-04 | pending | 0 |
| P0-05 | pending | 0 |
| P0-06 | pass | 19 |
| P0-07 | pass | 10 |
| P0-08 | pass | 15 |
| P0-09 | pass | 7 |
| P0-10 | pass | 9 |
| P0-11 | pending | 0 |
| P0-12 | pending | 0 |
| P0-13 | pending | 0 |
| P0-14 | pending | 0 |

## Results

| Test | P0 | Markers | Outcome | Duration (s) |
| --- | --- | --- | --- | --- |
| `tests/qualification/test_p0_01_pins.py::test_evidence_pins_block_matches_recorded_values` | P0-01 | fast | passed | 0.130 |
| `tests/qualification/test_p0_01_pins.py::test_harness_lock_wheel_parity_with_host_lock` | P0-01 | fast | passed | 0.048 |
| `tests/qualification/test_p0_01_pins.py::test_host_checkout_head_is_pinned_commit` | P0-01 | fast | passed | 0.017 |
| `tests/qualification/test_p0_01_pins.py::test_host_lock_and_pypi_are_wheels_only` | P0-01 | fast | passed | 0.033 |
| `tests/qualification/test_p0_01_pins.py::test_installed_nostr_sdk_is_exactly_pinned` | P0-01 | fast | passed | 0.001 |
| `tests/qualification/test_p0_01_pins.py::test_installed_wheel_matches_machine_platform` | P0-01 | fast | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_native_library_hash_recorded_into_evidence_pins` | P0-01 | fast | passed | 0.025 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[0.44.8-nostr-sdk candidate pin]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[5dc79c5-GammaMarkets market-spec pin]` | P0-01 | fast, parametrize | passed | 0.001 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[Linux ARM64-blocking platform (ARM64)]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[Linux x86_64-blocking platform (x86_64)]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[PENDING-approval section (D-11)]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[PostgreSQL-blocking database]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[Python 3.12 only-Python 3.12-only claim (D-02)]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[SQLite-blocking database]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[a2494f4f81d46684e5814a9bf35e2b1df978f955-Nostr NIPs pin]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[a600c2a7186559b371030fe5fc5585c37b3a0931-release-source revision]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[chacha20poly1305-native Cargo dependency pin]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[e336fe14b841d6f0c940e75b3d343e3ab5cf8433-LNbits commit pin]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[hashed artifacts-D-15 contingency criterion]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[macOS ARM64-advisory smoke profile]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[owner approval-D-15 contingency criterion]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[pinned native revision-D-15 contingency criterion]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[reproducible build-D-15 contingency criterion]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[rust-nostr/nostr-sdk-ffi-release-source repository]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[secp256k1-native Cargo dependency pin]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[uv.lock-lockfile identity]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[v1.6.2-rc1-LNbits tag]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[v2 payload only-NIP-44 v2-only pin]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[wheels only-no-sdist provenance fact]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_release_source_and_native_cargo_provenance` | P0-01 | fast | passed | 0.050 |
| `tests/qualification/test_p0_01_pins.py::test_requires_python_is_3_12_only` | P0-01 | fast | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_running_interpreter_is_3_12` | P0-01 | fast | passed | 0.000 |
| `tests/qualification/test_p0_02_sdk_security.py::test_auth_flood_bounded_with_signing_paused` | P0-02 | asyncio, sdk | passed | 1.166 |
| `tests/qualification/test_p0_02_sdk_security.py::test_build_sign_and_verify_event` | P0-02 | asyncio, sdk | passed | 0.002 |
| `tests/qualification/test_p0_02_sdk_security.py::test_d16_subcheck_attribution_recorded` | P0-02 | asyncio, sdk | passed | 0.001 |
| `tests/qualification/test_p0_02_sdk_security.py::test_ffi_import_and_keypair_generation` | P0-02 | asyncio, sdk | passed | 0.002 |
| `tests/qualification/test_p0_02_sdk_security.py::test_invalid_events_rejected_before_trusted_processing` | P0-02 | asyncio, sdk | passed | 0.001 |
| `tests/qualification/test_p0_02_sdk_security.py::test_known_id_repetition_admitted_exactly_once` | P0-02 | asyncio, sdk | passed | 0.001 |
| `tests/qualification/test_p0_02_sdk_security.py::test_nip44_encrypt_decrypt_roundtrip` | P0-02 | asyncio, sdk | passed | 0.001 |
| `tests/qualification/test_p0_02_sdk_security.py::test_oversized_nip44_input_rejected_with_bounded_cost` | P0-02 | asyncio, sdk | passed | 2.663 |
| `tests/qualification/test_p0_02_sdk_security.py::test_tampered_event_fails_verification` | P0-02 | asyncio, sdk | passed | 0.001 |
| `tests/qualification/test_p0_02_sdk_security.py::test_tested_binary_identity_recorded_into_evidence_pins` | P0-02 | asyncio, sdk | passed | 0.050 |
| `tests/qualification/test_p0_03_host_contract.py::test_invoice_listener_lifecycle_and_owned_handle_cancellation` | P0-03 | asyncio, host | passed | 2.279 |
| `tests/qualification/test_p0_03_host_contract.py::test_invoice_metadata_persisted_and_exactly_queryable` | P0-03 | asyncio, host | passed | 1.151 |
| `tests/qualification/test_p0_03_host_contract.py::test_no_durable_callback_delivery_across_restart` | P0-03 | asyncio, host | passed | 5.145 |
| `tests/qualification/test_p0_06_transactions.py::test_adapter_only_transaction_rolls_back_cleanly` | P0-06 | asyncio, db | passed | 0.103 |
| `tests/qualification/test_p0_06_transactions.py::test_adapter_performs_in_transaction_writes_without_host_helpers` | P0-06 | asyncio, db | passed | 0.105 |
| `tests/qualification/test_p0_06_transactions.py::test_concurrent_duplicate_scoped_order_inserts_yield_one_row` | P0-06 | asyncio, db | passed | 0.124 |
| `tests/qualification/test_p0_06_transactions.py::test_dialect_selection_matches_environment` | P0-06 | db | passed | 0.000 |
| `tests/qualification/test_p0_06_transactions.py::test_duplicate_scoped_order_insert_conflicts` | P0-06 | asyncio, db | passed | 0.104 |
| `tests/qualification/test_p0_06_transactions.py::test_guard_failure_mid_claim_rolls_back_everything` | P0-06 | asyncio, db | passed | 0.129 |
| `tests/qualification/test_p0_06_transactions.py::test_host_auto_commit_helper_splits_domain_transaction` | P0-06 | asyncio, db | passed | 0.101 |
| `tests/qualification/test_p0_06_transactions.py::test_idempotency_record_scope_conflict` | P0-06 | asyncio, db | passed | 0.111 |
| `tests/qualification/test_p0_06_transactions.py::test_last_unit_concurrency_yields_exactly_one_reservation` | P0-06 | asyncio, db | passed | 0.172 |
| `tests/qualification/test_p0_06_transactions.py::test_lost_cas_rolls_back_the_entire_transaction` | P0-06 | asyncio, db | passed | 0.116 |
| `tests/qualification/test_p0_06_transactions.py::test_order_state_machine_table_exhaustive` | P0-06 | asyncio, db | passed | 0.332 |
| `tests/qualification/test_p0_06_transactions.py::test_orphan_inserts_violate_foreign_keys[inventory_reservations-params0]` | P0-06 | asyncio, db, parametrize | passed | 0.102 |
| `tests/qualification/test_p0_06_transactions.py::test_orphan_inserts_violate_foreign_keys[inventory_reservations-params1]` | P0-06 | asyncio, db, parametrize | passed | 0.105 |
| `tests/qualification/test_p0_06_transactions.py::test_orphan_inserts_violate_foreign_keys[order_items-params2]` | P0-06 | asyncio, db, parametrize | passed | 0.104 |
| `tests/qualification/test_p0_06_transactions.py::test_orphan_inserts_violate_foreign_keys[order_items-params3]` | P0-06 | asyncio, db, parametrize | passed | 0.110 |
| `tests/qualification/test_p0_06_transactions.py::test_orphan_inserts_violate_foreign_keys[relay_publications-params4]` | P0-06 | asyncio, db, parametrize | passed | 0.113 |
| `tests/qualification/test_p0_06_transactions.py::test_sorted_id_locking_avoids_deadlock` | P0-06 | asyncio, db | passed | 0.436 |
| `tests/qualification/test_p0_06_transactions.py::test_task_lease_fencing_rejects_stale_writes` | P0-06 | asyncio, db | passed | 0.117 |
| `tests/qualification/test_p0_06_transactions.py::test_winning_cas_leaves_one_held_reservation` | P0-06 | asyncio, db | passed | 0.265 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_during_inflight_invoice_creation[rejected]` | P0-07 | asyncio, db, parametrize | passed | 0.054 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_during_inflight_invoice_creation[success]` | P0-07 | asyncio, db, parametrize | passed | 0.057 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_during_inflight_invoice_creation[unknown]` | P0-07 | asyncio, db, parametrize | passed | 0.056 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_from_awaiting_payment_then_late_settlement` | P0-07 | asyncio, db | passed | 0.064 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_from_received_never_creates_an_invoice[rejected]` | P0-07 | asyncio, db, parametrize | passed | 0.054 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_from_received_never_creates_an_invoice[success]` | P0-07 | asyncio, db, parametrize | passed | 0.054 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_from_received_never_creates_an_invoice[unknown]` | P0-07 | asyncio, db, parametrize | passed | 0.052 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_creation_unknown_reconciliation_attaches_exactly_one` | P0-07 | asyncio, db | passed | 0.058 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_multiple_core_payments_with_one_external_id_quarantines` | P0-07 | asyncio, db | passed | 0.053 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_zero_matches_after_window_fails_projection_only_for_invoice_pending` | P0-07 | asyncio, db | passed | 0.069 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_claim_respects_dependencies_and_supersede` | P0-08 | asyncio, db | passed | 0.064 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_lease_expired_mid_claim_requeues_and_reclaims` | P0-08 | asyncio, db | passed | 0.052 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_merchant_sender_copy_recovered_without_dispatch` | P0-08 | asyncio, db | passed | 0.057 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_order_msg_keeps_stable_rumor_id_across_retries` | P0-08 | asyncio, db | passed | 0.058 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_pre_reservation_crash_resume_is_idempotent` | P0-08 | asyncio, db | passed | 0.060 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_relay_cursors_advance_only_after_eose` | P0-08 | asyncio, db | passed | 0.051 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_restart_admitted_not_validated` | P0-08 | asyncio, db | passed | 0.049 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_restart_after_attach_before_enqueue` | P0-08 | asyncio, db | passed | 0.059 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_restart_after_invoice_before_attach` | P0-08 | asyncio, db | passed | 0.057 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_restart_after_reservation_before_invoice_call` | P0-08 | asyncio, db | passed | 0.064 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_restart_between_settlement_and_callback` | P0-08 | asyncio, db | passed | 0.063 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_restart_claimed_not_published` | P0-08 | asyncio, db | passed | 0.059 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_restart_partially_published_retries_only_missing` | P0-08 | asyncio, db | passed | 0.062 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_restart_validated_not_dispatched` | P0-08 | asyncio, db | passed | 0.050 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_zero_positive_oks_backoff_then_failed` | P0-08 | asyncio, db | passed | 0.064 |
| `tests/qualification/test_p0_09_email_persistence.py::test_equality_hashes_are_purpose_separated_and_irreversible` | P0-09 | asyncio, db | passed | 0.051 |
| `tests/qualification/test_p0_09_email_persistence.py::test_malformed_and_noncanonical_tokens_rejected_before_lookup` | P0-09 | asyncio, db | passed | 0.070 |
| `tests/qualification/test_p0_09_email_persistence.py::test_no_plaintext_recipients_or_tokens_in_database` | P0-09 | asyncio, db | passed | 0.080 |
| `tests/qualification/test_p0_09_email_persistence.py::test_opt_out_revokes_consent_and_cancels_queued_customer_rows` | P0-09 | asyncio, db | passed | 0.059 |
| `tests/qualification/test_p0_09_email_persistence.py::test_token_rotation_and_revocation_invalidate_immediately` | P0-09 | asyncio, db | passed | 0.063 |
| `tests/qualification/test_p0_09_email_persistence.py::test_token_survives_idempotency_retention_then_expires` | P0-09 | asyncio, db | passed | 0.059 |
| `tests/qualification/test_p0_09_email_persistence.py::test_two_merchant_recipients_two_rows_delivered_independently` | P0-09 | asyncio, db | passed | 0.066 |
| `tests/qualification/test_p0_10_smtp_boundary.py::test_crash_after_smtp_acceptance_redelivers_on_resume` | P0-10 | asyncio, db | passed | 0.052 |
| `tests/qualification/test_p0_10_smtp_boundary.py::test_customer_rate_limit_waits_rather_than_delivering` | P0-10 | asyncio, db | passed | 0.101 |
| `tests/qualification/test_p0_10_smtp_boundary.py::test_exhausted_attempts_enter_failed_never_sent` | P0-10 | asyncio, db | passed | 0.070 |
| `tests/qualification/test_p0_10_smtp_boundary.py::test_logs_expose_neither_recipients_nor_bearer_links` | P0-10 | asyncio, db | passed | 0.057 |
| `tests/qualification/test_p0_10_smtp_boundary.py::test_merchant_alert_rate_limit_at_60_per_hour` | P0-10 | asyncio, db | passed | 0.163 |
| `tests/qualification/test_p0_10_smtp_boundary.py::test_only_true_enters_sent_false_retries_with_bound` | P0-10 | asyncio, db | passed | 0.062 |
| `tests/qualification/test_p0_10_smtp_boundary.py::test_raised_exception_and_recipient_rejection_surface_identically` | P0-10 | asyncio, db | passed | 0.064 |
| `tests/qualification/test_p0_10_smtp_boundary.py::test_suppressed_rows_never_touch_smtp` | P0-10 | asyncio, db | passed | 0.148 |
| `tests/qualification/test_p0_10_smtp_boundary.py::test_true_enters_sent_with_sent_at` | P0-10 | asyncio, db | passed | 0.054 |

## Failures

None.

## D-16 Disclosure — Subcheck Attribution

P0-02 subchecks are attributed as `sdk-internal` (blocking under D-13/D-16: an SDK-internal regression cannot be waived) or `admission-modeled` (extension-side defense in depth only).

| Test | Subcheck | Attribution |
| --- | --- | --- |
| `tests/qualification/test_p0_02_sdk_security.py::test_auth_flood_bounded_with_signing_paused` | paused-signing-auth-boundedness | sdk-internal |
| `tests/qualification/test_p0_02_sdk_security.py::test_invalid_events_rejected_before_trusted_processing` | invalid-event-rejection | sdk-internal |
| `tests/qualification/test_p0_02_sdk_security.py::test_known_id_repetition_admitted_exactly_once` | known-id-repetition-dedupe | admission-modeled |
| `tests/qualification/test_p0_02_sdk_security.py::test_oversized_nip44_input_rejected_with_bounded_cost` | oversized-nip44-input | sdk-internal |
| `tests/qualification/test_p0_02_sdk_security.py::test_tested_binary_identity_recorded_into_evidence_pins` | tested-binary-recorded | sdk-internal |

