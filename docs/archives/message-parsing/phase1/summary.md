## Summary

Phase 1 of structured message parsing: replaced `raw_message` string with `MessageArray` segment parsing. New `message_parser.py` converts Text, At/AtAll, Face, Reply, and media segments into LLM-readable text with XML tags and placeholders.

## Deviations from Plan

- `reply_quote_truncate_length` moved from `media.reply_quote_truncate_length` (nested) to top-level in `settings.yaml` and `_SETTINGS_DEFAULTS` — reply truncation is not a media feature.
- `_MEDIA_PLACEHOLDERS` dict retained but lookup changed from `type(seg) in dict` to `isinstance`-based iteration, to stay compatible with `MagicMock(spec=cls)` in tests while keeping the dict as the single source of truth for Phase 2 extension.

## Key Decisions

- `parse_message` is `async` even in Phase 1 (Reply requires an API call); this avoids a breaking signature change in Phase 2.
- `status` is imported inside `_parse_reply` rather than at module level, keeping the module importable without a running NcatBot instance and making it straightforward to patch in tests via `ncatbot.utils.status`.
- `message_handler.py` still uses `e.raw_message` for command detection (`startswith("/")`); only the LLM-bound content goes through the parser.

## Lessons Learned

- **`type(seg) in dict` breaks with `MagicMock(spec=cls)`** — `MagicMock` overrides `__class__` but `type()` still returns `MagicMock`. Use `isinstance` for dispatch when mocking is involved. The fix: iterate `_MEDIA_PLACEHOLDERS.items()` with `isinstance(seg, cls)`.
- **Patching locally-imported names** — `from ncatbot.utils import status` inside a function means the name lives in `ncatbot.utils`, not in `src.core.message_parser`. Patch `ncatbot.utils.status`, not `src.core.message_parser.status`.
- **`MagicMock(spec=cls)` vs `seg.__class__ = cls`** — setting `__class__` makes `isinstance` work correctly, but `type()` still returns `MagicMock`. Relying on `isinstance` throughout is the safe pattern.

## Follow-ups

- Phase 2: media transcription (download → trim → transcribe), `ParsedMessage` dataclass, scheduler awaits media tasks.
- Phase 3: media passthrough via base64 content blocks.
- The 3 pre-existing failures in `test_commands.py` (`test_raw_command_empty_history`, `test_reload_contact`, `test_reload_no_args`) are unrelated to this feature and should be fixed separately.
