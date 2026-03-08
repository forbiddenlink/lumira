# Testing Strategy

## Overview

Comprehensive testing strategy for the Lumira project to ensure reliability, quality, and maintainability.

---

## Testing Philosophy

- **Test Early**: Write tests alongside features
- **Test Often**: Run tests before commits
- **Test Realistically**: Use realistic data and scenarios
- **Test Edge Cases**: Don't just test the happy path

---

## Test Structure

```
tests/
├── unit/                  # Fast, isolated tests
│   ├── test_inspiration.py
│   ├── test_generation.py
│   ├── test_curation.py
│   ├── test_gallery.py
│   └── test_scheduler.py
├── integration/           # Component interaction tests
│   ├── test_pipeline.py
│   ├── test_database.py
│   └── test_api_clients.py
├── e2e/                   # End-to-end tests
│   └── test_full_workflow.py
├── fixtures/              # Test data
│   ├── sample_images/
│   ├── mock_responses/
│   └── test_configs/
└── conftest.py           # Shared fixtures
```

---

## Setup

### Install Test Dependencies

```bash
pip install pytest pytest-cov pytest-mock pytest-asyncio
pip install black ruff  # Linting and formatting
```

### Configuration

```ini
# pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    --verbose
    --cov=src
    --cov-report=html
    --cov-report=term-missing
    --cov-fail-under=70
```

---

## Unit Tests

### Example: Testing Inspiration Engine

```python
# tests/unit/test_inspiration.py
import pytest
from unittest.mock import Mock, patch
from src.inspiration.unsplash_client import UnsplashClient

class TestUnsplashClient:

    @pytest.fixture
    def client(self):
        return UnsplashClient(api_key="test_key")

    def test_fetch_random_image_success(self, client):
        """Test successful image fetch"""
        with patch('requests.get') as mock_get:
            mock_get.return_value.json.return_value = {
                'urls': {'regular': 'https://example.com/image.jpg'},
                'user': {'name': 'Test User'},
                'description': 'Test description'
            }
            mock_get.return_value.status_code = 200

            result = client.fetch_random_image(query="sunset")

            assert result['url'] == 'https://example.com/image.jpg'
            assert result['photographer'] == 'Test User'

    def test_fetch_image_retry_on_failure(self, client):
        """Test retry logic on API failure"""
        with patch('requests.get') as mock_get:
            # First two calls fail, third succeeds
            mock_get.side_effect = [
                Mock(status_code=500),
                Mock(status_code=500),
                Mock(status_code=200, json=lambda: {'urls': {'regular': 'test.jpg'}})
            ]

            result = client.fetch_random_image(query="test")

            assert mock_get.call_count == 3
            assert result['url'] == 'test.jpg'

    def test_fetch_image_rate_limit_handling(self, client):
        """Test rate limit error handling"""
        with patch('requests.get') as mock_get:
            mock_get.return_value.status_code = 429  # Rate limit

            with pytest.raises(RateLimitError):
                client.fetch_random_image(query="test")
```

### Example: Testing Curation System

```python
# tests/unit/test_curation.py
import pytest
import numpy as np
from src.curation.aesthetic_scorer import AestheticScorer

class TestAestheticScorer:

    @pytest.fixture
    def scorer(self):
        return AestheticScorer()

    def test_score_range(self, scorer):
        """Test score is in valid range"""
        mock_image = np.random.rand(512, 512, 3)
        score = scorer.score_image(mock_image)

        assert 0 <= score <= 100

    def test_score_consistency(self, scorer):
        """Test same image gets same score"""
        mock_image = np.random.rand(512, 512, 3)
        score1 = scorer.score_image(mock_image)
        score2 = scorer.score_image(mock_image)

        assert abs(score1 - score2) < 0.01

    def test_batch_scoring(self, scorer):
        """Test batch scoring performance"""
        images = [np.random.rand(512, 512, 3) for _ in range(5)]
        scores = scorer.score_batch(images)

        assert len(scores) == 5
        assert all(0 <= s <= 100 for s in scores)
```

---

## Integration Tests

### Example: Testing Full Pipeline

