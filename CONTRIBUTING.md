# Contributing Guidelines

## Welcome! 🎨

Thank you for your interest in contributing to the Lumira project. This guide will help you get started.

---

## Development Environment Setup

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/YOUR_USERNAME/lumira.git
cd lumira
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
# Install main dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt
```

### 4. Install Pre-commit Hooks

```bash
pip install pre-commit
pre-commit install
```

This will automatically run code formatting and linting before each commit.

---

## Code Standards

### Code Formatting

We use **Black** for code formatting:

```bash
# Format all files
black src/ tests/

# Check without modifying
black --check src/
```

**Black Configuration:**

- Line length: 88 characters
- Python 3.10+ syntax

### Linting

We use **Ruff** for fast linting:

```bash
# Run linter
ruff check src/ tests/

# Auto-fix issues
ruff check --fix src/
```

### Type Hints

Use type hints for all function signatures:

```python
from typing import Optional, List, Dict
from pathlib import Path

def generate_artwork(
    prompt: str,
    style: str,
    size: tuple[int, int] = (512, 512),
    variations: int = 1
) -> List[Dict[str, str]]:
    """
    Generate artwork with specified parameters.

    Args:
        prompt: Text description of desired artwork
        style: LoRA style name to apply
        size: Image dimensions (width, height)
        variations: Number of variations to generate

    Returns:
        List of dictionaries containing artwork metadata
    """
    pass
```

### Docstrings

Use Google-style docstrings:

```python
def curate_artwork(images: List[Image], threshold: float = 70.0) -> List[Image]:
    """
    Curate artwork based on quality metrics.

    Evaluates images using multiple metrics including aesthetic score,
    technical quality, and diversity. Only images scoring above the
    threshold are returned.

    Args:
        images: List of PIL Image objects to evaluate
        threshold: Minimum quality score (0-100) for selection

    Returns:
        Filtered list of images meeting quality threshold

    Raises:
        ValueError: If threshold is outside valid range

    Example:
        >>> images = [load_image(p) for p in image_paths]
        >>> selected = curate_artwork(images, threshold=75.0)
        >>> print(f"Selected {len(selected)} of {len(images)} images")
    """
    if not 0 <= threshold <= 100:
        raise ValueError("Threshold must be between 0 and 100")

    # Implementation...
```

---

## Development Workflow

### 1. Create a Branch

```bash
# Feature branch
git checkout -b feature/add-pexels-support

# Bug fix branch
git checkout -b fix/api-rate-limit-handling

# Documentation branch
git checkout -b docs/update-setup-guide
```

### Branch Naming Conventions

- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `refactor/` - Code refactoring
- `test/` - Test additions/improvements

### 2. Make Changes

- Write clean, readable code
- Follow the style guide
- Add tests for new features
- Update documentation as needed

### 3. Test Your Changes

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/unit/test_inspiration.py

# Run tests matching pattern
pytest -k "test_api"
```

### 4. Commit Changes

```bash
git add .
git commit -m "feat: add Pexels API support"
```

**Commit Message Format:**

```
<type>: <subject>

<body>

<footer>
```

**Types:**

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Test additions or modifications
- `chore`: Maintenance tasks

**Examples:**

```bash
git commit -m "feat: add diversity scoring to curation system"

git commit -m "fix: handle Unsplash API rate limits with exponential backoff"

git commit -m "docs: update training section with LoRA best practices"
```

### 5. Push and Create Pull Request

```bash
git push origin feature/add-pexels-support
```

Then create a Pull Request on GitHub.

---

## Pull Request Guidelines

### PR Checklist

Before submitting a PR:

- [ ] Code follows style guide (Black + Ruff pass)
- [ ] All tests pass (`pytest`)
- [ ] Coverage maintained or improved
- [ ] New features have tests
- [ ] Documentation updated
- [ ] Commit messages follow convention
- [ ] No merge conflicts
- [ ] PR description explains changes

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update
- [ ] Refactoring

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Manual testing performed

## Checklist
- [ ] Code follows style guidelines
- [ ] Tests pass locally
- [ ] Documentation updated
- [ ] No breaking changes (or documented)

