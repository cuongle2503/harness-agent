"""System prompts for Harness Agent and subagents."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """Load a system prompt by name.

    Args:
        name: Prompt file name without extension (e.g., "main_agent", "coder").

    Returns:
        The prompt text content.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """
    prompt_path = _PROMPTS_DIR / f"{name}.md"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


__all__ = ["load_prompt"]