```python
# tests/integration/test_pipeline.py
import pytest
from src.pipeline import ArtistPipeline
from src.database import Database

class TestArtistPipeline:

    @pytest.fixture
    def db(self, tmp_path):
        """Temporary test database"""
        db_path = tmp_path / "test.db"
        return Database(str(db_path))

    @pytest.fixture
    def pipeline(self, db, tmp_path):
        config = {
            'gallery_path': str(tmp_path / "gallery"),
            'model_id': 'test-model',
            'test_mode': True
        }
        return ArtistPipeline(config, db)

    def test_full_generation_workflow(self, pipeline, db):
        """Test complete artwork generation"""
        result = pipeline.create_artwork(
            theme="test",
            variations=2
        )

        # Check outputs
        assert result['status'] == 'success'
        assert len(result['artworks']) == 2

        # Check database
        artworks = db.get_recent_artworks(limit=2)
        assert len(artworks) == 2

        # Check files exist
        for artwork in artworks:
            assert os.path.exists(artwork['file_path'])

    def test_pipeline_failure_recovery(self, pipeline):
        """Test pipeline handles failures gracefully"""
        with patch('src.generation.pipeline.generate') as mock_gen:
            mock_gen.side_effect = RuntimeError("GPU error")

            result = pipeline.create_artwork(theme="test")

            assert result['status'] == 'failed'
            assert 'error' in result
            # Verify no partial files left behind
```

---

## End-to-End Tests

```python
# tests/e2e/test_full_workflow.py
import pytest
from src.main import AIArtist

class TestFullWorkflow:

    @pytest.fixture
    def artist(self, tmp_path):
        """Initialize Lumira with test config"""
        config_path = tmp_path / "config.yaml"
        # Write test config
        return AIArtist(config_path)

    @pytest.mark.slow
    def test_scheduled_creation(self, artist):
        """Test scheduled artwork creation"""
        # Start scheduler
        artist.start_scheduler()

        # Wait for job execution
        time.sleep(65)  # Wait for 1-minute job

        # Verify artwork created
        gallery = artist.get_gallery()
        assert len(gallery) > 0

        # Stop scheduler
        artist.stop_scheduler()

    @pytest.mark.slow
    @pytest.mark.gpu
    def test_style_training_workflow(self, artist, training_images):
        """Test LoRA training end-to-end"""
        result = artist.train_style(
            name="test_style",
            images=training_images,
            steps=100  # Minimal for testing
        )

        assert result['status'] == 'success'
        assert os.path.exists(result['lora_path'])

        # Test using the trained style
        artwork = artist.create_artwork(style="test_style")
        assert artwork is not None
```

---

## Test Coverage Goals

### Minimum Coverage Targets

```yaml
coverage_targets:
  overall: 70%
  critical_paths:
    - generation_pipeline: 90%
    - database_operations: 85%
    - api_clients: 80%
    - scheduler: 75%
  nice_to_have:
    - utilities: 60%
    - config_loading: 60%
```

### Running Coverage

```bash
# Generate coverage report
pytest --cov=src --cov-report=html

# View report
open htmlcov/index.html

# Check coverage threshold
pytest --cov=src --cov-fail-under=70
```

---

## Quality Metrics Testing

### Testing Curation Quality

```python
# tests/quality/test_curation_metrics.py
import pytest
from src.curation import CurationSystem

class TestCurationQuality:

    def test_diversity_scoring(self):
        """Ensure diverse artworks score higher"""
        curator = CurationSystem()

        # Generate similar images
        similar_images = generate_similar_batch()
        similar_score = curator.diversity_score(similar_images)

        # Generate diverse images
        diverse_images = generate_diverse_batch()
        diverse_score = curator.diversity_score(diverse_images)

        assert diverse_score > similar_score

    def test_quality_consistency(self):
        """Test quality scoring consistency"""
        curator = CurationSystem()

        high_quality = load_test_image("high_quality.png")
        low_quality = load_test_image("low_quality.png")

        hq_score = curator.quality_score(high_quality)
        lq_score = curator.quality_score(low_quality)

        assert hq_score > lq_score + 10  # Significant difference
```

