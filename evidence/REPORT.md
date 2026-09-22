# GammaMarkets Qualification Report

- Generated (UTC): 2026-09-22T20:50:13.751204+00:00
- Verify command: `make verify`
- Profile: Python 3.12.13 (CPython), arm64/darwin, database dialect: sqlite
- Pins: nostr-sdk 0.44.8, LNbits v1.6.2-rc1 at e336fe14b841, NIP-32 namespace `org.gammamarkets.protocol`
- Tested binary: libnostr_sdk_ffi.dylib (sha256 49b779657adfc809..., 4970368 bytes)
- Result: 377/378 passed (0 failed, 0 errors, 1 skipped), exit status 0

Rerun policy: Single run only (D-10 clean-pass policy): the tooling performs one run per verify command and has no retry loop; a rerun does not flip a recorded outcome.

## FX Float-Boundary Measurement (P0-13)

- Measured maximum relative float error: `7.458852468819816e-17`
- Corresponding absolute sat error: `0`
- Worst-case sample: `rng-16=46257.74717567518`

## P0 Coverage Map (P0-01..P0-14)

| P0 | Status | Tests |
| --- | --- | --- |
| P0-01 | pass | 33 |
| P0-02 | pass | 10 |
| P0-03 | pass | 3 |
| P0-04 | pass | 3 |
| P0-05 | pass | 28 |
| P0-06 | pass | 19 |
| P0-07 | pass | 10 |
| P0-08 | pass | 15 |
| P0-09 | pass | 7 |
| P0-10 | pass | 9 |
| P0-11 | pass | 28 |
| P0-12 | pass | 23 |
| P0-13 | pass | 21 |
| P0-14 | pass | 12 |

### Coverage pointers

