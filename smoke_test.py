"""Smoke test: prove the Qwen free-tier stack end-to-end (chat + image + tts + video).

Usage:
    python smoke_test.py            # fast path: chat + image + tts
    python smoke_test.py --video    # also generate one Wan video shot (slower)
"""
import sys
from pathlib import Path

from showrunner import qwen_client as qc

OUT = Path("output/smoke")


def main(do_video: bool) -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    print("[1/4] chat (qwen-max) - scene line...")
    line = qc.chat(
        "Write ONE punchy line of dialogue for a street-food vendor in Kuala Lumpur "
        "who just discovered his rival copied his recipe. Reply with the line only.",
        system="You are a short-drama screenwriter. Output only the line, no quotes.",
    )
    print("   ->", line)

    print("[2/4] image (wan2.2-t2i-flash) - storyboard frame...")
    img, _ = qc.generate_image(
        "cinematic vertical 9:16 storyboard frame, a Kuala Lumpur night market food stall "
        "at dusk, steam rising from a wok, moody neon, film still",
        OUT / "frame.png",
    )
    print("   ->", img, f"({img.stat().st_size} bytes)")

    print("[3/4] tts (qwen3-tts-flash) - voice line...")
    audio = qc.synthesize_speech(line, OUT / "line.wav")
    print("   ->", audio, f"({audio.stat().st_size} bytes)")

    if do_video:
        print("[4/4] video (wan2.2-t2v-plus) - one shot (takes a few minutes)...")
        vid, _ = qc.generate_video(
            "cinematic vertical shot, a KL night market food vendor turns and locks eyes "
            "with the camera, steam and neon, slow push-in",
            OUT / "shot.mp4",
        )
        print("   ->", vid, f"({vid.stat().st_size} bytes)")
    else:
        print("[4/4] video - skipped (pass --video to include)")

    print("\nSMOKE OK - assets in", OUT.resolve())


if __name__ == "__main__":
    main("--video" in sys.argv)
