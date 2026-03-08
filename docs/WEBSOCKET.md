# 🔌 WebSocket Real-Time Updates - Testing Guide

## Overview

Lumira now supports real-time progress updates via WebSocket! This allows you to track image generation progress as it happens, rather than waiting for completion.

## Features

✅ **Real-time Progress** - See generation progress update step-by-step
✅ **Session-Based** - Track multiple generations simultaneously
✅ **Auto-Reconnect** - Automatically reconnects if connection drops
✅ **Status Updates** - Get notified of completion, errors, and more
✅ **Modern UI** - Beautiful test interface included

## Quick Start

### 1. Start the Web Server

```bash
# Activate your virtual environment
source venv/bin/activate

# Start the server
python -m ai_artist.web.app
```

The server will start on `http://localhost:8000`

### 2. Open the Test Interface

Navigate to: **<http://localhost:8000/test/websocket>**

### 3. Test Generation

1. The WebSocket should auto-connect (green status)
2. Adjust the generation parameters:
   - Prompt: Describe what you want to generate
   - Negative Prompt: What to avoid
   - Inference Steps: 10-100 (more = better quality, slower)
   - Guidance Scale: 1-20 (how closely to follow prompt)
3. Click "Generate Artwork"
4. Watch the progress bar update in real-time!
5. When complete, images will appear below

## API Usage

### Connect to WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onopen = () => {
    console.log('Connected!');
    // Send ping to keep alive
    ws.send(JSON.stringify({ type: 'ping' }));
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Received:', data);
};
```

### Start Generation

```javascript
// POST to /api/generate
const response = await fetch('http://localhost:8000/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        prompt: "A serene mountain landscape at sunset",
        negative_prompt: "blurry, low quality",
        num_inference_steps: 30,
        guidance_scale: 7.5,
        num_images: 1
    })
});

const { session_id } = await response.json();

// Subscribe to updates for this session
ws.send(JSON.stringify({
    type: 'subscribe',
    session_id: session_id
}));
```

### Message Types

#### `generation_progress`

```json
{
    "type": "generation_progress",
    "session_id": "abc-123",
    "step": 15,
    "total_steps": 30,
    "message": "Generating... 50%"
}
```

#### `generation_complete`

```json
{
    "type": "generation_complete",
    "session_id": "abc-123",
    "image_paths": ["/path/to/image1.png"],
    "metadata": {
        "prompt": "A serene mountain landscape",
        "created_at": "2026-01-09T..."
    }
}
```

#### `generation_error`

```json
{
    "type": "generation_error",
    "session_id": "abc-123",
    "error": "Out of memory"
}
```

## Code Integration

### Generator with WebSocket

```python
from ai_artist.core.generator import ArtworkGenerator
from ai_artist.utils.config import load_config

config = load_config()
generator = ArtworkGenerator(
    model_id=config["model"]["base_model"],
    device=config["model"]["device"]
)
generator.load_model()

# Generate with session_id to enable WebSocket updates
images = generator.generate(
    prompt="A beautiful sunset",
    session_id="my-session-123"  # This enables real-time updates
)
```

### Custom WebSocket Handler

```python
from fastapi import WebSocket
from ai_artist.web.websocket import manager

@app.websocket("/my/custom/ws")
async def my_websocket(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # Handle messages
            await manager.broadcast({
                "type": "custom",
                "data": data
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

## Architecture

```
┌─────────────┐     HTTP POST      ┌──────────────┐
│   Client    │ ─────────────────> │  /api/generate│
│  (Browser)  │                    │   FastAPI    │
└─────────────┘                    └──────────────┘
       │                                    │
       │ WebSocket /ws                     │
       │                                    ▼
       │                          ┌──────────────────┐
       │<──────────────────────── │   Generator      │
       │   Progress Updates       │   with callback  │
       │                          └──────────────────┘
       │                                    │
       ▼                                    ▼
┌─────────────┐                    ┌──────────────┐
│  Live UI    │                    │   Gallery    │
│  Updates    │                    │   Storage    │
└─────────────┘                    └──────────────┘
```

## Files Modified

- **src/ai_artist/web/websocket.py** - Connection manager (NEW)
- **src/ai_artist/web/app.py** - WebSocket endpoint & generation API
- **src/ai_artist/core/generator.py** - Progress callback integration
- **src/ai_artist/web/templates/test_websocket.html** - Test UI (NEW)

## Troubleshooting

### WebSocket won't connect

- Check that the server is running on the expected port
- Verify no firewall is blocking WebSocket connections
- Check browser console for errors

### No progress updates

- Ensure you're passing `session_id` to `generator.generate()`
- Check that WebSocket connection is established before starting generation
- Verify the client subscribed to the session

### Progress updates stop mid-generation

- Check for errors in server logs
- Verify the WebSocket connection didn't drop
- Check system resources (GPU memory, RAM)

## Next Steps

🎯 **Modern Web UI** - Build a production-ready interface with Tailwind CSS
🎯 **Multiple Workers** - Support concurrent generation jobs
🎯 **Progress Persistence** - Store progress in database for recovery
🎯 **Gallery Updates** - Push new images to gallery in real-time

## Resources

- [FastAPI WebSockets Docs](https://fastapi.tiangolo.com/advanced/websockets/)
- [WebSocket API (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
- [IMPLEMENTATION_PROGRESS.md](../IMPLEMENTATION_PROGRESS.md) - Full progress report

---

**Questions or Issues?** Check [TROUBLESHOOTING.md](../TROUBLESHOOTING.md) or open an issue on GitHub.