- **P0-01**: `tests/qualification/test_p0_01_pins.py::test_evidence_pins_block_matches_recorded_values`, `tests/qualification/test_p0_01_pins.py::test_harness_lock_wheel_parity_with_host_lock`, `tests/qualification/test_p0_01_pins.py::test_host_checkout_head_is_pinned_commit`, `tests/qualification/test_p0_01_pins.py::test_host_lock_and_pypi_are_wheels_only`, `tests/qualification/test_p0_01_pins.py::test_installed_nostr_sdk_is_exactly_pinned`, `tests/qualification/test_p0_01_pins.py::test_installed_wheel_matches_machine_platform`, `tests/qualification/test_p0_01_pins.py::test_native_library_hash_recorded_into_evidence_pins`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[0.44.8-nostr-sdk candidate pin]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[5dc79c5-GammaMarkets market-spec pin]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[APPROVED-approval section (D-11)]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[Linux ARM64-blocking platform (ARM64)]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[Linux x86_64-blocking platform (x86_64)]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[PostgreSQL-blocking database]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[Python 3.12 only-Python 3.12-only claim (D-02)]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[SQLite-blocking database]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[a2494f4f81d46684e5814a9bf35e2b1df978f955-Nostr NIPs pin]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[a600c2a7186559b371030fe5fc5585c37b3a0931-release-source revision]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[chacha20poly1305-native Cargo dependency pin]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[e336fe14b841d6f0c940e75b3d343e3ab5cf8433-LNbits commit pin]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[hashed artifacts-D-15 contingency criterion]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[macOS ARM64-advisory smoke profile]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[owner approval-D-15 contingency criterion]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[pinned native revision-D-15 contingency criterion]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[reproducible build-D-15 contingency criterion]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[rust-nostr/nostr-sdk-ffi-release-source repository]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[secp256k1-native Cargo dependency pin]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[uv.lock-lockfile identity]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[v1.6.2-rc1-LNbits tag]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[v2 payload only-NIP-44 v2-only pin]`, `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[wheels only-no-sdist provenance fact]`, `tests/qualification/test_p0_01_pins.py::test_release_source_and_native_cargo_provenance`, `tests/qualification/test_p0_01_pins.py::test_requires_python_is_3_12_only`, `tests/qualification/test_p0_01_pins.py::test_running_interpreter_is_3_12`
- **P0-02**: `tests/qualification/test_p0_02_sdk_security.py::test_auth_flood_bounded_with_signing_paused`, `tests/qualification/test_p0_02_sdk_security.py::test_build_sign_and_verify_event`, `tests/qualification/test_p0_02_sdk_security.py::test_d16_subcheck_attribution_recorded`, `tests/qualification/test_p0_02_sdk_security.py::test_ffi_import_and_keypair_generation`, `tests/qualification/test_p0_02_sdk_security.py::test_invalid_events_rejected_before_trusted_processing`, `tests/qualification/test_p0_02_sdk_security.py::test_known_id_repetition_admitted_exactly_once`, `tests/qualification/test_p0_02_sdk_security.py::test_nip44_encrypt_decrypt_roundtrip`, `tests/qualification/test_p0_02_sdk_security.py::test_oversized_nip44_input_rejected_with_bounded_cost`, `tests/qualification/test_p0_02_sdk_security.py::test_tampered_event_fails_verification`, `tests/qualification/test_p0_02_sdk_security.py::test_tested_binary_identity_recorded_into_evidence_pins`
- **P0-03**: `tests/qualification/test_p0_03_host_contract.py::test_invoice_listener_lifecycle_and_owned_handle_cancellation`, `tests/qualification/test_p0_03_host_contract.py::test_invoice_metadata_persisted_and_exactly_queryable`, `tests/qualification/test_p0_03_host_contract.py::test_no_durable_callback_delivery_across_restart`
- **P0-04**: `tests/qualification/test_p0_04_relay_ack.py::test_external_relay_smoke`, `tests/qualification/test_p0_04_relay_ack.py::test_positive_negative_and_timeout_acks_classified_per_relay`, `tests/qualification/test_p0_04_relay_ack.py::test_targeted_send_never_reaches_unlisted_relay`
- **P0-05**: `tests/qualification/test_p0_05_encrypted_fixtures.py::test_copies_route_only_to_their_partys_relays`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_duplicate_common_tag_rejected`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_golden_recipient_copy_unwraps_to_golden_rumor`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_golden_sender_copy_unwraps_to_golden_rumor`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_golden_wraps_are_independent_copies`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_no_plaintext_or_key_material_in_logs`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_noncanonical_rumor_id_rejected`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_retry_wrap_preserves_rumor_id`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_rumor_seal_pubkey_mismatch_rejected`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_seal_with_nonempty_tags_rejected`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_seeded_generated_mutations_rejected[bit-flipped-signature]`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_seeded_generated_mutations_rejected[duplicate-p-tag]`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_seeded_generated_mutations_rejected[missing-p-tag]`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_seeded_generated_mutations_rejected[noncanonical-outer-id]`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_seeded_generated_mutations_rejected[oversized-content]`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_seeded_generated_mutations_rejected[truncated-content]`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_seeded_generated_mutations_rejected[wrong-outer-kind]`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_signed_rumor_rejected`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_tampered_outer_content_rejected`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_tampered_outer_signature_rejected`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_tampered_seal_content_rejected`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_tampered_seal_signature_rejected`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_valid_wrap_with_undecryptable_content_rejected`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_validate_kind16_tags_counts_on_raw_json`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_wrap_for_other_recipient_rejected`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_wrong_outer_kind_rejected`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_wrong_recipient_key_decrypt_fails`, `tests/qualification/test_p0_05_encrypted_fixtures.py::test_wrong_rumor_kind_rejected`
- **P0-06**: `tests/qualification/test_p0_06_transactions.py::test_adapter_only_transaction_rolls_back_cleanly`, `tests/qualification/test_p0_06_transactions.py::test_adapter_performs_in_transaction_writes_without_host_helpers`, `tests/qualification/test_p0_06_transactions.py::test_concurrent_duplicate_scoped_order_inserts_yield_one_row`, `tests/qualification/test_p0_06_transactions.py::test_dialect_selection_matches_environment`, `tests/qualification/test_p0_06_transactions.py::test_duplicate_scoped_order_insert_conflicts`, `tests/qualification/test_p0_06_transactions.py::test_guard_failure_mid_claim_rolls_back_everything`, `tests/qualification/test_p0_06_transactions.py::test_host_auto_commit_helper_splits_domain_transaction`, `tests/qualification/test_p0_06_transactions.py::test_idempotency_record_scope_conflict`, `tests/qualification/test_p0_06_transactions.py::test_last_unit_concurrency_yields_exactly_one_reservation`, `tests/qualification/test_p0_06_transactions.py::test_lost_cas_rolls_back_the_entire_transaction`, `tests/qualification/test_p0_06_transactions.py::test_order_state_machine_table_exhaustive`, `tests/qualification/test_p0_06_transactions.py::test_orphan_inserts_violate_foreign_keys[inventory_reservations-params0]`, `tests/qualification/test_p0_06_transactions.py::test_orphan_inserts_violate_foreign_keys[inventory_reservations-params1]`, `tests/qualification/test_p0_06_transactions.py::test_orphan_inserts_violate_foreign_keys[order_items-params2]`, `tests/qualification/test_p0_06_transactions.py::test_orphan_inserts_violate_foreign_keys[order_items-params3]`, `tests/qualification/test_p0_06_transactions.py::test_orphan_inserts_violate_foreign_keys[relay_publications-params4]`, `tests/qualification/test_p0_06_transactions.py::test_sorted_id_locking_avoids_deadlock`, `tests/qualification/test_p0_06_transactions.py::test_task_lease_fencing_rejects_stale_writes`, `tests/qualification/test_p0_06_transactions.py::test_winning_cas_leaves_one_held_reservation`
- **P0-07**: `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_during_inflight_invoice_creation[rejected]`, `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_during_inflight_invoice_creation[success]`, `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_during_inflight_invoice_creation[unknown]`, `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_from_awaiting_payment_then_late_settlement`, `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_from_received_never_creates_an_invoice[rejected]`, `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_from_received_never_creates_an_invoice[success]`, `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_from_received_never_creates_an_invoice[unknown]`, `tests/qualification/test_p0_07_cancellation_saga.py::test_creation_unknown_reconciliation_attaches_exactly_one`, `tests/qualification/test_p0_07_cancellation_saga.py::test_multiple_core_payments_with_one_external_id_quarantines`, `tests/qualification/test_p0_07_cancellation_saga.py::test_zero_matches_after_window_fails_projection_only_for_invoice_pending`
- **P0-08**: `tests/qualification/test_p0_08_recovery_closure.py::test_claim_respects_dependencies_and_supersede`, `tests/qualification/test_p0_08_recovery_closure.py::test_lease_expired_mid_claim_requeues_and_reclaims`, `tests/qualification/test_p0_08_recovery_closure.py::test_merchant_sender_copy_recovered_without_dispatch`, `tests/qualification/test_p0_08_recovery_closure.py::test_order_msg_keeps_stable_rumor_id_across_retries`, `tests/qualification/test_p0_08_recovery_closure.py::test_pre_reservation_crash_resume_is_idempotent`, `tests/qualification/test_p0_08_recovery_closure.py::test_relay_cursors_advance_only_after_eose`, `tests/qualification/test_p0_08_recovery_closure.py::test_restart_admitted_not_validated`, `tests/qualification/test_p0_08_recovery_closure.py::test_restart_after_attach_before_enqueue`, `tests/qualification/test_p0_08_recovery_closure.py::test_restart_after_invoice_before_attach`, `tests/qualification/test_p0_08_recovery_closure.py::test_restart_after_reservation_before_invoice_call`, `tests/qualification/test_p0_08_recovery_closure.py::test_restart_between_settlement_and_callback`, `tests/qualification/test_p0_08_recovery_closure.py::test_restart_claimed_not_published`, `tests/qualification/test_p0_08_recovery_closure.py::test_restart_partially_published_retries_only_missing`, `tests/qualification/test_p0_08_recovery_closure.py::test_restart_validated_not_dispatched`, `tests/qualification/test_p0_08_recovery_closure.py::test_zero_positive_oks_backoff_then_failed`
- **P0-09**: `tests/qualification/test_p0_09_email_persistence.py::test_equality_hashes_are_purpose_separated_and_irreversible`, `tests/qualification/test_p0_09_email_persistence.py::test_malformed_and_noncanonical_tokens_rejected_before_lookup`, `tests/qualification/test_p0_09_email_persistence.py::test_no_plaintext_recipients_or_tokens_in_database`, `tests/qualification/test_p0_09_email_persistence.py::test_opt_out_revokes_consent_and_cancels_queued_customer_rows`, `tests/qualification/test_p0_09_email_persistence.py::test_token_rotation_and_revocation_invalidate_immediately`, `tests/qualification/test_p0_09_email_persistence.py::test_token_survives_idempotency_retention_then_expires`, `tests/qualification/test_p0_09_email_persistence.py::test_two_merchant_recipients_two_rows_delivered_independently`
- **P0-10**: `tests/qualification/test_p0_10_smtp_boundary.py::test_crash_after_smtp_acceptance_redelivers_on_resume`, `tests/qualification/test_p0_10_smtp_boundary.py::test_customer_rate_limit_waits_rather_than_delivering`, `tests/qualification/test_p0_10_smtp_boundary.py::test_exhausted_attempts_enter_failed_never_sent`, `tests/qualification/test_p0_10_smtp_boundary.py::test_logs_expose_neither_recipients_nor_bearer_links`, `tests/qualification/test_p0_10_smtp_boundary.py::test_merchant_alert_rate_limit_at_60_per_hour`, `tests/qualification/test_p0_10_smtp_boundary.py::test_only_true_enters_sent_false_retries_with_bound`, `tests/qualification/test_p0_10_smtp_boundary.py::test_raised_exception_and_recipient_rejection_surface_identically`, `tests/qualification/test_p0_10_smtp_boundary.py::test_suppressed_rows_never_touch_smtp`, `tests/qualification/test_p0_10_smtp_boundary.py::test_true_enters_sent_with_sent_at`
- **P0-11**: `tests/qualification/test_p0_11_nip89_route.py::test_foreign_merchant_naddr_rejected`, `tests/qualification/test_p0_11_nip89_route.py::test_golden_naddr_resolves_locally`, `tests/qualification/test_p0_11_nip89_route.py::test_golden_nip89_pair_validates`, `tests/qualification/test_p0_11_nip89_route.py::test_hidden_and_preorder_map_to_quantity_zero`, `tests/qualification/test_p0_11_nip89_route.py::test_invalid_d_naddr_rejected[bad-alphabet]`, `tests/qualification/test_p0_11_nip89_route.py::test_invalid_d_naddr_rejected[too-long]`, `tests/qualification/test_p0_11_nip89_route.py::test_invalid_d_naddr_rejected[too-short]`, `tests/qualification/test_p0_11_nip89_route.py::test_invalid_d_naddr_rejected[uppercase]`, `tests/qualification/test_p0_11_nip89_route.py::test_invalid_product_variants_rejected[invalid_missing_shipping_id.json-product-shipping-missing-id]`, `tests/qualification/test_p0_11_nip89_route.py::test_invalid_product_variants_rejected[invalid_quantity_float.json-product-quantity-not-int-or-null]`, `tests/qualification/test_p0_11_nip89_route.py::test_invalid_product_variants_rejected[invalid_quantity_string.json-product-quantity-not-int-or-null]`, `tests/qualification/test_p0_11_nip89_route.py::test_invalid_product_variants_rejected[invalid_specs_object.json-product-specs-not-pair-array]`, `tests/qualification/test_p0_11_nip89_route.py::test_malformed_naddr_rejected[corrupt-bech32]`, `tests/qualification/test_p0_11_nip89_route.py::test_malformed_naddr_rejected[empty]`, `tests/qualification/test_p0_11_nip89_route.py::test_malformed_naddr_rejected[npub-not-naddr]`, `tests/qualification/test_p0_11_nip89_route.py::test_malformed_naddr_rejected[plain-text]`, `tests/qualification/test_p0_11_nip89_route.py::test_mismatched_currencies_rejected`, `tests/qualification/test_p0_11_nip89_route.py::test_opaque_address_physical_order_shape`, `tests/qualification/test_p0_11_nip89_route.py::test_relay_hint_never_fetched`, `tests/qualification/test_p0_11_nip89_route.py::test_tampered_nip89_pair_rejected[a-tag-not-web]`, `tests/qualification/test_p0_11_nip89_route.py::test_tampered_nip89_pair_rejected[handler-d-equalized]`, `tests/qualification/test_p0_11_nip89_route.py::test_tampered_nip89_pair_rejected[handler-k-tag-wrong]`, `tests/qualification/test_p0_11_nip89_route.py::test_tampered_nip89_pair_rejected[handler-wrong-kind]`, `tests/qualification/test_p0_11_nip89_route.py::test_tampered_nip89_pair_rejected[rec-d-equalized-to-app-id]`, `tests/qualification/test_p0_11_nip89_route.py::test_tampered_nip89_pair_rejected[rec-foreign-author]`, `tests/qualification/test_p0_11_nip89_route.py::test_unmapped_product_naddr_rejected`, `tests/qualification/test_p0_11_nip89_route.py::test_valid_stall_and_product_dtos`, `tests/qualification/test_p0_11_nip89_route.py::test_wrong_kind_naddr_rejected`
- **P0-12**: `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_approved_cookie_same_origin_path_passes`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_audit_rows_redact_secrets_and_pii`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_cookie_only_without_origin_rejected`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_cross_origin_cookie_mutation_rejected`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_id_only_login_method_refused`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_mutation_requires_authenticated_session`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_order_status_audit_capture_redacts_token`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_order_status_requires_x_order_token_header`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_order_status_token_in_path_not_routed`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_order_status_token_in_query_rejected`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_order_status_wrong_token_rejected`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_production_topology_refusal[-1-False-unsupported-dialect:unknown]`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_production_topology_refusal[cockroachdb-1-False-unsupported-dialect:cockroachdb]`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_production_topology_refusal[postgresql-1-True-supported]`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_production_topology_refusal[postgresql-4-True-supported]`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_production_topology_refusal[sqlite-1-True-supported]`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_production_topology_refusal[sqlite-2-False-sqlite-multi-process-refused]`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_production_topology_refusal[sqlite-8-False-sqlite-multi-process-refused]`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_request_header_logging_redacts_order_token`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_sdk_client_cleanup_on_direct_task_cancel`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_startup_registers_only_bounded_tasks`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_stop_hook_cancels_only_owned_handles`, `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_wrong_origin_subdomain_rejected`
- **P0-13**: `tests/qualification/test_p0_13_decimal_fx.py::test_all_providers_failed_rejects_no_provenance`, `tests/qualification/test_p0_13_decimal_fx.py::test_ceiling_applies_per_component_not_on_summed_total`, `tests/qualification/test_p0_13_decimal_fx.py::test_checked_total_sum_and_minimum_one_sat`, `tests/qualification/test_p0_13_decimal_fx.py::test_empty_quote_rejected`, `tests/qualification/test_p0_13_decimal_fx.py::test_failed_nonfinite_nonpositive_providers_filtered`, `tests/qualification/test_p0_13_decimal_fx.py::test_float_boundary_measurement_is_deterministic_and_recorded`, `tests/qualification/test_p0_13_decimal_fx.py::test_fractional_minor_unit_conversion_ceils`, `tests/qualification/test_p0_13_decimal_fx.py::test_invalid_quote_inputs_rejected`, `tests/qualification/test_p0_13_decimal_fx.py::test_mixed_currency_cart_converts_each_line_with_own_quote`, `tests/qualification/test_p0_13_decimal_fx.py::test_mixed_currency_shipping_components`, `tests/qualification/test_p0_13_decimal_fx.py::test_model_never_calls_host_cached_fiat_helper`, `tests/qualification/test_p0_13_decimal_fx.py::test_nonfinite_rate_rejected`, `tests/qualification/test_p0_13_decimal_fx.py::test_order_fx_quotes_persists_decimal_strings`, `tests/qualification/test_p0_13_decimal_fx.py::test_order_fx_quotes_unique_per_currency`, `tests/qualification/test_p0_13_decimal_fx.py::test_provenance_free_quote_rejected`, `tests/qualification/test_p0_13_decimal_fx.py::test_provider_floats_cross_once_via_decimal_str`, `tests/qualification/test_p0_13_decimal_fx.py::test_quote_ttl_is_five_minutes`, `tests/qualification/test_p0_13_decimal_fx.py::test_rejection_leaves_no_reservation_or_stock_or_quote_rows`, `tests/qualification/test_p0_13_decimal_fx.py::test_stale_quote_rejected_at_conversion_edge`, `tests/qualification/test_p0_13_decimal_fx.py::test_valid_quote_then_reservation_flow`, `tests/qualification/test_p0_13_decimal_fx.py::test_zero_and_negative_rate_rejected`
- **P0-14**: `tests/qualification/test_p0_14_contract_closure.py::test_fixture_coverage_for_required_kinds`, `tests/qualification/test_p0_14_contract_closure.py::test_identifier_closure`, `tests/qualification/test_p0_14_contract_closure.py::test_p0_evidence_closure`, `tests/qualification/test_p0_14_contract_closure.py::test_registered_literals_appear_in_spec`, `tests/qualification/test_p0_14_contract_closure.py::test_release_gates_scope_event_kinds`, `tests/qualification/test_p0_14_contract_closure.py::test_routes_match_spec_bidirectional`, `tests/qualification/test_p0_14_contract_closure.py::test_schema_fields_match_registry_bidirectional`, `tests/qualification/test_p0_14_contract_closure.py::test_section4_table_classification_complete`, `tests/qualification/test_p0_14_contract_closure.py::test_state_machines_match_spec_bidirectional`, `tests/qualification/test_p0_14_contract_closure.py::test_state_tables_match_registry`, `tests/qualification/test_p0_14_contract_closure.py::test_topology_refusal_registered`, `tests/qualification/test_p0_14_contract_closure.py::test_transitions_classified_exhaustively`

