"""Prompt processing engine with wildcard support."""

import random
import re
from pathlib import Path

from .logging import get_logger
from .prompt_emphasis import PromptEmphasis
from .prompt_matrix import PromptMatrix

logger = get_logger(__name__)


class PromptEngine:
    """Handles dynamic prompt generation with wildcards and randomization.

    Supports:
    - Choice syntax: {option A|option B|option C}
    - Wildcards: __wildcard_name__ (loads from config/wildcards/wildcard_name.txt)
    - Emphasis syntax: (text:1.5) for weighted importance
    - Prompt matrix: [red|blue] for combinatorial generation
    """

    def __init__(self, wildcards_dir: Path = Path("config/wildcards")) -> None:
        self.wildcards_dir = wildcards_dir
        self.wildcards: dict[str, list[str]] = {}
        self.prompt_emphasis = PromptEmphasis()
        self.prompt_matrix = PromptMatrix()
        self._load_wildcards()

    def reload(self) -> None:
        """Reload all wildcards from disk."""
        self.wildcards.clear()
        self._load_wildcards()

    def _load_wildcards(self) -> None:
        """Load all wildcard files from directory."""
        if not self.wildcards_dir.exists():
            logger.warning("wildcards_dir_not_found", path=str(self.wildcards_dir))
            return

        for file_path in self.wildcards_dir.glob("*.txt"):
            key = f"__{file_path.stem}__"
            try:
                with open(file_path, encoding="utf-8") as f:
                    lines = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.startswith("#")
                    ]
                if lines:
                    self.wildcards[key] = lines
                    logger.debug("wildcard_loaded", key=key, count=len(lines))
            except Exception as e:
                logger.error("wildcard_load_failed", file=file_path.name, error=str(e))

    def _process_choices(self, text: str) -> str:
        """Process {a|b|c} syntax."""

        def replace(match: re.Match[str]) -> str:
            choices = match.group(1).split("|")
            return str(random.choice(choices).strip())

        # Recursively replace choices (in case of nested choices)
        while "{" in text and "}" in text:
            new_text = re.sub(r"\{([^{}]+)\}", replace, text)
            if new_text == text:  # No changes made, break to avoid infinite loop
                break
            text = new_text

        return text

    def _process_wildcards(self, text: str) -> str:
        """Replace __wildcard__ with random line from file."""
        for key, values in self.wildcards.items():
            if key in text:
                # Replace ALL occurrences of this wildcard
                # Use a loop to support multiple distinct random choices for same wildcard
                # e.g. "__color__ and __color__" -> "red and blue"
                while key in text:
                    replacement = random.choice(values)
                    text = text.replace(key, replacement, 1)
        return text

    def process(self, prompt: str, apply_emphasis: bool = False) -> str:
        """Process a prompt with all dynamic features.

        Args:
            prompt: The input prompt to process
            apply_emphasis: If True, process (text:weight) emphasis syntax

        Returns:
            Processed prompt string
        """
        # First process wildcards (which might contain choices)
        prompt = self._process_wildcards(prompt)
        # Then process choices
        prompt = self._process_choices(prompt)

        # Apply emphasis if requested (converts AUTOMATIC1111-style weights to Compel format)
        if apply_emphasis:
            prompt = self.prompt_emphasis.apply_emphasis_to_compel(prompt)

        # Clean up double spaces and commas
        prompt = re.sub(r"\s+", " ", prompt).strip()
        prompt = re.sub(r"\s*,\s*", ", ", prompt)
        prompt = re.sub(r",,+", ",", prompt)

        return prompt

    def process_matrix(self, prompt: str) -> list[str]:
        """Process a prompt matrix to generate all combinations.

        Args:
            prompt: Prompt with [option1|option2] matrix syntax

        Returns:
            List of all prompt combinations

        Example:
            >>> engine = PromptEngine()
            >>> engine.process_matrix("a [red|blue] [cat|dog]")
            ['a red cat', 'a red dog', 'a blue cat', 'a blue dog']
        """
        # Note: PromptMatrix uses {option|option} not [option|option]
        # Convert bracket syntax to curly brace syntax for compatibility
        matrix_prompt = prompt.replace("[", "{").replace("]", "}")

        # Generate all combinations
        combinations = self.prompt_matrix.parse_prompt(matrix_prompt)

        # Process each combination through the normal pipeline
        return [self.process(combo) for combo in combinations]
