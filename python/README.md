# Instructions

## `encode/encode.py`

A video encoding utility built around FFmpeg, originally created to batch-encode video files and reduce storage requirements for a media server.

Supports individual files and directory-based processing, with configurable encoding quality, output resolution, HDR handling and parallel processing.

### Requirements

- Python 3
- FFmpeg with NVIDIA NVENC support
- Python dependencies: `ffmpeg-python`, `python-dotenv`
- Supporting modules: `mailer.py`, `progress.py`
- NVIDIA GPU with compatible NVENC support

HDR-to-SDR conversion additionally requires FFmpeg's `zscale` and `tonemap` filters.

Email reporting requires SMTP credentials configured in the environment file.

### Configuration

Create an environment file using the provided example and configure the following:

| Variable | Purpose |
|---|---|
| `source_mail` | Sender email address |
| `password` | SMTP password or app password |
| `receiver` | Recipient email address |
| `FFMPEG_BIN` | Path to the FFmpeg executable |

### Usage Examples

```bash
# Encode a single video file
python3 encode.py video.mp4 /path/to/destination

# Encode all videos in a directory
python3 encode.py -d /path/to/source /path/to/destination

# Set maximum video bitrate (kb/s)
python3 encode.py video.mp4 /path/to/destination -b 2000

# Set constant quality
python3 encode.py video.mp4 /path/to/destination --cq 28

# Set output resolution (short side)
python3 encode.py video.mp4 /path/to/destination -r 720

# Enable HDR-to-SDR conversion
python3 encode.py video.mp4 /path/to/destination --hdr2sdr

# Encode directory contents recursively
python3 encode.py -d source destination -R

# Encode multiple files simultaneously
python3 encode.py -d source destination -j 2

# Disable email notifications
python3 encode.py -d source destination -nm
```

### Arguments

| Argument | Purpose |
|---|---|
| `-d`, `--dir` | Treat the source as a directory |
| `-b`, `--bitrate` | Maximum video bitrate in kb/s. Default: 1500 |
| `--cq` | Constant quality level. Lower values produce better quality and larger files. Default: 30 |
| `-r`, `--res` | Target output resolution, based on the shorter side. Default: 1080 |
| `-j`, `--jobs` | Number of files to encode simultaneously. Default: 1 |
| `-R`, `--recursive` | Recursively process subdirectories and recreate their structure in the destination |
| `-h2s`, `--hdr2sdr` | Convert HDR video to SDR using GPU encoding |
| `-y`, `--noconfirm` | Skip overwrite confirmation |
| `-nm`, `--no-mail` | Disable email notifications |

### Notes

- Output resolution is based on the shorter side of the video, preserving its aspect ratio.
- Videos are never upscaled.
- HDR files are encoded using the CPU by default to preserve HDR information. Use `--hdr2sdr` to convert them to SDR.
- Parallel processing applies to directory mode.
- When recursive processing is enabled, the source directory structure is recreated inside the destination.
- Original files are retained when decoding errors are detected, even if deletion after encoding was requested.