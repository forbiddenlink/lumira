"""
Prompt Matrix Generator - inspired by AUTOMATIC1111's prompt matrix system.

Generates combinations of prompt variations using {option1|option2} syntax.
Example: "a {red|blue} {cat|dog}" generates 4 combinations.
"""

import re
from itertools import product


class PromptMatrix:
    """Generate prompt combinations from matrix syntax."""

    def __init__(self) -> None:
        # Pattern to match {option1|option2|option3}
        self.pattern = re.compile(r"\{([^}]+)\}")

    def parse_prompt(self, prompt: str) -> list[str]:
        """
        Parse a prompt with matrix syntax and generate all combinations.

        Args:
            prompt: Prompt with {option1|option2} syntax

        Returns:
            List of all possible prompt combinations

        Example:
            >>> pm = PromptMatrix()
            >>> pm.parse_prompt("a {red|blue} {cat|dog}")
            ['a red cat', 'a red dog', 'a blue cat', 'a blue dog']
        """
        # Find all matrix patterns
        matches = list(self.pattern.finditer(prompt))

        if not matches:
            return [prompt]

        # Extract options for each pattern
        option_groups = []
        for match in matches:
            options = [opt.strip() for opt in match.group(1).split("|")]
            option_groups.append(options)

        # Generate all combinations
        all_combinations = list(product(*option_groups))

        # Replace patterns with combinations
        results = []
        for combination in all_combinations:
            result = prompt
            # Replace from right to left to preserve indices
            for i, match in enumerate(reversed(matches)):
                idx = len(matches) - 1 - i
                start, end = match.span()
                result = result[:start] + combination[idx] + result[end:]
            results.append(result)

        return results

    def count_combinations(self, prompt: str) -> int:
        """Count how many combinations a prompt will generate."""
        matches = list(self.pattern.finditer(prompt))

        if not matches:
            return 1

        count = 1
        for match in matches:
            options = match.group(1).split("|")
            count *= len(options)

        return count

    def validate_syntax(self, prompt: str) -> tuple[bool, str]:
        """
        Validate prompt matrix syntax.

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check for unmatched braces
        open_count = prompt.count("{")
        close_count = prompt.count("}")

        if open_count != close_count:
            return False, f"Unmatched braces: {open_count} '{{' vs {close_count} '}}'"

        # Check for nested braces
        depth = 0
        for char in prompt:
            if char == "{":
                depth += 1
                if depth > 1:
                    return False, "Nested braces are not supported"
            elif char == "}":
                depth -= 1
                if depth < 0:
                    return False, "Mismatched braces"

        # Check for empty options
        matches = list(self.pattern.finditer(prompt))
        for match in matches:
            options = [opt.strip() for opt in match.group(1).split("|")]
            if any(not opt for opt in options):
                return False, f"Empty option in {match.group(0)}"
            if len(options) < 2:
                return False, f"Need at least 2 options in {match.group(0)}"

        return True, ""


# Example usage and testing
if __name__ == "__main__":
    pm = PromptMatrix()

    # Test cases
    test_prompts = [
        "a {red|blue} {cat|dog}",
        "portrait of a {young|old} {man|woman} in {renaissance|baroque} style",
        "simple prompt without matrix",
        "{abstract|realistic} art, {vibrant|muted} colors",
    ]

    for prompt in test_prompts:
        print(f"\nPrompt: {prompt}")
        is_valid, error = pm.validate_syntax(prompt)

        if is_valid:
            count = pm.count_combinations(prompt)
            print(f"Valid - will generate {count} combinations:")

            combinations = pm.parse_prompt(prompt)
            for i, combo in enumerate(combinations, 1):
                print(f"  {i}. {combo}")
        else:
            print(f"Invalid: {error}")
