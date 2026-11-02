"""Tests for the image-review skill's detection rules (no OCR or Pillow needed)."""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / ".claude/skills/image-review/scripts/scan_images.py"
spec = importlib.util.spec_from_file_location("scan_images", SCRIPT)
scan_images = importlib.util.module_from_spec(spec)
sys.modules["scan_images"] = scan_images  # dataclasses look the module up while loading
spec.loader.exec_module(scan_images)


def rules(line):
    return [rule for rule, _, _ in scan_images.scan_text(line)]


@pytest.mark.parametrize(
    "line, expected",
    [
        ("akankshal@Akankshas-MacBook-Air interview-prep-agents % pytest", "terminal user@host"),
        ("(.venv) dev@laptop ~/code $", "terminal user@host"),
        ("rootdir: /Users/akankshal/git/interview-prep-agents", "home folder path"),
        ("cd /home/runner-name/work", "home folder path"),
        (r"C:\Users\someone\Desktop", "home folder path"),
        ("Contact: jane.doe@gmail.com", "email address"),
        ("token ghp_" + "a" * 36, "GitHub token"),
        ("github_pat_" + "B" * 30, "GitHub token"),
        ("OPENAI_API_KEY=sk-proj-" + "x" * 24, "API key"),
        ("aws AKIAABCDEFGHIJKLMNOP", "AWS access key"),
        ("-----BEGIN OPENSSH PRIVATE KEY-----", "private key"),
        ("ssh to 192.168.1.20", "IP address"),
    ],
)
def test_detects_personal_data_and_secrets(line, expected):
    assert expected in rules(line)


@pytest.mark.parametrize(
    "line",
    [
        "platform darwin -- Python 3.11.17, pytest-9.1.1, pluggy-1.7.0",
        "Co-Authored-By: Claude <noreply@anthropic.com>",
        "123+user@users.noreply.github.com",
        "git@github.com",
        "See /Users/Shared/notes",
        "server on 127.0.0.1:8000",
        "Comment /assign on the issue so @maintainer sees it",
        "6 passed in 0.02s",
        "@ee@ S Interview prep agents ~oe@eo",  # OCR noise from macOS window buttons
    ],
)
def test_ignores_safe_text(line):
    assert rules(line) == []


def test_email_is_not_also_reported_as_terminal_prompt():
    assert rules("jane@example.org and bob@corp.io") == ["email address"]


def test_findings_never_show_the_full_value():
    [(_, _, sample)] = scan_images.scan_text("rootdir: /Users/akankshal/git")
    assert "akankshal" not in sample
    assert sample.startswith("/U")


def test_fail_on_threshold(tmp_path, monkeypatch):
    svg = tmp_path / "diagram.svg"
    svg.write_text("<svg><text>build by me@laptop</text></svg>")
    assert scan_images.main([str(svg), "--no-ocr"]) == 1
    assert scan_images.main([str(svg), "--no-ocr", "--fail-on", "never"]) == 0

    clean = tmp_path / "clean.svg"
    clean.write_text("<svg><text>Question Generator</text></svg>")
    assert scan_images.main([str(clean), "--no-ocr"]) == 0