---

## Performance Testing

```python
# tests/performance/test_generation_speed.py
import pytest
import time

class TestPerformanceMetrics:

    @pytest.mark.benchmark
    def test_generation_speed(self, pipeline):
        """Ensure generation completes in reasonable time"""
        start = time.time()

        pipeline.generate_image(
            prompt="test prompt",
            steps=25,
            size=512
        )

        duration = time.time() - start

        # Should complete in under 30 seconds on GPU
        assert duration < 30

    @pytest.mark.benchmark
    def test_curation_speed(self, curator):
        """Test curation scoring performance"""
        images = [generate_test_image() for _ in range(10)]

        start = time.time()
        scores = curator.score_batch(images)
        duration = time.time() - start

        # Should process 10 images in under 5 seconds
        assert duration < 5
```

---

## Testing Best Practices

### 1. Use Fixtures for Common Setup

```python
@pytest.fixture(scope="session")
def test_model():
    """Load model once for all tests"""
    model = load_stable_diffusion_model()
    yield model
    # Cleanup if needed
```

### 2. Mock External Services

```python
@pytest.fixture
def mock_unsplash():
    with patch('src.inspiration.unsplash_client.requests.get') as mock:
        mock.return_value.json.return_value = MOCK_RESPONSE
        yield mock
```

### 3. Parametrize Tests

```python
@pytest.mark.parametrize("size,expected_time", [
    (256, 5),
    (512, 15),
    (1024, 60)
])
def test_generation_time_by_size(size, expected_time):
    # Test generation time scales appropriately
    pass
```

### 4. Tag Tests

```python
@pytest.mark.slow      # Long-running tests
@pytest.mark.gpu       # Requires GPU
@pytest.mark.integration  # Integration test
def test_something():
    pass

# Run specific tags
# pytest -m "not slow"
# pytest -m "gpu"
```

---

## Continuous Integration

### GitHub Actions Example

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        pip install -r requirements-full.txt
        pip install pytest pytest-cov

    - name: Run tests
      run: |
        pytest --cov=src --cov-report=xml

    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

---

## Running Tests

### Quick Test

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_inspiration.py

# Run specific test
pytest tests/unit/test_inspiration.py::TestUnsplashClient::test_fetch_random_image_success
```

### With Coverage

```bash
pytest --cov=src --cov-report=term-missing
```

### Skip Slow Tests

```bash
pytest -m "not slow"
```

### Verbose Output

```bash
pytest -v
```

---

## Test Data Management

### Fixtures Directory

```
tests/fixtures/
├── images/
│   ├── test_512x512.png
│   ├── test_1024x1024.png
│   └── sample_batch/
├── configs/
│   ├── test_config.yaml
│   └── minimal_config.yaml
└── responses/
    ├── unsplash_response.json
    └── pexels_response.json
```

### Loading Test Data

```python
@pytest.fixture
def sample_image():
    path = Path(__file__).parent / "fixtures/images/test_512x512.png"
    return Image.open(path)
```

---

## Debugging Failed Tests

```bash
# Run with print statements visible
pytest -s

# Drop into debugger on failure
pytest --pdb

# Show local variables on failure
pytest -l

# Run last failed tests only
pytest --lf
```

---

## Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.12.1
    hooks:
      - id: black

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.9
    hooks:
      - id: ruff

  - repo: local
    hooks:
      - id: pytest-check
        name: pytest-check
        entry: pytest
        language: system
        pass_filenames: false
        always_run: true
```

Install:

```bash
pip install pre-commit
pre-commit install
```

---

## Testing Checklist

Before committing:

- [ ] All tests pass locally
- [ ] Coverage meets minimum threshold (70%)
- [ ] New features have tests
- [ ] Bug fixes have regression tests
- [ ] No skipped tests without good reason
- [ ] Test data is in fixtures, not hardcoded
- [ ] Mock external services
- [ ] Documentation updated if needed

---

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-cov Plugin](https://pytest-cov.readthedocs.io/)
- [Testing Best Practices](https://docs.python-guide.org/writing/tests/)
