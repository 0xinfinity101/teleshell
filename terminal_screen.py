import pyte


class MiniTerminalScreen:
    def __init__(self, columns: int, lines: int, history: int = 200):
        self.columns = columns
        self.lines = lines
        self.screen = pyte.HistoryScreen(columns, lines, history=history)
        self.stream = pyte.Stream(self.screen)

    def feed(self, text: str):
        if not text:
            return
        # Telegram tests and process-end notices often use plain LF, while a
        # PTY usually emits CRLF. Normalize LF so pyte advances to column zero.
        normalized = text.replace("\r\n", "\n").replace("\n", "\r\n")
        self.stream.feed(normalized)

    def render_lines(self) -> list[str]:
        lines = [self._history_row(row) for row in self.screen.history.top]
        lines.extend(row.rstrip() for row in self.screen.display)

        while lines and not lines[-1].strip():
            lines.pop()
        return lines

    def _history_row(self, row: dict[int, object]) -> str:
        cells = [" "] * self.columns
        for column, char in row.items():
            if 0 <= column < self.columns:
                cells[column] = char.data
        return "".join(cells).rstrip()
