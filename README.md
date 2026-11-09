# CastEd

Local screen streaming tool with a Tkinter GUI controller and a Flask MJPEG streaming server.

## Features

- Tkinter GUI with stream toggle, sound toggle, client monitor, and activity log.
- MJPEG stream served over HTTP via Flask.
- Audio cues on client connect and disconnect.
- Screen capture via `mss` with `PIL.ImageGrab` fallback.

## Requirements

- Python 3.10+
- Linux audio player (`pw-play`, `paplay`, or `aplay`) or Windows

## Setup

1. Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the application:

```bash
python cast_ed.py
```

## Usage

1. Click **START STREAM** in the CastEd GUI to begin broadcasting.
2. Viewers on the same local network can open the displayed URL (e.g., `http://<your-ip>:5000`) in a web browser.
3. Enter a display name to join and watch the stream.
