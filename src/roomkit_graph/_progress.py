"""A run's progress on a terminal, as it happens: ``roomkit_graph.verbose()``.

The engine and the RoomKit handlers log each thing a run does (``_log.py``).
``verbose()`` prints those records as short lines, each prefixed by its graph
and run, so two runs interleaved stay readable::

    [research-crew 3f2a1b9c] ▶ run started
    [research-crew 3f2a1b9c] ▶ research (agent)
    [research-crew 3f2a1b9c]   researcher · Senior research analyst · working…
    [research-crew 3f2a1b9c]   researcher answered · 9.8 s · 512 → 640 tokens
    [research-crew 3f2a1b9c] ✓ research · 9.9 s
"""

from __future__ import annotations

import logging
import sys
import unicodedata
from collections import Counter
from collections.abc import Callable
from typing import Any, TextIO

from roomkit_graph._log import FIELDS

LOGGER = "roomkit_graph"
_EXCERPT = 160

_GREEN, _YELLOW, _RED, _CYAN, _DIM = "32", "33", "31", "36", "2"


def _printable(text: str) -> str:
    """*text* with every control or format character shown escaped (``\\x1b``).

    What a line prints comes from outside — a customer's message, a model's
    answer, an error — and a terminal obeys an escape sequence or a bidi
    override it is written: it could clear the screen or fake a line.
    """
    return "".join(
        c.encode("unicode_escape").decode("ascii") if unicodedata.category(c)[0] == "C" else c
        for c in text
    )


def _excerpt(text: Any) -> str:
    """*text* on one line, cut to ``_EXCERPT`` characters."""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= _EXCERPT else flat[: _EXCERPT - 1] + "…"


def _tokens(fields: dict[str, Any]) -> str:
    tokens_in, tokens_out = fields.get("tokens_in"), fields.get("tokens_out")
    if tokens_in is None and tokens_out is None:
        return ""
    cached = f" ({fields['tokens_cached']:,} from cache)" if fields.get("tokens_cached") else ""
    return f" · {tokens_in or 0:,} → {tokens_out or 0:,} tokens{cached}"


def _tools(fields: dict[str, Any]) -> str:
    counts = Counter(fields.get("tools") or [])
    if not counts:
        return ""
    named = ", ".join(name if n == 1 else f"{name} ×{n}" for name, n in counts.items())
    return f" · tools: {named}"


def _agent_done(f: dict[str, Any]) -> str:
    status = "" if f.get("status") == "completed" else f" · {f.get('status')}"
    return f"  {f['agent']} answered · {f['seconds']:.1f} s{_tokens(f)}{_tools(f)}{status}"


def _agent_start(f: dict[str, Any]) -> str:
    role = f" · {f['role']}" if f.get("role") else ""
    return f"  {f['agent']}{role} · working…"


def _run_done(f: dict[str, Any]) -> str:
    seconds = f" · {f['seconds']:.1f} s" if f.get("seconds") is not None else ""
    return f"✓ run done{seconds} · {f['steps']} steps"


# event → (its line, the colour of the line's first mark)
_LINES: dict[str, tuple[Callable[[dict[str, Any]], str], str | None]] = {
    "run.start": (lambda f: "▶ run started", _CYAN),
    "node.start": (lambda f: f"▶ {f['node']} ({f['type']})", _CYAN),
    "agent.start": (_agent_start, None),
    "agent.prompt": (lambda f: f"  asked: {_excerpt(f['text'])}", _DIM),
    "agent.done": (_agent_done, None),
    "agent.answer": (lambda f: f"  answer: {_excerpt(f['text'])}", _DIM),
    "message.sent": (lambda f: f"  sent into room {f['room']}", None),
    "question.sent": (lambda f: f"  asked in room {f['room']}", None),
    "message.text": (lambda f: f"  text: {_excerpt(f['text'])}", _DIM),
    "node.complete": (lambda f: f"✓ {f['node']} · {f['seconds']:.1f} s", _GREEN),
    "node.wait": (lambda f: f"⏸ {f['node']} · waiting for an answer", _YELLOW),
    "node.resume": (lambda f: f"↻ {f['node']} · answered, the run goes on", _CYAN),
    "node.fail": (lambda f: f"✗ {f['node']} · {f.get('error')}", _RED),
    "run.complete": (_run_done, _GREEN),
}


class _ProgressHandler(logging.Handler):
    """Prints the run records of the ``roomkit_graph`` loggers as progress lines."""

    def __init__(self, stream: TextIO, logger: logging.Logger) -> None:
        super().__init__()
        self._stream = stream
        self._colour = stream.isatty()
        self._logger = logger
        self._previous = (logger.level, logger.propagate)

    def emit(self, record: logging.LogRecord) -> None:
        fields = getattr(record, FIELDS, None)
        if fields is None or fields.get("event") not in _LINES:
            return
        if fields.get("type") == "start":  # "run started" already says it
            return
        render, colour = _LINES[fields["event"]]
        prefix = self._paint(_printable(f"[{fields['graph']} {fields['run']}]"), _DIM)
        try:
            line = self._paint(_printable(render(fields)), colour)
            self._stream.write(f"{prefix} {line}\n")
            self._stream.flush()
        except Exception:  # a display must never break the run it shows
            self.handleError(record)

    def close(self) -> None:
        """Stop printing: detach, and give the logger its level and propagation back."""
        self._logger.removeHandler(self)
        self._logger.setLevel(self._previous[0])
        self._logger.propagate = self._previous[1]
        super().close()

    def _paint(self, text: str, colour: str | None) -> str:
        if not self._colour or colour is None:
            return text
        return f"\033[{colour}m{text}\033[0m"


def verbose(*, content: bool = True, stream: TextIO | None = None) -> logging.Handler:
    """Print every run's progress on *stream* (stderr by default) as it happens.

    Each step, each agent's turn (who, how long, tokens, tools called) and each
    message sent is one line. With *content*, what each agent was asked and
    answered, and the text of each message, are printed too, cut to one line.

    The ``roomkit_graph`` logger then prints here only: it stops propagating,
    so a root handler does not print the same records again. ``close()`` on the
    returned handler stops it and restores the logger. Calling ``verbose()``
    again replaces the previous display.
    """
    logger = logging.getLogger(LOGGER)
    for handler in list(logger.handlers):
        if isinstance(handler, _ProgressHandler):
            handler.close()
    handler = _ProgressHandler(stream or sys.stderr, logger)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if content else logging.INFO)
    logger.propagate = False
    return handler