## Screenshots (if applicable)
Add screenshots for UI changes
```

---

## Project Structure

Understanding the codebase:

```
lumira/
├── src/
│   ├── inspiration/       # Image sourcing
│   │   ├── __init__.py
│   │   ├── unsplash_client.py
│   │   └── pexels_client.py
│   ├── generation/        # Image generation
│   │   ├── __init__.py
│   │   ├── pipeline.py
│   │   └── prompt_builder.py
│   ├── training/          # LoRA training
│   │   ├── __init__.py
│   │   └── lora_trainer.py
│   ├── curation/          # Quality assessment
│   │   ├── __init__.py
│   │   ├── aesthetic_scorer.py
│   │   └── diversity_scorer.py
│   ├── gallery/           # Portfolio management
│   │   ├── __init__.py
│   │   └── database.py
│   ├── scheduling/        # Automation
│   │   ├── __init__.py
│   │   └── scheduler.py
│   └── main.py           # Entry point
├── tests/                # Test suite
├── config/               # Configuration
├── docs/                 # Documentation
└── requirements.txt
```

---

## Adding New Features

### 1. API Client Example

```python
# src/inspiration/new_api_client.py

from typing import Dict, Optional
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

class NewAPIClient:
    """Client for NewAPI image service."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.newservice.com"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def fetch_random_image(self, query: Optional[str] = None) -> Dict[str, str]:
        """
        Fetch random image from NewAPI.

        Args:
            query: Optional search query

        Returns:
            Dictionary with image URL and metadata

        Raises:
            APIError: If request fails after retries
        """
        # Implementation
        pass
```

### 2. Add Tests

```python
# tests/unit/test_new_api_client.py

import pytest
from unittest.mock import patch
from src.inspiration.new_api_client import NewAPIClient

class TestNewAPIClient:

    @pytest.fixture
    def client(self):
        return NewAPIClient(api_key="test_key")

    def test_fetch_random_image_success(self, client):
        # Test implementation
        pass
```

### 3. Update Documentation

- Add to README.md features list
- Update ARCHITECTURE.md with new component
- Add configuration example to SETUP.md

---

## Code Review Process

### For Contributors

- Be open to feedback
- Respond to review comments promptly
- Make requested changes or discuss alternatives
- Keep PR scope focused

### For Reviewers

Review checklist:

- [ ] Code quality and readability
- [ ] Test coverage
- [ ] Documentation updates
- [ ] Performance considerations
- [ ] Security implications
- [ ] Error handling
- [ ] Breaking changes

**Provide Constructive Feedback:**

✅ Good: "Consider extracting this logic into a separate function for better testability"

❌ Bad: "This code is messy"

---

## Common Tasks

### Running the Application

```bash
# Activate environment
source venv/bin/activate

# Run single generation
python src/main.py --mode manual --prompt "a beautiful landscape"

# Start scheduler
python src/main.py --mode auto

# Train LoRA
python src/train_lora.py --config config/training.yaml
```

### Database Migrations

```python
# src/gallery/migrations/001_add_diversity_score.py

def upgrade(db):
    """Add diversity_score column to artworks table."""
    db.execute("""
        ALTER TABLE artworks
        ADD COLUMN diversity_score REAL DEFAULT 0
    """)

def downgrade(db):
    """Remove diversity_score column."""
    # SQLite doesn't support DROP COLUMN easily
    # Document manual migration steps
    pass
```

### Adding Configuration Options

```yaml
# config/config.example.yaml

new_feature:
  enabled: true
  parameter: value
  options:
    - option1
    - option2
```

Update config loading:

```python
# src/config/loader.py

@dataclass
class NewFeatureConfig:
    enabled: bool
    parameter: str
    options: List[str]

# Add to main config
```

---

## Debugging Tips

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Use IPython for Interactive Testing

```bash
pip install ipython

# Start IPython
ipython

# Import and test
from src.generation.pipeline import GenerationPipeline
pipeline = GenerationPipeline(config)
```

### Profile Performance

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Code to profile
generate_artwork()

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)
```

---

## Getting Help

- **Documentation**: Check README, ARCHITECTURE, and SETUP
- **Issues**: Search existing GitHub issues
- **Discussions**: Use GitHub Discussions for questions
- **Code Review**: Tag maintainers for review help

---

## Recognition

Contributors will be:

- Listed in README.md
- Credited in release notes
- Appreciated in the community! 🎉

---

## Code of Conduct

### Our Pledge

We are committed to providing a welcoming and inclusive environment for all contributors.

### Standards

**Expected Behavior:**

- Be respectful and inclusive
- Welcome newcomers
- Accept constructive criticism
- Focus on what's best for the project

**Unacceptable Behavior:**

- Harassment or discrimination
- Trolling or insulting comments
- Personal or political attacks
- Publishing others' private information

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

## Questions?

If you have questions about contributing, feel free to:

- Open an issue with the `question` label
- Start a discussion on GitHub
- Reach out to maintainers

**Happy Contributing! 🚀**
