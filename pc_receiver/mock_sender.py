"""Mock Sender for ZeroCast PC Receiver Testing
Generates test frames and streams them to 127.0.0.1:8888 to verify PC receiver without an Android device.
"""

import io
import time
import socket
from PIL import Image, ImageDraw, ImageFont
from core.protocol import pack_header, TYPE_VIDEO_MJPEG


def generate_frame(frame_num: int, width: int = 1280, height: int = 720) -> bytes:
    """Generates an animated test card with timestamp and moving graphics."""
    img = Image.new("RGB", (width, height), color=(20, 24, 30))
    draw = ImageDraw.Draw(img)

    # Moving circle
    cx = int((width / 2) + 300 * (0.5 + 0.5 * (frame_num % 100) / 100.0) * (1 if (frame_num // 100) % 2 == 0 else -1))
    cy = height // 2
    draw.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], fill=(0, 230, 118))

    # Grid lines
    for x in range(0, width, 160):
        draw.line([(x, 0), (x, height)], fill=(40, 45, 55), width=1)
    for y in range(0, height, 90):
        draw.line([(0, y), (width, y)], fill=(40, 45, 55), width=1)

    # Text Info
    draw.text((50, 50), "ZeroCast Mock Streamer", fill=(255, 255, 255))
    draw.text((50, 80), f"Frame #{frame_num} | Resolution: {width}x{height}", fill=(200, 200, 200))
    draw.text((50, 110), f"Simulated Latency & Real-Time MJPEG Stream", fill=(150, 150, 150))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def run_mock_stream(host: str = "127.0.0.1", port: int = 8888, fps: int = 30):
    print(f"Connecting to ZeroCast receiver at {host}:{port}...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    try:
        s.connect((host, port))
        print("Connected! Streaming simulated frames...")
    except Exception as e:
        print(f"Failed to connect: {e}")
        print("Please make sure 'python main.py' is running on the PC first.")
        return

    frame_num = 0
    interval = 1.0 / fps

    try:
        while True:
            t0 = time.time()
            jpeg_bytes = generate_frame(frame_num)
            ts_us = int(time.time() * 1_000_000)

            header = pack_header(
                packet_type=TYPE_VIDEO_MJPEG,
                flags=0,
                payload_length=len(jpeg_bytes),
                timestamp_us=ts_us
            )

            s.sendall(header + jpeg_bytes)
            frame_num += 1

            elapsed = time.time() - t0
            sleep_time = max(0.0, interval - elapsed)
            time.sleep(sleep_time)
    except KeyboardInterrupt:
        print("\nStream stopped by user.")
    except Exception as e:
        print(f"Streaming error: {e}")
    finally:
        s.close()


if __name__ == "__main__":
    run_mock_stream()
