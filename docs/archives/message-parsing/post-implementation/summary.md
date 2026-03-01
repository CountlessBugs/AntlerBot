## Summary

Simplified media processing configuration by merging `transcribe` and `passthrough` flags into a single `enabled` switch, with `transcribe_threshold_mb` controlling the processing mode. Added `max_file_size_mb` to skip oversized files entirely.

## Changes

- **Config**: Replaced per-type `transcribe`/`passthrough` booleans with `enabled`. Added media-level `max_file_size_mb` and `transcribe_threshold_mb`.
- **message_parser.py**: Refactored mode selection logic — `enabled` gates processing, `transcribe_threshold_mb` determines passthrough vs transcription. Files exceeding `max_file_size_mb` are skipped with a `skipped="file_too_large"` tag.
- **media_processor.py**: Removed defensive `transcribe`/`passthrough` flag checks (caller now decides mode).
- **Tests**: Updated all settings references, removed tests for removed flags (`test_process_image_disabled`, `test_passthrough_disabled`).

## New Config Model

| Setting | Scope | Effect |
|---------|-------|--------|
| `max_file_size_mb` | media | Skip file entirely if exceeded |
| `transcribe_threshold_mb` | media | ≤ threshold → passthrough, > threshold → transcribe, 0 → always transcribe, unset → always passthrough |
| `enabled` | per-type | Whether to process this media type at all |

## Deviations from Plan

- No separate plan existed; this was an iterative refinement during the media transcription feature branch.

## Key Decisions

- Kept `enabled` as an explicit per-type switch rather than inferring from config presence, for clarity.
- `transcribe_threshold_mb` is media-level (not per-type) to reduce config complexity.
- Unknown file size defaults to transcription when threshold is set (conservative approach).

## Follow-ups

- User's local `settings.yaml` needs manual migration from `transcribe`/`passthrough` to `enabled`.
