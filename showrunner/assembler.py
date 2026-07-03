"""Post-production stage — mux each shot's video+voice, burn subtitles, concat.

Uses the system ffmpeg/ffprobe (confirmed present). Each scene is normalised to
the same size/codec so the final concatenation is a cheap stream copy.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# CJK-capable fonts first so Chinese subtitles render; fall back to Latin.
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",     # Microsoft YaHei (CJK)
    "C:/Windows/Fonts/msyhl.ttc",
    "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/arial.ttf",
]


def _font() -> str:
    for f in _FONT_CANDIDATES:
        if Path(f).exists():
            return f
    return _FONT_CANDIDATES[-1]


def _run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{' '.join(args)}\n{proc.stderr[-600:]}")


def _duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def _wrap(text: str, width: int = 22) -> str:
    """Naive word-wrap so drawtext (which has no auto-wrap) stays on screen."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines) if lines else text


def _esc_path(p: str) -> str:
    """Escape a Windows path for use inside an ffmpeg filtergraph option."""
    return p.replace("\\", "/").replace(":", r"\:")


def assemble_scene(video: Path, audio: Path, subtitle: str, dest: Path,
                   size: str = "480*832") -> Path:
    """Combine one shot's video + voice + burned subtitle into a normalised clip."""
    w, h = size.split("*")
    v_dur, a_dur = _duration(video), _duration(audio)
    target = max(v_dur, a_dur, 1.0)
    extra = max(0.0, a_dur - v_dur)

    sub_file = dest.with_suffix(".sub.txt")
    sub_file.write_text(_wrap(subtitle), encoding="utf-8")

    drawtext = (
        f"drawtext=fontfile='{_esc_path(_font())}':textfile='{_esc_path(str(sub_file))}'"
        f":fontcolor=white:fontsize=30:box=1:boxcolor=black@0.55:boxborderw=14"
        f":x=(w-text_w)/2:y=h-text_h-70:line_spacing=8"
    )
    # extend video with a frozen last frame only when the voice runs longer
    tpad = f"tpad=stop_mode=clone:stop_duration={extra:.2f}," if extra > 0.05 else ""
    filtergraph = (
        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},{tpad}{drawtext}[v];[1:a]apad[a]"
    )

    _run([
        "ffmpeg", "-y", "-i", str(video), "-i", str(audio),
        "-filter_complex", filtergraph,
        "-map", "[v]", "-map", "[a]",
        "-t", f"{target:.2f}",
        "-r", "24", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", str(dest),
    ])
    sub_file.unlink(missing_ok=True)
    return dest


def concat_scenes(scenes: list[Path], dest: Path) -> Path:
    """Concatenate normalised scene clips into the final episode."""
    listing = dest.with_suffix(".concat.txt")
    listing.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in scenes),
        encoding="utf-8",
    )
    try:
        _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
              "-c", "copy", str(dest)])
    except RuntimeError:
        # fall back to re-encode if stream-copy concat is rejected
        _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
              "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(dest)])
    listing.unlink(missing_ok=True)
    return dest
