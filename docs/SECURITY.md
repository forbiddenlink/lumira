# Security Guidelines

## Overview

Security best practices for the Lumira project, covering API keys, secrets management, and safe operation.

---

## API Keys & Credentials

### Never Commit Secrets

**❌ NEVER do this:**

```python
# Bad - hardcoded API key
api_key = "sk-abc123xyz789"
```

**✅ Always do this:**

```python
# Good - use environment variables
import os
api_key = os.getenv("UNSPLASH_API_KEY")
```

### Environment Variables

Create `.env` file (excluded from git):

```bash
# .env
UNSPLASH_ACCESS_KEY=your_access_key_here
UNSPLASH_SECRET_KEY=your_secret_key_here
PEXELS_API_KEY=your_pexels_key_here
HUGGINGFACE_TOKEN=your_hf_token_here
```

Load in application:

```python
from dotenv import load_dotenv
import os

load_dotenv()  # Load .env file

unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY")
if not unsplash_key:
    raise ValueError("UNSPLASH_ACCESS_KEY not found in environment")
```

### .gitignore Configuration

Ensure these are in `.gitignore`:

```gitignore
# Secrets
.env
.env.local
.env.*.local
secrets/
*.pem
*.key

# API keys
config/config.yaml  # If contains secrets
api_keys.json

# Credentials
credentials/
tokens/
```

---

## Secrets Management

### Development Environment

Use `python-dotenv`:

```bash
pip install python-dotenv
```

```python
# src/config/secrets.py
from dotenv import load_dotenv
import os
from pathlib import Path

def load_secrets():
    """Load secrets from .env file."""
    env_path = Path(__file__).parent.parent.parent / '.env'
    load_dotenv(env_path)

    return {
        'unsplash': {
            'access_key': os.getenv('UNSPLASH_ACCESS_KEY'),
            'secret_key': os.getenv('UNSPLASH_SECRET_KEY'),
        },
        'pexels': {
            'api_key': os.getenv('PEXELS_API_KEY'),
        }
    }
```

### Production Environment

For production deployments, use:

1. **System Environment Variables**

   ```bash
   export UNSPLASH_ACCESS_KEY="..."
   ```

2. **Secrets Manager** (for cloud deployments)
   - AWS Secrets Manager
   - Azure Key Vault
   - Google Secret Manager
   - HashiCorp Vault

3. **Encrypted Config Files**

   ```bash
   # Encrypt config
   gpg -c config.yaml

   # Decrypt on use
   gpg -d config.yaml.gpg > config.yaml
   ```

---

## API Security

### Rate Limiting

Implement rate limiting to avoid API abuse:

```python
from functools import wraps
import time
from collections import deque

class RateLimiter:
    """Rate limiter using sliding window."""

    def __init__(self, max_calls: int, period: int):
        self.max_calls = max_calls
        self.period = period
        self.calls = deque()

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()

            # Remove old calls
            while self.calls and self.calls[0] < now - self.period:
                self.calls.popleft()

            if len(self.calls) >= self.max_calls:
                sleep_time = self.period - (now - self.calls[0])
                time.sleep(sleep_time)
                return wrapper(*args, **kwargs)

            self.calls.append(now)
            return func(*args, **kwargs)

        return wrapper

# Usage
@RateLimiter(max_calls=50, period=3600)  # 50 calls per hour
def fetch_from_unsplash(query: str):
    # API call
    pass
```

### Request Validation

Validate and sanitize all external inputs:

```python
def validate_prompt(prompt: str) -> str:
    """Validate and sanitize user prompt."""
    # Length check
    if len(prompt) > 500:
        raise ValueError("Prompt too long (max 500 characters)")

    # Remove potential injection attacks
    # (Though SD prompts don't execute code, still good practice)
    dangerous_chars = ['<', '>', '{', '}', '|']
    for char in dangerous_chars:
        if char in prompt:
            prompt = prompt.replace(char, '')

    return prompt.strip()
```

### HTTPS Only

Always use HTTPS for API calls:

```python
import requests

def fetch_image(url: str):
    """Fetch image with security checks."""
    # Ensure HTTPS
    if not url.startswith('https://'):
        raise ValueError("Only HTTPS URLs allowed")

    # Set timeout
    response = requests.get(
        url,
        timeout=30,  # Prevent hanging
        verify=True  # Verify SSL certificates
    )

    return response
```

---

## File System Security

### Safe File Operations

```python
from pathlib import Path
import os

def safe_save_image(image, filename: str, gallery_path: Path):
    """Safely save image with path validation."""
    # Resolve to absolute path
    gallery_path = gallery_path.resolve()

    # Sanitize filename
    filename = os.path.basename(filename)  # Remove path components
    filename = filename.replace('..', '')  # Prevent directory traversal

    # Construct full path
    full_path = gallery_path / filename

    # Ensure path is within gallery
    if not full_path.resolve().is_relative_to(gallery_path):
        raise ValueError("Invalid file path")

    # Save with restricted permissions
    image.save(full_path)
    os.chmod(full_path, 0o644)  # rw-r--r--
```

### Temporary Files

Use `tempfile` for temporary files:

```python
import tempfile
from pathlib import Path

def process_with_temp_file(image):
    """Process image using temporary file."""
    with tempfile.NamedTemporaryFile(suffix='.png', delete=True) as tmp:
        tmp_path = Path(tmp.name)
        image.save(tmp_path)

        # Process...
        result = process_image(tmp_path)

        # File automatically deleted when exiting context
        return result
```

---

## Database Security

