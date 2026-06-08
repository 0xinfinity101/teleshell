from dataclasses import dataclass, field
from html import escape

from terminal_screen import MiniTerminalScreen


@dataclass
class TerminalPanel:
    command: str
    cwd: str
    max_lines: int = 16
    max_columns: int = 42
    max_chars: int = 3500
    status: str = ""
    lines: list[str] = field(default_factory=list)
    scroll_offset: int = 0
    screen: MiniTerminalScreen = field(init=False)

    def __post_init__(self):
        self.screen = MiniTerminalScreen(self.max_columns, self.max_lines)

    def set_status(self, status: str):
        self.status = status.strip()

    def append(self, text: str):
        if not text or not text.strip():
            return
        self.screen.feed(text)
        self.lines = self.screen.render_lines()

    def scroll_up(self):
        if not self.lines:
            return
        max_offset = max(0, len(self.lines) - self.max_lines)
        self.scroll_offset = min(max_offset, self.scroll_offset + self.max_lines)

    def scroll_down(self):
        self.scroll_offset = max(0, self.scroll_offset - self.max_lines)

    def render(self) -> str:
        body_lines = self._visible_lines()
        body = "\n".join(self._fit_line(line) for line in body_lines).strip() or "(waiting for output)"
        header = f"teleshell: {self.command}\ncwd: {self.cwd}"
        if self.status:
            header += f"\nstatus: {self.status}"
        rendered = f"{header}\n\n{body}"
        if len(rendered) <= self.max_chars:
            return rendered
        return rendered[-self.max_chars:]

    def render_for_telegram(self) -> str:
        return f"<pre>{escape(self.render())}</pre>"

    def _visible_lines(self) -> list[str]:
        if not self.lines:
            return []
        end = len(self.lines) - self.scroll_offset
        start = max(0, end - self.max_lines)
        return self.lines[start:end]

    def _fit_line(self, line: str) -> str:
        return line[:self.max_columns]