## Results

| Test | P0 | Markers | Outcome | Duration (s) |
| --- | --- | --- | --- | --- |
| `tests/qualification/test_p0_01_pins.py::test_evidence_pins_block_matches_recorded_values` | P0-01 | fast | passed | 0.128 |
| `tests/qualification/test_p0_01_pins.py::test_harness_lock_wheel_parity_with_host_lock` | P0-01 | fast | passed | 0.047 |
| `tests/qualification/test_p0_01_pins.py::test_host_checkout_head_is_pinned_commit` | P0-01 | fast | passed | 0.079 |
| `tests/qualification/test_p0_01_pins.py::test_host_lock_and_pypi_are_wheels_only` | P0-01 | fast | passed | 0.032 |
| `tests/qualification/test_p0_01_pins.py::test_installed_nostr_sdk_is_exactly_pinned` | P0-01 | fast | passed | 0.001 |
| `tests/qualification/test_p0_01_pins.py::test_installed_wheel_matches_machine_platform` | P0-01 | fast | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_native_library_hash_recorded_into_evidence_pins` | P0-01 | fast | passed | 0.024 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[0.44.8-nostr-sdk candidate pin]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[5dc79c5-GammaMarkets market-spec pin]` | P0-01 | fast, parametrize | passed | 0.001 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[APPROVED-approval section (D-11)]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[Linux ARM64-blocking platform (ARM64)]` | P0-01 | fast, parametrize | passed | 0.000 |
| `tests/qualification/test_p0_01_pins.py::test_pins_md_records_the_pinned_identities[Linux x86_64-blocking platform (x86_64)]` | P0-01 | fast, parametrize | passed | 0.000 |
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
| `tests/qualification/test_p0_02_sdk_security.py::test_auth_flood_bounded_with_signing_paused` | P0-02 | asyncio, sdk | passed | 1.165 |
| `tests/qualification/test_p0_02_sdk_security.py::test_build_sign_and_verify_event` | P0-02 | asyncio, sdk | passed | 0.001 |
| `tests/qualification/test_p0_02_sdk_security.py::test_d16_subcheck_attribution_recorded` | P0-02 | asyncio, sdk | passed | 0.001 |
| `tests/qualification/test_p0_02_sdk_security.py::test_ffi_import_and_keypair_generation` | P0-02 | asyncio, sdk | passed | 0.001 |
| `tests/qualification/test_p0_02_sdk_security.py::test_invalid_events_rejected_before_trusted_processing` | P0-02 | asyncio, sdk | passed | 0.001 |
| `tests/qualification/test_p0_02_sdk_security.py::test_known_id_repetition_admitted_exactly_once` | P0-02 | asyncio, sdk | passed | 0.001 |
| `tests/qualification/test_p0_02_sdk_security.py::test_nip44_encrypt_decrypt_roundtrip` | P0-02 | asyncio, sdk | passed | 0.001 |
| `tests/qualification/test_p0_02_sdk_security.py::test_oversized_nip44_input_rejected_with_bounded_cost` | P0-02 | asyncio, sdk | passed | 2.586 |
| `tests/qualification/test_p0_02_sdk_security.py::test_tampered_event_fails_verification` | P0-02 | asyncio, sdk | passed | 0.001 |
| `tests/qualification/test_p0_02_sdk_security.py::test_tested_binary_identity_recorded_into_evidence_pins` | P0-02 | asyncio, sdk | passed | 0.049 |
| `tests/qualification/test_p0_03_host_contract.py::test_invoice_listener_lifecycle_and_owned_handle_cancellation` | P0-03 | asyncio, host | passed | 2.348 |
| `tests/qualification/test_p0_03_host_contract.py::test_invoice_metadata_persisted_and_exactly_queryable` | P0-03 | asyncio, host | passed | 1.164 |
| `tests/qualification/test_p0_03_host_contract.py::test_no_durable_callback_delivery_across_restart` | P0-03 | asyncio, host | passed | 5.213 |
| `tests/qualification/test_p0_04_relay_ack.py::test_external_relay_smoke` | P0-04 | asyncio, protocol, skipif | skipped | 0.000 |
| `tests/qualification/test_p0_04_relay_ack.py::test_positive_negative_and_timeout_acks_classified_per_relay` | P0-04 | asyncio, protocol | passed | 10.014 |
| `tests/qualification/test_p0_04_relay_ack.py::test_targeted_send_never_reaches_unlisted_relay` | P0-04 | asyncio, protocol | passed | 0.008 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_copies_route_only_to_their_partys_relays` | P0-05 | asyncio, protocol | passed | 0.003 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_duplicate_common_tag_rejected` | P0-05 | asyncio, protocol | passed | 0.003 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_golden_recipient_copy_unwraps_to_golden_rumor` | P0-05 | asyncio, protocol | passed | 0.008 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_golden_sender_copy_unwraps_to_golden_rumor` | P0-05 | asyncio, protocol | passed | 0.003 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_golden_wraps_are_independent_copies` | P0-05 | asyncio, protocol | passed | 0.002 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_no_plaintext_or_key_material_in_logs` | P0-05 | asyncio, protocol | passed | 0.005 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_noncanonical_rumor_id_rejected` | P0-05 | asyncio, protocol | passed | 0.002 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_retry_wrap_preserves_rumor_id` | P0-05 | asyncio, protocol | passed | 0.004 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_rumor_seal_pubkey_mismatch_rejected` | P0-05 | asyncio, protocol | passed | 0.003 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_seal_with_nonempty_tags_rejected` | P0-05 | asyncio, protocol | passed | 0.002 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_seeded_generated_mutations_rejected[bit-flipped-signature]` | P0-05 | asyncio, parametrize, protocol | passed | 0.001 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_seeded_generated_mutations_rejected[duplicate-p-tag]` | P0-05 | asyncio, parametrize, protocol | passed | 0.001 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_seeded_generated_mutations_rejected[missing-p-tag]` | P0-05 | asyncio, parametrize, protocol | passed | 0.001 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_seeded_generated_mutations_rejected[noncanonical-outer-id]` | P0-05 | asyncio, parametrize, protocol | passed | 0.001 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_seeded_generated_mutations_rejected[oversized-content]` | P0-05 | asyncio, parametrize, protocol | passed | 0.002 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_seeded_generated_mutations_rejected[truncated-content]` | P0-05 | asyncio, parametrize, protocol | passed | 0.001 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_seeded_generated_mutations_rejected[wrong-outer-kind]` | P0-05 | asyncio, parametrize, protocol | passed | 0.001 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_signed_rumor_rejected` | P0-05 | asyncio, protocol | passed | 0.002 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_tampered_outer_content_rejected` | P0-05 | asyncio, protocol | passed | 0.001 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_tampered_outer_signature_rejected` | P0-05 | asyncio, protocol | passed | 0.001 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_tampered_seal_content_rejected` | P0-05 | asyncio, protocol | passed | 0.002 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_tampered_seal_signature_rejected` | P0-05 | asyncio, protocol | passed | 0.002 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_valid_wrap_with_undecryptable_content_rejected` | P0-05 | asyncio, protocol | passed | 0.001 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_validate_kind16_tags_counts_on_raw_json` | P0-05 | asyncio, protocol | passed | 0.000 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_wrap_for_other_recipient_rejected` | P0-05 | asyncio, protocol | passed | 0.001 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_wrong_outer_kind_rejected` | P0-05 | asyncio, protocol | passed | 0.001 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_wrong_recipient_key_decrypt_fails` | P0-05 | asyncio, protocol | passed | 0.001 |
| `tests/qualification/test_p0_05_encrypted_fixtures.py::test_wrong_rumor_kind_rejected` | P0-05 | asyncio, protocol | passed | 0.002 |
| `tests/qualification/test_p0_06_transactions.py::test_adapter_only_transaction_rolls_back_cleanly` | P0-06 | asyncio, db | passed | 0.014 |
| `tests/qualification/test_p0_06_transactions.py::test_adapter_performs_in_transaction_writes_without_host_helpers` | P0-06 | asyncio, db | passed | 0.014 |
| `tests/qualification/test_p0_06_transactions.py::test_concurrent_duplicate_scoped_order_inserts_yield_one_row` | P0-06 | asyncio, db | passed | 0.012 |
| `tests/qualification/test_p0_06_transactions.py::test_dialect_selection_matches_environment` | P0-06 | db | passed | 0.000 |
| `tests/qualification/test_p0_06_transactions.py::test_duplicate_scoped_order_insert_conflicts` | P0-06 | asyncio, db | passed | 0.012 |
| `tests/qualification/test_p0_06_transactions.py::test_guard_failure_mid_claim_rolls_back_everything` | P0-06 | asyncio, db | passed | 0.024 |
| `tests/qualification/test_p0_06_transactions.py::test_host_auto_commit_helper_splits_domain_transaction` | P0-06 | asyncio, db | passed | 0.014 |
| `tests/qualification/test_p0_06_transactions.py::test_idempotency_record_scope_conflict` | P0-06 | asyncio, db | passed | 0.013 |
| `tests/qualification/test_p0_06_transactions.py::test_last_unit_concurrency_yields_exactly_one_reservation` | P0-06 | asyncio, db | passed | 0.044 |
| `tests/qualification/test_p0_06_transactions.py::test_lost_cas_rolls_back_the_entire_transaction` | P0-06 | asyncio, db | passed | 0.014 |
| `tests/qualification/test_p0_06_transactions.py::test_order_state_machine_table_exhaustive` | P0-06 | asyncio, db | passed | 0.187 |
| `tests/qualification/test_p0_06_transactions.py::test_orphan_inserts_violate_foreign_keys[inventory_reservations-params0]` | P0-06 | asyncio, db, parametrize | passed | 0.013 |
| `tests/qualification/test_p0_06_transactions.py::test_orphan_inserts_violate_foreign_keys[inventory_reservations-params1]` | P0-06 | asyncio, db, parametrize | passed | 0.014 |
| `tests/qualification/test_p0_06_transactions.py::test_orphan_inserts_violate_foreign_keys[order_items-params2]` | P0-06 | asyncio, db, parametrize | passed | 0.012 |
| `tests/qualification/test_p0_06_transactions.py::test_orphan_inserts_violate_foreign_keys[order_items-params3]` | P0-06 | asyncio, db, parametrize | passed | 0.013 |
| `tests/qualification/test_p0_06_transactions.py::test_orphan_inserts_violate_foreign_keys[relay_publications-params4]` | P0-06 | asyncio, db, parametrize | passed | 0.016 |
| `tests/qualification/test_p0_06_transactions.py::test_sorted_id_locking_avoids_deadlock` | P0-06 | asyncio, db | passed | 0.386 |
| `tests/qualification/test_p0_06_transactions.py::test_task_lease_fencing_rejects_stale_writes` | P0-06 | asyncio, db | passed | 0.017 |
| `tests/qualification/test_p0_06_transactions.py::test_winning_cas_leaves_one_held_reservation` | P0-06 | asyncio, db | passed | 0.016 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_during_inflight_invoice_creation[rejected]` | P0-07 | asyncio, db, parametrize | passed | 0.019 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_during_inflight_invoice_creation[success]` | P0-07 | asyncio, db, parametrize | passed | 0.021 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_during_inflight_invoice_creation[unknown]` | P0-07 | asyncio, db, parametrize | passed | 0.018 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_from_awaiting_payment_then_late_settlement` | P0-07 | asyncio, db | passed | 0.025 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_from_received_never_creates_an_invoice[rejected]` | P0-07 | asyncio, db, parametrize | passed | 0.019 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_from_received_never_creates_an_invoice[success]` | P0-07 | asyncio, db, parametrize | passed | 0.016 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_cancel_from_received_never_creates_an_invoice[unknown]` | P0-07 | asyncio, db, parametrize | passed | 0.016 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_creation_unknown_reconciliation_attaches_exactly_one` | P0-07 | asyncio, db | passed | 0.023 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_multiple_core_payments_with_one_external_id_quarantines` | P0-07 | asyncio, db | passed | 0.020 |
| `tests/qualification/test_p0_07_cancellation_saga.py::test_zero_matches_after_window_fails_projection_only_for_invoice_pending` | P0-07 | asyncio, db | passed | 0.029 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_claim_respects_dependencies_and_supersede` | P0-08 | asyncio, db | passed | 0.026 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_lease_expired_mid_claim_requeues_and_reclaims` | P0-08 | asyncio, db | passed | 0.016 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_merchant_sender_copy_recovered_without_dispatch` | P0-08 | asyncio, db | passed | 0.019 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_order_msg_keeps_stable_rumor_id_across_retries` | P0-08 | asyncio, db | passed | 0.022 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_pre_reservation_crash_resume_is_idempotent` | P0-08 | asyncio, db | passed | 0.023 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_relay_cursors_advance_only_after_eose` | P0-08 | asyncio, db | passed | 0.016 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_restart_admitted_not_validated` | P0-08 | asyncio, db | passed | 0.017 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_restart_after_attach_before_enqueue` | P0-08 | asyncio, db | passed | 0.021 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_restart_after_invoice_before_attach` | P0-08 | asyncio, db | passed | 0.020 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_restart_after_reservation_before_invoice_call` | P0-08 | asyncio, db | passed | 0.021 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_restart_between_settlement_and_callback` | P0-08 | asyncio, db | passed | 0.025 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_restart_claimed_not_published` | P0-08 | asyncio, db | passed | 0.025 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_restart_partially_published_retries_only_missing` | P0-08 | asyncio, db | passed | 0.023 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_restart_validated_not_dispatched` | P0-08 | asyncio, db | passed | 0.016 |
| `tests/qualification/test_p0_08_recovery_closure.py::test_zero_positive_oks_backoff_then_failed` | P0-08 | asyncio, db | passed | 0.027 |
| `tests/qualification/test_p0_09_email_persistence.py::test_equality_hashes_are_purpose_separated_and_irreversible` | P0-09 | asyncio, db | passed | 0.013 |
| `tests/qualification/test_p0_09_email_persistence.py::test_malformed_and_noncanonical_tokens_rejected_before_lookup` | P0-09 | asyncio, db | passed | 0.012 |
| `tests/qualification/test_p0_09_email_persistence.py::test_no_plaintext_recipients_or_tokens_in_database` | P0-09 | asyncio, db | passed | 0.024 |
| `tests/qualification/test_p0_09_email_persistence.py::test_opt_out_revokes_consent_and_cancels_queued_customer_rows` | P0-09 | asyncio, db | passed | 0.018 |
| `tests/qualification/test_p0_09_email_persistence.py::test_token_rotation_and_revocation_invalidate_immediately` | P0-09 | asyncio, db | passed | 0.016 |
| `tests/qualification/test_p0_09_email_persistence.py::test_token_survives_idempotency_retention_then_expires` | P0-09 | asyncio, db | passed | 0.019 |
| `tests/qualification/test_p0_09_email_persistence.py::test_two_merchant_recipients_two_rows_delivered_independently` | P0-09 | asyncio, db | passed | 0.027 |
| `tests/qualification/test_p0_10_smtp_boundary.py::test_crash_after_smtp_acceptance_redelivers_on_resume` | P0-10 | asyncio, db | passed | 0.023 |
| `tests/qualification/test_p0_10_smtp_boundary.py::test_customer_rate_limit_waits_rather_than_delivering` | P0-10 | asyncio, db | passed | 0.050 |
| `tests/qualification/test_p0_10_smtp_boundary.py::test_exhausted_attempts_enter_failed_never_sent` | P0-10 | asyncio, db | passed | 0.030 |
| `tests/qualification/test_p0_10_smtp_boundary.py::test_logs_expose_neither_recipients_nor_bearer_links` | P0-10 | asyncio, db | passed | 0.023 |
| `tests/qualification/test_p0_10_smtp_boundary.py::test_merchant_alert_rate_limit_at_60_per_hour` | P0-10 | asyncio, db | passed | 0.164 |
| `tests/qualification/test_p0_10_smtp_boundary.py::test_only_true_enters_sent_false_retries_with_bound` | P0-10 | asyncio, db | passed | 0.019 |
| `tests/qualification/test_p0_10_smtp_boundary.py::test_raised_exception_and_recipient_rejection_surface_identically` | P0-10 | asyncio, db | passed | 0.024 |
| `tests/qualification/test_p0_10_smtp_boundary.py::test_suppressed_rows_never_touch_smtp` | P0-10 | asyncio, db | passed | 0.039 |
| `tests/qualification/test_p0_10_smtp_boundary.py::test_true_enters_sent_with_sent_at` | P0-10 | asyncio, db | passed | 0.017 |
| `tests/qualification/test_p0_11_nip89_route.py::test_foreign_merchant_naddr_rejected` | P0-11 | protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_golden_naddr_resolves_locally` | P0-11 | protocol | passed | 0.001 |
| `tests/qualification/test_p0_11_nip89_route.py::test_golden_nip89_pair_validates` | P0-11 | protocol | passed | 0.001 |
| `tests/qualification/test_p0_11_nip89_route.py::test_hidden_and_preorder_map_to_quantity_zero` | P0-11 | protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_invalid_d_naddr_rejected[bad-alphabet]` | P0-11 | parametrize, protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_invalid_d_naddr_rejected[too-long]` | P0-11 | parametrize, protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_invalid_d_naddr_rejected[too-short]` | P0-11 | parametrize, protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_invalid_d_naddr_rejected[uppercase]` | P0-11 | parametrize, protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_invalid_product_variants_rejected[invalid_missing_shipping_id.json-product-shipping-missing-id]` | P0-11 | parametrize, protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_invalid_product_variants_rejected[invalid_quantity_float.json-product-quantity-not-int-or-null]` | P0-11 | parametrize, protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_invalid_product_variants_rejected[invalid_quantity_string.json-product-quantity-not-int-or-null]` | P0-11 | parametrize, protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_invalid_product_variants_rejected[invalid_specs_object.json-product-specs-not-pair-array]` | P0-11 | parametrize, protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_malformed_naddr_rejected[corrupt-bech32]` | P0-11 | parametrize, protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_malformed_naddr_rejected[empty]` | P0-11 | parametrize, protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_malformed_naddr_rejected[npub-not-naddr]` | P0-11 | parametrize, protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_malformed_naddr_rejected[plain-text]` | P0-11 | parametrize, protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_mismatched_currencies_rejected` | P0-11 | protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_opaque_address_physical_order_shape` | P0-11 | protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_relay_hint_never_fetched` | P0-11 | asyncio, protocol | passed | 0.001 |
| `tests/qualification/test_p0_11_nip89_route.py::test_tampered_nip89_pair_rejected[a-tag-not-web]` | P0-11 | parametrize, protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_tampered_nip89_pair_rejected[handler-d-equalized]` | P0-11 | parametrize, protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_tampered_nip89_pair_rejected[handler-k-tag-wrong]` | P0-11 | parametrize, protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_tampered_nip89_pair_rejected[handler-wrong-kind]` | P0-11 | parametrize, protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_tampered_nip89_pair_rejected[rec-d-equalized-to-app-id]` | P0-11 | parametrize, protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_tampered_nip89_pair_rejected[rec-foreign-author]` | P0-11 | parametrize, protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_unmapped_product_naddr_rejected` | P0-11 | protocol | passed | 0.000 |
| `tests/qualification/test_p0_11_nip89_route.py::test_valid_stall_and_product_dtos` | P0-11 | protocol | passed | 0.001 |
| `tests/qualification/test_p0_11_nip89_route.py::test_wrong_kind_naddr_rejected` | P0-11 | protocol | passed | 0.000 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_approved_cookie_same_origin_path_passes` | P0-12 | asyncio, host | passed | 0.220 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_audit_rows_redact_secrets_and_pii` | P0-12 | asyncio, host | passed | 0.000 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_cookie_only_without_origin_rejected` | P0-12 | asyncio, host | passed | 0.229 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_cross_origin_cookie_mutation_rejected` | P0-12 | asyncio, host | passed | 0.220 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_id_only_login_method_refused` | P0-12 | asyncio, host | passed | 0.654 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_mutation_requires_authenticated_session` | P0-12 | asyncio, host | passed | 0.002 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_order_status_audit_capture_redacts_token` | P0-12 | asyncio, host | passed | 0.001 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_order_status_requires_x_order_token_header` | P0-12 | asyncio, host | passed | 0.001 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_order_status_token_in_path_not_routed` | P0-12 | asyncio, host | passed | 0.002 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_order_status_token_in_query_rejected` | P0-12 | asyncio, host | passed | 0.001 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_order_status_wrong_token_rejected` | P0-12 | asyncio, host | passed | 0.001 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_production_topology_refusal[-1-False-unsupported-dialect:unknown]` | P0-12 | asyncio, host, parametrize | passed | 0.104 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_production_topology_refusal[cockroachdb-1-False-unsupported-dialect:cockroachdb]` | P0-12 | asyncio, host, parametrize | passed | 0.001 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_production_topology_refusal[postgresql-1-True-supported]` | P0-12 | asyncio, host, parametrize | passed | 0.001 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_production_topology_refusal[postgresql-4-True-supported]` | P0-12 | asyncio, host, parametrize | passed | 0.001 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_production_topology_refusal[sqlite-1-True-supported]` | P0-12 | asyncio, host, parametrize | passed | 0.001 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_production_topology_refusal[sqlite-2-False-sqlite-multi-process-refused]` | P0-12 | asyncio, host, parametrize | passed | 0.001 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_production_topology_refusal[sqlite-8-False-sqlite-multi-process-refused]` | P0-12 | asyncio, host, parametrize | passed | 0.001 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_request_header_logging_redacts_order_token` | P0-12 | asyncio, host | passed | 0.000 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_sdk_client_cleanup_on_direct_task_cancel` | P0-12 | asyncio, host | passed | 0.160 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_startup_registers_only_bounded_tasks` | P0-12 | asyncio, host | passed | 0.051 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_stop_hook_cancels_only_owned_handles` | P0-12 | asyncio, host | passed | 0.103 |
| `tests/qualification/test_p0_12_auth_privacy_lifecycle.py::test_wrong_origin_subdomain_rejected` | P0-12 | asyncio, host | passed | 0.232 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_all_providers_failed_rejects_no_provenance` | P0-13 | db | passed | 0.001 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_ceiling_applies_per_component_not_on_summed_total` | P0-13 | db | passed | 0.000 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_checked_total_sum_and_minimum_one_sat` | P0-13 | db | passed | 0.001 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_empty_quote_rejected` | P0-13 | db | passed | 0.001 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_failed_nonfinite_nonpositive_providers_filtered` | P0-13 | db | passed | 0.001 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_float_boundary_measurement_is_deterministic_and_recorded` | P0-13 | db | passed | 0.001 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_fractional_minor_unit_conversion_ceils` | P0-13 | db | passed | 0.000 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_invalid_quote_inputs_rejected` | P0-13 | db | passed | 0.001 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_mixed_currency_cart_converts_each_line_with_own_quote` | P0-13 | db | passed | 0.000 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_mixed_currency_shipping_components` | P0-13 | db | passed | 0.000 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_model_never_calls_host_cached_fiat_helper` | P0-13 | db | passed | 0.012 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_nonfinite_rate_rejected` | P0-13 | db | passed | 0.001 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_order_fx_quotes_persists_decimal_strings` | P0-13 | asyncio, db | passed | 0.022 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_order_fx_quotes_unique_per_currency` | P0-13 | asyncio, db | passed | 0.016 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_provenance_free_quote_rejected` | P0-13 | db | passed | 0.000 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_provider_floats_cross_once_via_decimal_str` | P0-13 | db | passed | 0.001 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_quote_ttl_is_five_minutes` | P0-13 | db | passed | 0.001 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_rejection_leaves_no_reservation_or_stock_or_quote_rows` | P0-13 | asyncio, db | passed | 0.014 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_stale_quote_rejected_at_conversion_edge` | P0-13 | db | passed | 0.000 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_valid_quote_then_reservation_flow` | P0-13 | asyncio, db | passed | 0.014 |
| `tests/qualification/test_p0_13_decimal_fx.py::test_zero_and_negative_rate_rejected` | P0-13 | db | passed | 0.001 |
| `tests/qualification/test_p0_14_contract_closure.py::test_fixture_coverage_for_required_kinds` | P0-14 | protocol | passed | 0.001 |
| `tests/qualification/test_p0_14_contract_closure.py::test_identifier_closure` | P0-14 | protocol | passed | 0.010 |
| `tests/qualification/test_p0_14_contract_closure.py::test_p0_evidence_closure` | P0-14 | protocol | passed | 0.001 |
| `tests/qualification/test_p0_14_contract_closure.py::test_registered_literals_appear_in_spec` | P0-14 | protocol | passed | 0.000 |
| `tests/qualification/test_p0_14_contract_closure.py::test_release_gates_scope_event_kinds` | P0-14 | protocol | passed | 0.000 |
| `tests/qualification/test_p0_14_contract_closure.py::test_routes_match_spec_bidirectional` | P0-14 | protocol | passed | 0.000 |
| `tests/qualification/test_p0_14_contract_closure.py::test_schema_fields_match_registry_bidirectional` | P0-14 | protocol | passed | 0.005 |
| `tests/qualification/test_p0_14_contract_closure.py::test_section4_table_classification_complete` | P0-14 | protocol | passed | 0.001 |
| `tests/qualification/test_p0_14_contract_closure.py::test_state_machines_match_spec_bidirectional` | P0-14 | protocol | passed | 0.001 |
| `tests/qualification/test_p0_14_contract_closure.py::test_state_tables_match_registry` | P0-14 | protocol | passed | 0.000 |
| `tests/qualification/test_p0_14_contract_closure.py::test_topology_refusal_registered` | P0-14 | protocol | passed | 0.000 |
| `tests/qualification/test_p0_14_contract_closure.py::test_transitions_classified_exhaustively` | P0-14 | protocol | passed | 0.000 |
| `tests/runtime/test_catalog_api.py::test_catalog_crud` | - | asyncio, runtime | passed | 1.371 |
| `tests/runtime/test_catalog_api.py::test_collection_zero_members_no_intent` | - | asyncio, runtime | passed | 0.016 |
| `tests/runtime/test_catalog_api.py::test_delete_reference_report_and_strip` | - | asyncio, runtime | passed | 0.024 |
| `tests/runtime/test_catalog_api.py::test_draft_produces_no_intent` | - | asyncio, runtime | passed | 0.022 |
| `tests/runtime/test_catalog_api.py::test_dry_run_deterministic` | - | asyncio, runtime | passed | 0.026 |
| `tests/runtime/test_catalog_api.py::test_membership_enqueues_collection_and_product_dep` | - | asyncio, runtime | passed | 0.024 |
| `tests/runtime/test_catalog_api.py::test_owner_scoping` | - | asyncio, runtime | passed | 0.554 |
| `tests/runtime/test_catalog_api.py::test_product_crud_and_outbox_intent` | - | asyncio, runtime | passed | 0.024 |
| `tests/runtime/test_catalog_api.py::test_product_delete_enqueues_tombstone` | - | asyncio, runtime | passed | 0.020 |
| `tests/runtime/test_catalog_api.py::test_product_validation_bounds` | - | asyncio, runtime | passed | 0.090 |
| `tests/runtime/test_catalog_api.py::test_published_at_preserved_across_edits` | - | asyncio, runtime | passed | 0.037 |
| `tests/runtime/test_catalog_api.py::test_shipping_validation` | - | asyncio, runtime | passed | 0.046 |
| `tests/runtime/test_catalog_api.py::test_variation_rules` | - | asyncio, runtime | passed | 0.082 |
| `tests/runtime/test_catalog_events.py::test_collection_event` | - | asyncio, runtime | passed | 0.001 |
| `tests/runtime/test_catalog_events.py::test_identity_and_handler_events_have_no_labels` | - | asyncio, runtime | passed | 0.001 |
| `tests/runtime/test_catalog_events.py::test_nip15_currency_mismatch_is_error` | - | asyncio, runtime | passed | 0.001 |
| `tests/runtime/test_catalog_events.py::test_nip15_hidden_and_digital` | - | asyncio, runtime | passed | 0.001 |
| `tests/runtime/test_catalog_events.py::test_nip15_projection` | - | asyncio, runtime | passed | 0.001 |
| `tests/runtime/test_catalog_events.py::test_nip15_variation_id_composition_and_fallback` | - | asyncio, runtime | passed | 0.001 |
| `tests/runtime/test_catalog_events.py::test_outbox_dependency_edges` | - | asyncio, runtime | passed | 0.008 |
| `tests/runtime/test_catalog_events.py::test_outbox_enqueue_and_supersession` | - | asyncio, runtime | passed | 0.061 |
| `tests/runtime/test_catalog_events.py::test_product_event_deterministic` | - | asyncio, runtime | passed | 0.001 |
| `tests/runtime/test_catalog_events.py::test_product_event_recurring_and_sold` | - | asyncio, runtime | passed | 0.001 |
| `tests/runtime/test_catalog_events.py::test_product_event_required_tags` | - | asyncio, runtime | passed | 0.001 |
| `tests/runtime/test_catalog_events.py::test_product_event_unlimited_stock_omits_stock_tag` | - | asyncio, runtime | passed | 0.001 |
| `tests/runtime/test_catalog_events.py::test_product_event_variation_single_parent_a` | - | asyncio, runtime | passed | 0.001 |
| `tests/runtime/test_catalog_events.py::test_shipping_event` | - | asyncio, runtime | passed | 0.001 |
| `tests/runtime/test_catalog_events.py::test_tombstone_descriptor` | - | asyncio, runtime | passed | 0.001 |
| `tests/runtime/test_checkout.py::test_fresh_checkout_creates_order` | - | asyncio, runtime | passed | 0.026 |
| `tests/runtime/test_checkout.py::test_fx_usd_conversion` | - | asyncio, runtime | passed | 0.024 |
| `tests/runtime/test_checkout.py::test_idempotency_crash_resume` | - | asyncio, runtime | passed | 0.029 |
| `tests/runtime/test_checkout.py::test_idempotency_replay_and_conflict` | - | asyncio, runtime | passed | 0.030 |
| `tests/runtime/test_checkout.py::test_intake_rejects_bad_items` | - | asyncio, runtime | passed | 1.356 |
| `tests/runtime/test_checkout.py::test_intake_rejects_unpurchasable` | - | asyncio, runtime | passed | 0.014 |
| `tests/runtime/test_checkout.py::test_missing_fx_rejected` | - | asyncio, runtime | passed | 0.111 |
| `tests/runtime/test_checkout.py::test_oversell_rejected` | - | asyncio, runtime | passed | 0.014 |
| `tests/runtime/test_crypto_keystore.py::test_envelope_prefix_ambiguity_blocked` | - | runtime | passed | 0.000 |
| `tests/runtime/test_crypto_keystore.py::test_envelope_rejects_wrong_aad_parts` | - | runtime | passed | 0.001 |
| `tests/runtime/test_crypto_keystore.py::test_envelope_roundtrip_and_layout` | - | runtime | passed | 0.000 |
| `tests/runtime/test_crypto_keystore.py::test_envelope_version_absent_from_keyring` | - | runtime | passed | 0.000 |
| `tests/runtime/test_crypto_keystore.py::test_hmac_index_normalization` | - | runtime | passed | 0.000 |
| `tests/runtime/test_crypto_keystore.py::test_hmac_index_purpose_separation` | - | runtime | passed | 0.000 |
| `tests/runtime/test_crypto_keystore.py::test_imported_nsec_never_stored_plaintext` | - | asyncio, runtime | passed | 0.004 |
| `tests/runtime/test_crypto_keystore.py::test_keyring_validation_via_env` | - | runtime | passed | 0.001 |
| `tests/runtime/test_crypto_keystore.py::test_keystore_backup_restore_drill` | - | asyncio, runtime | passed | 0.010 |
| `tests/runtime/test_crypto_keystore.py::test_keystore_generate_sign_roundtrip` | - | asyncio, runtime | passed | 0.120 |
| `tests/runtime/test_crypto_keystore.py::test_keystore_import_validates_nsec` | - | asyncio, runtime | passed | 0.002 |
| `tests/runtime/test_crypto_keystore.py::test_keystore_release_gated_methods` | - | asyncio, runtime | passed | 0.000 |
| `tests/runtime/test_crypto_keystore.py::test_keystore_rewrap_resume_drill` | - | asyncio, runtime | passed | 0.023 |
| `tests/runtime/test_crypto_keystore.py::test_keystore_rewrap_rotation_drill` | - | asyncio, runtime | passed | 0.010 |
| `tests/runtime/test_crypto_keystore.py::test_public_base_url_must_be_canonical_https` | - | runtime | passed | 0.000 |
| `tests/runtime/test_crypto_keystore.py::test_public_token_rejects_noncanonical` | - | runtime | passed | 0.000 |
| `tests/runtime/test_crypto_keystore.py::test_public_token_roundtrip` | - | runtime | passed | 0.000 |
| `tests/runtime/test_crypto_keystore.py::test_relay_url_validation` | - | runtime | passed | 0.000 |
| `tests/runtime/test_crypto_keystore.py::test_start_hook_fails_before_activation` | - | runtime | passed | 0.000 |
| `tests/runtime/test_db.py::test_commit_persists` | - | asyncio, runtime | passed | 0.017 |
| `tests/runtime/test_db.py::test_concurrent_writers_serialize` | - | asyncio, runtime | passed | 0.122 |
| `tests/runtime/test_db.py::test_fencing_update_inside_tx` | - | asyncio, runtime | passed | 0.003 |
| `tests/runtime/test_db.py::test_fk_enforced_inside_tx` | - | asyncio, runtime | passed | 0.001 |
| `tests/runtime/test_db.py::test_rollback_discards` | - | asyncio, runtime | passed | 0.002 |
| `tests/runtime/test_email_queue.py::test_claim_token_fencing` | - | asyncio, runtime | passed | 0.027 |
| `tests/runtime/test_email_queue.py::test_consent_revocation_suppresses` | - | asyncio, runtime | passed | 0.033 |
| `tests/runtime/test_email_queue.py::test_enqueue_dedupes` | - | asyncio, runtime | passed | 1.296 |
| `tests/runtime/test_email_queue.py::test_orderless_test_send` | - | asyncio, runtime | passed | 0.018 |
| `tests/runtime/test_email_queue.py::test_send_classification` | - | asyncio, runtime | passed | 0.060 |
| `tests/runtime/test_email_queue.py::test_subject_has_no_pii` | - | asyncio, runtime | passed | 0.102 |
| `tests/runtime/test_email_queue.py::test_suppression_taxonomy` | - | asyncio, runtime | passed | 0.032 |
| `tests/runtime/test_install.py::test_admin_page_renders_template` | - | asyncio, runtime | passed | 0.107 |
| `tests/runtime/test_install.py::test_admin_page_requires_auth` | - | asyncio, runtime | passed | 0.002 |
| `tests/runtime/test_install.py::test_deactivation_404s_routes` | - | asyncio, runtime | passed | 0.048 |
| `tests/runtime/test_install.py::test_discovered_and_registered` | - | asyncio, runtime | passed | 1.283 |
| `tests/runtime/test_install.py::test_m001_tables_created` | - | asyncio, runtime | passed | 0.002 |
| `tests/runtime/test_install.py::test_modeled_columns_match_registry` | - | asyncio, runtime | passed | 0.020 |
| `tests/runtime/test_install.py::test_reactivation_reruns_start_hook` | - | asyncio, runtime | passed | 0.103 |
| `tests/runtime/test_install.py::test_static_probe_mounted` | - | asyncio, runtime | passed | 0.004 |
| `tests/runtime/test_merchant_api.py::test_audit_posture_qualified_and_flagged` | - | asyncio, runtime | passed | 0.114 |
| `tests/runtime/test_merchant_api.py::test_bearer_mutation_passes_without_origin` | - | asyncio, runtime | passed | 0.013 |
| `tests/runtime/test_merchant_api.py::test_cookie_mutation_requires_origin_and_csrf` | - | asyncio, runtime | passed | 0.017 |
| `tests/runtime/test_merchant_api.py::test_cookie_with_forged_bearer_still_enforces_origin` | - | asyncio, runtime | passed | 0.009 |
| `tests/runtime/test_merchant_api.py::test_current_merchant_projection` | - | asyncio, runtime | passed | 0.007 |
| `tests/runtime/test_merchant_api.py::test_deactivation_enqueues_tombstones` | - | asyncio, runtime | passed | 0.019 |
| `tests/runtime/test_merchant_api.py::test_duplicate_merchant_rejected` | - | asyncio, runtime | passed | 0.006 |
| `tests/runtime/test_merchant_api.py::test_foreign_merchant_is_404` | - | asyncio, runtime | passed | 0.005 |
| `tests/runtime/test_merchant_api.py::test_idempotency_key_accepted_and_shape_validated` | - | asyncio, runtime | passed | 0.017 |
| `tests/runtime/test_merchant_api.py::test_key_import_replaces_identity` | - | asyncio, runtime | passed | 0.010 |
| `tests/runtime/test_merchant_api.py::test_notification_config` | - | asyncio, runtime | passed | 0.019 |
| `tests/runtime/test_merchant_api.py::test_publish_enqueues_outbox_intents` | - | asyncio, runtime | passed | 0.015 |
| `tests/runtime/test_merchant_api.py::test_relay_config_validation` | - | asyncio, runtime | passed | 0.022 |
| `tests/runtime/test_merchant_api.py::test_safe_get_requires_auth` | - | asyncio, runtime | passed | 1.275 |
| `tests/runtime/test_merchant_api.py::test_user_id_only_mutation_rejected` | - | asyncio, runtime | passed | 0.003 |
| `tests/runtime/test_merchant_api.py::test_wallet_binding_rejects_foreign_wallet` | - | asyncio, runtime | passed | 0.009 |
| `tests/runtime/test_nip89.py::test_invalid_naddr_variants_render_invalid_link` | - | asyncio, runtime | passed | 0.023 |
| `tests/runtime/test_nip89.py::test_public_product_json_contract` | - | asyncio, runtime | passed | 0.043 |
| `tests/runtime/test_nip89.py::test_public_product_page_states` | - | asyncio, runtime | passed | 0.122 |
| `tests/runtime/test_nip89.py::test_rate_limit_enforced_on_public_routes` | - | asyncio, runtime | passed | 0.589 |
| `tests/runtime/test_nip89.py::test_valid_naddr_redirects_to_canonical` | - | asyncio, runtime | passed | 1.336 |
| `tests/runtime/test_order_admin.py::test_admin_idempotency_key_accepted` | - | asyncio, runtime | passed | 0.156 |
| `tests/runtime/test_order_admin.py::test_cancel_releases_stock_once` | - | asyncio, runtime | passed | 0.063 |
| `tests/runtime/test_order_admin.py::test_decrypted_pii_owner_only` | - | asyncio, runtime | passed | 0.563 |
| `tests/runtime/test_order_admin.py::test_events_chronology` | - | asyncio, runtime | passed | 0.058 |
| `tests/runtime/test_order_admin.py::test_exception_refund_attestation` | - | asyncio, runtime | passed | 0.073 |
| `tests/runtime/test_order_admin.py::test_list_and_detail` | - | asyncio, runtime | passed | 1.340 |
| `tests/runtime/test_order_admin.py::test_token_reissue` | - | asyncio, runtime | passed | 0.059 |
| `tests/runtime/test_order_admin.py::test_transition_matrix` | - | asyncio, runtime | passed | 0.079 |
| `tests/runtime/test_order_saga.py::test_amount_and_wallet_mismatch_quarantine` | - | asyncio, runtime | passed | 0.100 |
| `tests/runtime/test_order_saga.py::test_buyer_cancel_before_payment` | - | asyncio, runtime | passed | 0.047 |
| `tests/runtime/test_order_saga.py::test_invoice_creation_unknown_never_duplicates` | - | asyncio, runtime | passed | 0.056 |
| `tests/runtime/test_order_saga.py::test_kill_before_callback_reconcile_confirms` | - | asyncio, runtime | passed | 0.071 |
| `tests/runtime/test_order_saga.py::test_late_settlement_on_expired_order` | - | asyncio, runtime | passed | 0.056 |
| `tests/runtime/test_order_saga.py::test_lease_fencing` | - | asyncio, runtime | passed | 0.106 |
| `tests/runtime/test_order_saga.py::test_reconcile_resumes_received_order` | - | asyncio, runtime | passed | 0.066 |
| `tests/runtime/test_order_saga.py::test_reservation_expiry_releases_once` | - | asyncio, runtime | passed | 0.054 |
| `tests/runtime/test_order_saga.py::test_settlement_confirms_once` | - | asyncio, runtime | passed | 1.309 |
| `tests/runtime/test_order_saga.py::test_settlement_foreign_payment_ignored` | - | asyncio, runtime | passed | 0.046 |
| `tests/runtime/test_outbox.py::test_accepted_targets_are_never_resent` | - | asyncio, runtime | passed | 20.092 |
| `tests/runtime/test_outbox.py::test_dead_relay_isolated_one_failure_never_crashes_batch` | - | asyncio, runtime | passed | 9.039 |
| `tests/runtime/test_outbox.py::test_dependency_gate_blocks_until_published` | - | asyncio, runtime | passed | 0.022 |
| `tests/runtime/test_outbox.py::test_newer_live_revision_supersedes_stale_intent` | - | asyncio, runtime | passed | 0.036 |
| `tests/runtime/test_outbox.py::test_oq6_send_to_dead_relay_is_timeout_not_exception` | - | asyncio, runtime | passed | 0.001 |
| `tests/runtime/test_outbox.py::test_oq6_send_to_unconnected_client_times_out` | - | asyncio, runtime | passed | 0.002 |
| `tests/runtime/test_outbox.py::test_oq6_send_to_unregistered_relay_is_safe` | - | asyncio, runtime | passed | 0.001 |
| `tests/runtime/test_outbox.py::test_publish_accepted_marks_published_and_records_evidence` | - | asyncio, runtime | passed | 0.074 |
| `tests/runtime/test_outbox.py::test_rejected_and_timeout_relays_leave_intent_pending` | - | asyncio, runtime | passed | 10.034 |
| `tests/runtime/test_outbox.py::test_relay_targets_direction_and_defaults` | - | asyncio, runtime | passed | 0.019 |
| `tests/runtime/test_outbox.py::test_retry_intent_resets_failed_and_skips_accepted` | - | asyncio, runtime | passed | 0.018 |
| `tests/runtime/test_outbox.py::test_stale_claim_recovery_requeues_with_evidence` | - | asyncio, runtime | passed | 0.010 |
| `tests/runtime/test_public_contract.py::test_checkout_rate_limits` | - | asyncio, runtime | passed | 0.067 |
| `tests/runtime/test_public_contract.py::test_end_to_end_journey` | - | asyncio, runtime | passed | 0.179 |
| `tests/runtime/test_public_contract.py::test_order_status_exact_field_set` | - | asyncio, runtime | passed | 0.035 |
| `tests/runtime/test_public_contract.py::test_protective_headers_everywhere` | - | asyncio, runtime | passed | 0.016 |
| `tests/runtime/test_public_contract.py::test_route_table_has_no_token_param` | - | asyncio, runtime | passed | 1.419 |
| `tests/runtime/test_public_contract.py::test_token_failures_indistinguishable` | - | asyncio, runtime | passed | 0.014 |
| `tests/runtime/test_public_pages.py::test_collection_and_merchant_pages` | - | asyncio, runtime | passed | 0.096 |
| `tests/runtime/test_public_pages.py::test_compact_fallback_and_gm_public_css` | - | asyncio, runtime | passed | 0.004 |
| `tests/runtime/test_public_pages.py::test_hidden_and_sold_and_preorder_states` | - | asyncio, runtime | passed | 0.129 |
| `tests/runtime/test_public_pages.py::test_not_found_and_invalid_d_tag` | - | asyncio, runtime | passed | 0.014 |
| `tests/runtime/test_public_pages.py::test_order_page_shell` | - | asyncio, runtime | passed | 0.106 |
| `tests/runtime/test_public_pages.py::test_product_page_headers_and_scoping` | - | asyncio, runtime | passed | 1.344 |
| `tests/runtime/test_relay_config_api.py::test_blossom_servers_configurable_with_https_only` | - | asyncio, runtime | passed | 0.040 |
| `tests/runtime/test_relay_config_api.py::test_outbox_listing_and_retry_routes` | - | asyncio, runtime | passed | 0.144 |
| `tests/runtime/test_relay_config_api.py::test_relay_config_accepts_public_inbox_both` | - | asyncio, runtime | passed | 1.294 |
| `tests/runtime/test_relay_config_api.py::test_relay_config_rejects_invalid_and_duplicates` | - | asyncio, runtime | passed | 0.041 |
| `tests/runtime/test_status_api.py::test_checkout_gated_by_readiness` | - | asyncio, runtime | passed | 0.106 |
| `tests/runtime/test_status_api.py::test_checkout_happy_path` | - | asyncio, runtime | passed | 0.055 |
| `tests/runtime/test_status_api.py::test_checkout_requires_idempotency_key` | - | asyncio, runtime | passed | 1.286 |
| `tests/runtime/test_status_api.py::test_email_opt_out` | - | asyncio, runtime | passed | 0.012 |
| `tests/runtime/test_status_api.py::test_order_status_after_confirmation` | - | asyncio, runtime | passed | 0.009 |
| `tests/runtime/test_status_api.py::test_order_status_token_contract` | - | asyncio, runtime | passed | 0.014 |
| `tests/runtime/test_themes.py::test_advanced_token_allowlist` | - | asyncio, runtime | passed | 0.038 |
| `tests/runtime/test_themes.py::test_advanced_tokens_require_opt_in` | - | asyncio, runtime | passed | 0.012 |
| `tests/runtime/test_themes.py::test_brand_basics_bounds` | - | asyncio, runtime | passed | 0.048 |
| `tests/runtime/test_themes.py::test_contrast_gate_blocks_failing_pairs` | - | asyncio, runtime | passed | 0.012 |
| `tests/runtime/test_themes.py::test_invalid_preset_and_layout_rejected` | - | asyncio, runtime | passed | 0.023 |
| `tests/runtime/test_themes.py::test_layout_compact_fallback_in_css` | - | asyncio, runtime | passed | 0.002 |
| `tests/runtime/test_themes.py::test_preset_and_layout_persist` | - | asyncio, runtime | passed | 1.307 |
| `tests/runtime/test_themes.py::test_reset_to_preset_clears_overrides` | - | asyncio, runtime | passed | 0.132 |
| `tests/runtime/test_themes.py::test_theme_reaches_public_page_only` | - | asyncio, runtime | passed | 0.186 |

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

P0-02 SDK security/FFI/crypto status this run: **pass**.

## Platform Claims (D-12)

Blocking claims are Linux x86_64 and Linux ARM64 on SQLite AND PostgreSQL; macOS runs are advisory developer checks only. This report records only what THIS run's profile observed — see the CI artifacts below for the full blocking matrix.

## CI Artifacts

For each blocking profile (Linux x86_64 + SQLite, Linux x86_64 + PostgreSQL, Linux ARM64 + SQLite, Linux ARM64 + PostgreSQL) and the advisory macOS profile, CI uploads: the raw pytest output, the generated `evidence/REPORT.md`, and the canonical `evidence/manifest.json`.

External relay smoke is opt-in only (`GAMMA_QUAL_SMOKE_RELAY`) and is never the authoritative source of a pass.

## Approval Status (D-11)

Evidence record only — **owner approval of `PINS.md` remains explicitly pending** and is required before Phase 2. Nothing in this report constitutes approval.

