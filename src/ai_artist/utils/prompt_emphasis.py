"""
Prompt Emphasis System - inspired by AUTOMATIC1111's weighting syntax.

Allows emphasizing or de-emphasizing parts of prompts using (word:weight) syntax.
Example: "(beautiful:1.5) woman, (ugly:-0.5) background"

This converts to embeddings with adjusted attention weights.
"""

import re

import structlog

logger = structlog.get_logger()


class PromptEmphasis:
    """Handle prompt emphasis with weight adjustments."""

    def __init__(self) -> None:
        # Pattern for (text:weight) or (text) for 1.1x emphasis
        self.weight_pattern = re.compile(r"\(([^:)]+)(?::([+-]?\d*\.?\d+))?\)")
        # Default multiplier for () without explicit weight
        self.default_emphasis = 1.1

    def parse_emphasis(self, prompt: str) -> list[tuple[str, float]]:
        """
        Parse prompt with emphasis syntax into weighted segments.

        Args:
            prompt: Prompt with (text:weight) syntax

        Returns:
            List of (text, weight) tuples

        Example:
            >>> pe = PromptEmphasis()
            >>> pe.parse_emphasis("(beautiful:1.5) woman, (ugly:0.5) background")
            [('beautiful', 1.5), ('woman', 1.0), ('ugly', 0.5), ('background', 1.0)]
        """
        segments = []
        last_end = 0

        for match in self.weight_pattern.finditer(prompt):
            # Add unweighted text before this match
            before = prompt[last_end : match.start()].strip()
            if before:
                segments.append((before, 1.0))

            # Add weighted text
            text = match.group(1).strip()
            weight_str = match.group(2)

            # () without weight means 1.1x emphasis
            weight = float(weight_str) if weight_str else self.default_emphasis

            if text:
                segments.append((text, weight))

            last_end = match.end()

        # Add remaining unweighted text
        remaining = prompt[last_end:].strip()
        if remaining:
            segments.append((remaining, 1.0))

        return segments

    def apply_emphasis_to_compel(self, prompt: str) -> str:
        """
        Convert emphasis syntax to Compel's format.

        Compel uses (text)+ for emphasis and (text)- for de-emphasis.
        We convert our weight syntax to Compel's format.

        Args:
            prompt: Prompt with (text:weight) syntax

        Returns:
            Prompt in Compel format
        """
        segments = self.parse_emphasis(prompt)
        compel_parts = []

        for text, weight in segments:
            # Clean up the text - remove commas that might be part of segments
            text = text.strip(" ,")

            if not text:
                continue

            if weight == 1.0:
                # No emphasis
                compel_parts.append(text)
            elif weight > 1.0:
                # Emphasis - use (text)+ syntax
                # Each + adds ~1.1x, so convert weight to number of +
                plus_count = int((weight - 1.0) / 0.1)
                compel_parts.append(f"({text}){'+' * max(1, plus_count)}")
            else:
                # De-emphasis - use (text)- syntax
                # Each - reduces by ~0.9x
                minus_count = int((1.0 - weight) / 0.1)
                compel_parts.append(f"({text}){'-' * max(1, minus_count)}")

        return ", ".join(compel_parts)

    def validate_syntax(self, prompt: str) -> tuple[bool, str]:
        """
        Validate emphasis syntax.

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check for balanced parentheses
        depth = 0
        for i, char in enumerate(prompt):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth < 0:
                    return False, f"Unmatched ')' at position {i}"

        if depth != 0:
            return False, f"Unmatched '(' - missing {depth} closing parentheses"

        # Check for valid weights
        for match in self.weight_pattern.finditer(prompt):
            weight_str = match.group(2)
            if weight_str:
                try:
                    weight = float(weight_str)
                    if weight < 0:
                        return False, f"Negative weights not allowed: {match.group(0)}"
                    if weight > 2.0:
                        logger.warning(
                            "high_emphasis_weight", weight=weight, text=match.group(1)
                        )
                except ValueError:
                    return False, f"Invalid weight format: {match.group(0)}"

        return True, ""

    def get_effective_weight(self, prompt: str) -> float:
        """
        Calculate the average effective weight of the prompt.

        Useful for understanding overall emphasis level.
        """
        segments = self.parse_emphasis(prompt)

        if not segments:
            return 1.0

        total_weight = sum(weight for _, weight in segments)
        return total_weight / len(segments)

    def normalize_weights(self, prompt: str, target_avg: float = 1.0) -> str:
        """
        Normalize weights so the average is target_avg.

        This prevents extremely emphasized prompts from causing issues.
        """
        segments = self.parse_emphasis(prompt)
        current_avg = self.get_effective_weight(prompt)

        if current_avg == 0 or abs(current_avg - target_avg) < 0.01:
            return prompt

        # Calculate normalization factor
        factor = target_avg / current_avg

        # Apply normalization
        normalized_parts = []
        for text, weight in segments:
            new_weight = weight * factor
            if abs(new_weight - 1.0) < 0.01:
                normalized_parts.append(text)
            else:
                normalized_parts.append(f"({text}:{new_weight:.2f})")

        return ", ".join(normalized_parts)


# Example usage and testing
if __name__ == "__main__":
    pe = PromptEmphasis()

    test_prompts = [
        "(beautiful:1.5) woman, detailed face",
        "(dark moody:1.3) atmosphere, (bright:0.7) highlights",
        "simple prompt without emphasis",
        "(masterpiece) artwork, (amateur:0.5) quality",
    ]

    print("Prompt Emphasis Parser Tests\n")

    for prompt in test_prompts:
        print(f"Original: {prompt}")

        is_valid, error = pe.validate_syntax(prompt)
        if not is_valid:
            print(f"  ERROR: {error}\n")
            continue

        segments = pe.parse_emphasis(prompt)
        print("  Parsed segments:")
        for text, weight in segments:
            print(f"    - '{text}' (weight: {weight})")

        compel_format = pe.apply_emphasis_to_compel(prompt)
        print(f"  Compel format: {compel_format}")

        avg_weight = pe.get_effective_weight(prompt)
        print(f"  Average weight: {avg_weight:.2f}\n")