### SQL Injection Prevention

Use parameterized queries:

```python
import sqlite3

# ❌ NEVER do this (SQL injection risk)
def get_artwork_bad(title: str):
    query = f"SELECT * FROM artworks WHERE title = '{title}'"
    return db.execute(query)

# ✅ Always use parameters
def get_artwork_safe(title: str):
    query = "SELECT * FROM artworks WHERE title = ?"
    return db.execute(query, (title,))
```

### Database Permissions

```python
import sqlite3
import os

def create_database(db_path: str):
    """Create database with restricted permissions."""
    conn = sqlite3.connect(db_path)

    # Set restrictive permissions
    os.chmod(db_path, 0o600)  # rw-------

    return conn
```

### Sensitive Data

Avoid storing sensitive data in database:

```python
# ❌ Don't store API keys in database
# ✅ Store only non-sensitive metadata
artwork_metadata = {
    'filename': 'artwork_001.png',
    'created_at': datetime.now(),
    'prompt': prompt,
    # API key not stored
}
```

---

## Model Security

### Model Download Verification

```python
from huggingface_hub import hf_hub_download
import hashlib

def download_model_safe(model_id: str, expected_hash: str = None):
    """Download model with optional hash verification."""
    model_path = hf_hub_download(
        repo_id=model_id,
        filename="pytorch_model.bin"
    )

    if expected_hash:
        # Verify file hash
        with open(model_path, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        if file_hash != expected_hash:
            raise ValueError("Model hash mismatch - potential tampering")

    return model_path
```

### Sandboxing (Optional)

For high-security environments:

```python
# Run generation in isolated environment
import subprocess

def generate_sandboxed(prompt: str):
    """Run generation in sandbox."""
    result = subprocess.run(
        ['firejail', '--net=none', 'python', 'generate.py', prompt],
        capture_output=True,
        timeout=300
    )
    return result.stdout
```

---

## Logging Security

### Sanitize Logs

Never log sensitive information:

```python
import logging
import re

def sanitize_for_logging(text: str) -> str:
    """Remove sensitive data before logging."""
    # Remove API keys
    text = re.sub(r'api[_-]?key["\s:=]+[\w-]+', 'api_key=<redacted>', text, flags=re.IGNORECASE)

    # Remove tokens
    text = re.sub(r'token["\s:=]+[\w-]+', 'token=<redacted>', text, flags=re.IGNORECASE)

    # Remove email addresses
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '<email>', text)

    return text

# Use in logging
logger.info(f"Request: {sanitize_for_logging(request_data)}")
```

### Secure Log Storage

```python
import logging
from logging.handlers import RotatingFileHandler
import os

def setup_secure_logging():
    """Configure logging with security considerations."""
    log_file = 'logs/lumira.log'

    # Create logs directory with restricted permissions
    os.makedirs('logs', exist_ok=True)
    os.chmod('logs', 0o700)

    # Rotating file handler
    handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )

    # Set log file permissions
    os.chmod(log_file, 0o600)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[handler]
    )
```

---

## Dependency Security

### Keep Dependencies Updated

```bash
# Check for vulnerabilities
pip install safety
safety check

# Update dependencies
pip install --upgrade -r requirements.txt
```

### Pin Versions

Use specific versions in `requirements.txt`:

```
# Good - specific versions
diffusers==0.25.0
torch==2.1.0

# Avoid - unpinned versions
# diffusers
# torch>=2.0.0
```

### Audit Dependencies

```bash
# Check for known vulnerabilities
pip-audit

# Review dependency tree
pipdeptree
```

---

## Network Security

### Firewall Considerations

If running as service:

```bash
# Allow only necessary ports
# Example: Only allow localhost access
sudo ufw allow from 127.0.0.1 to any port 5000
```

### Disable Unnecessary Services

```python
# Don't expose internal services unnecessarily
# If adding web UI, use authentication
from flask import Flask, request
from functools import wraps

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return 'Authentication required', 401
        return f(*args, **kwargs)
    return decorated

@app.route('/generate')
@require_auth
def generate():
    # Protected endpoint
    pass
```

---

## Incident Response

### If API Keys are Compromised

1. **Immediate Actions:**

   ```bash
   # Revoke compromised keys immediately
   # 1. Go to API provider dashboard
   # 2. Revoke old keys
   # 3. Generate new keys
   # 4. Update .env file
   ```

2. **Audit Usage:**
   - Check API usage logs for unauthorized activity
   - Review recent generations for anomalies
   - Check file system for unauthorized changes

3. **Update All Instances:**

   ```bash
   # Update environment variables
   export UNSPLASH_ACCESS_KEY="new_key"

   # Restart services
   systemctl restart lumira
   ```

### Security Checklist

- [ ] No secrets in code or git history
- [ ] `.env` file in `.gitignore`
- [ ] Using parameterized database queries
- [ ] Rate limiting implemented
- [ ] Input validation on all external data
- [ ] HTTPS for all API calls
- [ ] File paths validated
- [ ] Logs sanitized
- [ ] Dependencies up to date
- [ ] Restrictive file permissions

---

## Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Python Security Best Practices](https://python.readthedocs.io/en/stable/library/security_warnings.html)
- [API Security Checklist](https://github.com/shieldfy/API-Security-Checklist)

---

## Reporting Security Issues

If you discover a security vulnerability:

1. **DO NOT** open a public issue
2. Email security concerns to [maintainer email]
3. Include:
   - Description of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will respond within 48 hours.

---

*Security is everyone's responsibility. Stay vigilant!*
