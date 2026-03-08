# Railway Admin API Setup

## Setting Up Admin API Key

To use the admin upload endpoints, you need to configure an API key on Railway.

### 1. Set Environment Variable in Railway

Go to your Railway project dashboard:

1. Navigate to your `lumira` service
2. Click on "Variables" tab
3. Add new variable:
   - **Name**: `RAILWAY_API_KEY`
   - **Value**: Generate a secure random key (see below)

### 2. Generate a Secure API Key

```bash
# Using Python
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Or using openssl
openssl rand -base64 32
```

Save this key securely - you'll need it for uploads!

### 3. Configure Web App to Use API Key

The web app needs to validate this key. We need to update the config to read from environment:

**Add to Railway Variables:**

```
RAILWAY_API_KEY=your-generated-key-here
```

The app will automatically use this for authentication on admin endpoints.

### 4. Use the API Key Locally

When uploading from your local machine:

```bash
# Set environment variable
export RAILWAY_API_KEY="your-generated-key-here"

# Run upload script
python scripts/upload_to_railway.py
```

Or pass directly:

```bash
python scripts/upload_to_railway.py --api-key "your-generated-key-here"
```

## Admin Endpoints

With API key configured, you can use:

### Upload Single Image

```bash
curl -X POST https://lumira-production-3084.up.railway.app/api/admin/upload-image \
  -H "X-API-Key: your-api-key-here" \
  -F "image=@path/to/image.png" \
  -F "metadata={\"prompt\":\"Your prompt here\"}"
```

### Upload Batch

```bash
python scripts/upload_to_railway.py --all
```

## Security Notes

- **Keep your API key secret** - don't commit it to git
- API keys are stored in Railway environment variables (not in code)
- Upload endpoints are rate-limited (10/minute for single, 5/minute for batch)
- All uploads validated for file type and size

## Testing

Test that your API key works:

```bash
curl -X GET https://lumira-production-3084.up.railway.app/api/images \
  -H "X-API-Key: your-api-key-here"
```

If configured correctly, you'll get the image list. If not, you'll get a 401/403 error.
