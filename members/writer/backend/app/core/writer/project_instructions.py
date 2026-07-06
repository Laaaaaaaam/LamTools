from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PROJECT_INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md", "CONTEXT.md")


@dataclass(frozen=True)
class ProjectInstruction:
    path: Path
    content: str

    def to_prompt_block(self) -> str:
        return f"Instructions from: {self.path}\n{self.content.strip()}"


class ProjectInstructionLoader:
    """Loads stable project instruction files for Writer prompts."""

    def __init__(self, max_chars_per_file: int = 20000):
        self._max_chars_per_file = max_chars_per_file

    def load(self, work_root: str | Path | None) -> list[ProjectInstruction]:
        if not work_root:
            return []
        root = Path(work_root).resolve()
        if not root.exists():
            return []

        for filename in PROJECT_INSTRUCTION_FILES:
            path = root / filename
            if not path.is_file():
                continue
            content = self._read(path)
            if content:
                return [ProjectInstruction(path=path, content=content)]
        return []

    def _read(self, path: Path) -> str:
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

        if len(content) <= self._max_chars_per_file:
            return content
        return (
            content[: self._max_chars_per_file]
            + "\n\n[Instruction file truncated. Read the file directly if exact later sections matter.]"
        )
