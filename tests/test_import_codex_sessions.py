#!/usr/bin/env python3
"""Smoke tests for bin/import_codex_sessions.py.

Plain assert-based — this repo has no test framework dependency.
Run: .venv/bin/python tests/test_import_codex_sessions.py
"""
import json
import sys
import tempfile
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "bin"))
import import_codex_sessions as ics  # noqa: E402


def write_rollout(path: Path, lines: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n")


def test_fully_replayed_session_produces_no_output(tmp_dir: Path) -> None:
    rollout = tmp_dir / "rollout-replay.jsonl"
    write_rollout(rollout, [
        {"timestamp": "2026-08-20T12:00:00.000Z", "type": "session_meta",
         "payload": {"session_id": "replay-session", "cwd": "/Users/jordan/code/weir"}},
        {"timestamp": "2026-08-20T12:00:01.000Z", "type": "event_msg",
         "payload": {"type": "task_started", "turn_id": "external-import-turn-1"}},
        {"timestamp": "2026-08-20T12:00:02.000Z", "type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "replayed question"}]}},
        {"timestamp": "2026-08-20T12:00:03.000Z", "type": "response_item",
         "payload": {"type": "message", "role": "assistant",
                     "content": [{"type": "output_text", "text": "replayed answer"}]}},
        {"timestamp": "2026-08-20T12:00:04.000Z", "type": "event_msg",
         "payload": {"type": "task_complete", "turn_id": "external-import-turn-1"}},
    ])

    ics.SESSIONS_DIR = tmp_dir / "sessions"
    status = ics.process(rollout)

    assert status == "empty", f"expected 'empty', got {status!r}"
    assert not (ics.SESSIONS_DIR / "codex-weir" / "replay-session.jsonl").exists()
    print("PASS: test_fully_replayed_session_produces_no_output")


def test_mixed_session_keeps_only_organic_turn(tmp_dir: Path) -> None:
    rollout = tmp_dir / "rollout-mixed.jsonl"
    write_rollout(rollout, [
        {"timestamp": "2026-08-20T12:00:00.000Z", "type": "session_meta",
         "payload": {"session_id": "mixed-session", "cwd": "/Users/jordan/code/weir"}},
        {"timestamp": "2026-08-20T12:00:01.000Z", "type": "event_msg",
         "payload": {"type": "task_started", "turn_id": "external-import-turn-1"}},
        {"timestamp": "2026-08-20T12:00:02.000Z", "type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "replayed question"}]}},
        {"timestamp": "2026-08-20T12:00:03.000Z", "type": "event_msg",
         "payload": {"type": "task_complete", "turn_id": "external-import-turn-1"}},
        {"timestamp": "2026-08-20T12:01:00.000Z", "type": "event_msg",
         "payload": {"type": "task_started", "turn_id": "01a01ffe-real-turn"}},
        {"timestamp": "2026-08-20T12:01:01.000Z", "type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "a genuinely new question"}]}},
        {"timestamp": "2026-08-20T12:01:02.000Z", "type": "response_item",
         "payload": {"type": "message", "role": "assistant",
                     "content": [{"type": "output_text", "text": "a genuinely new answer"}]}},
        {"timestamp": "2026-08-20T12:01:03.000Z", "type": "event_msg",
         "payload": {"type": "task_complete", "turn_id": "01a01ffe-real-turn"}},
    ])

    ics.SESSIONS_DIR = tmp_dir / "sessions"
    status = ics.process(rollout)

    assert status == "written", f"expected 'written', got {status!r}"
    target = ics.SESSIONS_DIR / "codex-weir" / "mixed-session.jsonl"
    lines = [json.loads(line) for line in target.read_text().splitlines()]
    assert len(lines) == 2, f"expected 2 surviving records, got {len(lines)}"
    assert lines[0]["type"] == "user"
    assert lines[0]["message"]["content"] == "a genuinely new question"
    assert lines[1]["type"] == "assistant"
    assert lines[1]["message"]["content"] == [{"type": "text", "text": "a genuinely new answer"}]
    print("PASS: test_mixed_session_keeps_only_organic_turn")


def test_rerun_is_idempotent(tmp_dir: Path) -> None:
    rollout = tmp_dir / "rollout-idempotent.jsonl"
    write_rollout(rollout, [
        {"timestamp": "2026-08-20T12:00:00.000Z", "type": "session_meta",
         "payload": {"session_id": "idempotent-session", "cwd": "/Users/jordan/code/weir"}},
        {"timestamp": "2026-08-20T12:01:00.000Z", "type": "event_msg",
         "payload": {"type": "task_started", "turn_id": "01a01ffe-real-turn"}},
        {"timestamp": "2026-08-20T12:01:01.000Z", "type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "hello"}]}},
        {"timestamp": "2026-08-20T12:01:03.000Z", "type": "event_msg",
         "payload": {"type": "task_complete", "turn_id": "01a01ffe-real-turn"}},
    ])

    ics.SESSIONS_DIR = tmp_dir / "sessions"
    first = ics.process(rollout)
    second = ics.process(rollout)

    assert first == "written", f"expected 'written', got {first!r}"
    assert second == "unchanged", f"expected 'unchanged', got {second!r}"
    print("PASS: test_rerun_is_idempotent")


def test_no_cwd_falls_back_to_flat_dir(tmp_dir: Path) -> None:
    rollout = tmp_dir / "rollout-no-cwd.jsonl"
    write_rollout(rollout, [
        {"timestamp": "2026-08-20T12:00:00.000Z", "type": "session_meta",
         "payload": {"session_id": "no-cwd-session"}},
        {"timestamp": "2026-08-20T12:01:00.000Z", "type": "event_msg",
         "payload": {"type": "task_started", "turn_id": "01a01ffe-real-turn"}},
        {"timestamp": "2026-08-20T12:01:01.000Z", "type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "hi"}]}},
        {"timestamp": "2026-08-20T12:01:02.000Z", "type": "event_msg",
         "payload": {"type": "task_complete", "turn_id": "01a01ffe-real-turn"}},
    ])

    ics.SESSIONS_DIR = tmp_dir / "sessions"
    status = ics.process(rollout)

    assert status == "written", f"expected 'written', got {status!r}"
    assert (ics.SESSIONS_DIR / "codex" / "no-cwd-session.jsonl").exists()
    print("PASS: test_no_cwd_falls_back_to_flat_dir")


def test_scratch_workspace_falls_back_to_flat_dir(tmp_dir: Path) -> None:
    scratch_cwd = str(Path.home() / "Documents" / "Codex" / "2026-08-20" / "hey-i-asked-you-recently-about")
    rollout = tmp_dir / "rollout-scratch.jsonl"
    write_rollout(rollout, [
        {"timestamp": "2026-08-20T12:00:00.000Z", "type": "session_meta",
         "payload": {"session_id": "scratch-session", "cwd": scratch_cwd}},
        {"timestamp": "2026-08-20T12:01:00.000Z", "type": "event_msg",
         "payload": {"type": "task_started", "turn_id": "01a01ffe-real-turn"}},
        {"timestamp": "2026-08-20T12:01:01.000Z", "type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "hi from a scratch chat"}]}},
        {"timestamp": "2026-08-20T12:01:02.000Z", "type": "event_msg",
         "payload": {"type": "task_complete", "turn_id": "01a01ffe-real-turn"}},
    ])

    ics.SESSIONS_DIR = tmp_dir / "sessions"
    status = ics.process(rollout)

    assert status == "written", f"expected 'written', got {status!r}"
    assert (ics.SESSIONS_DIR / "codex" / "scratch-session.jsonl").exists()
    print("PASS: test_scratch_workspace_falls_back_to_flat_dir")


def test_synthetic_context_boilerplate_is_stripped(tmp_dir: Path) -> None:
    rollout = tmp_dir / "rollout-boilerplate.jsonl"
    boilerplate = (
        "<recommended_plugins>\nHere is a list of plugins.\n</recommended_plugins>\n"
        "<environment_context>\n  <cwd>/some/path</cwd>\n</environment_context>"
    )
    write_rollout(rollout, [
        {"timestamp": "2026-08-20T12:00:00.000Z", "type": "session_meta",
         "payload": {"session_id": "boilerplate-session", "cwd": "/Users/jordan/code/weir"}},
        {"timestamp": "2026-08-20T12:01:00.000Z", "type": "event_msg",
         "payload": {"type": "task_started", "turn_id": "01a01ffe-real-turn"}},
        {"timestamp": "2026-08-20T12:01:01.000Z", "type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": boilerplate}]}},
        {"timestamp": "2026-08-20T12:01:02.000Z", "type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "what's the real question"}]}},
        {"timestamp": "2026-08-20T12:01:03.000Z", "type": "event_msg",
         "payload": {"type": "task_complete", "turn_id": "01a01ffe-real-turn"}},
    ])

    ics.SESSIONS_DIR = tmp_dir / "sessions"
    status = ics.process(rollout)

    assert status == "written", f"expected 'written', got {status!r}"
    target = ics.SESSIONS_DIR / "codex-weir" / "boilerplate-session.jsonl"
    lines = [json.loads(line) for line in target.read_text().splitlines()]
    assert len(lines) == 1, f"expected the pure-boilerplate turn to be dropped, got {len(lines)} record(s)"
    assert lines[0]["message"]["content"] == "what's the real question"
    print("PASS: test_synthetic_context_boilerplate_is_stripped")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for name, test in [
            ("t1", test_fully_replayed_session_produces_no_output),
            ("t2", test_mixed_session_keeps_only_organic_turn),
            ("t3", test_rerun_is_idempotent),
            ("t4", test_no_cwd_falls_back_to_flat_dir),
            ("t5", test_scratch_workspace_falls_back_to_flat_dir),
            ("t6", test_synthetic_context_boilerplate_is_stripped),
        ]:
            case_dir = tmp_dir / name
            case_dir.mkdir()
            test(case_dir)
    print("All tests passed.")


if __name__ == "__main__":
    main()
