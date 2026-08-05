# MIDIWIN runtime observability

MIDIWIN records controller inputs, modifier transitions, mapping decisions,
action dispatches, backend messages, and selected backend results in an
append-only JSONL event ledger.

Default path:

```text
%APPDATA%\MidiWin\events.jsonl
```

Override it for one run:

```powershell
midiwin --event-log C:\Logs\midiwin-events.jsonl --monitor
```

## Status

```powershell
midiwin --json-status
```

The JSON report includes configuration validity, enabled mapping count, runtime
PID, detected device information, event-ledger path and size, and device-query
errors.

## Inspect or reset the ledger

```powershell
midiwin --event-tail 100
midiwin --clear-event-log
```

Every event contains a UTC timestamp, schema version, event kind, and relevant
structured fields. Common password, token, API-key, Bearer, and OpenAI-shaped
secrets are redacted before persistence.

## Mapping decisions

The ledger distinguishes:

- `control_input` — normalized input from X1 or F1;
- `modifier_state` — current Shift/Hotcue layer state;
- `mapping_selected` — mapping and conditions selected for dispatch;
- `mapping_unmatched` — input had no active mapping;
- `action_dispatch` — action chosen and normalized event values;
- `action_log` — human-readable backend action line;
- `action_result` — structured backend success/failure where supported;
- runtime start, stop, claim and release events.

`--monitor` and `--dry-run` retain their existing safety semantics while still
writing evidence. No controller action is executed in those modes.

## Configuration collision checks

Validation rejects two enabled mappings with the same device, control, event
kind, required modifiers, and excluded modifiers. It also rejects mappings
that require and exclude the same modifier. Disabled mappings do not create a
runtime collision.
