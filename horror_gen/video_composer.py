"""
video_composer.py
-----------------
Composes the final horror video from still images, narration audio, and
optional burned-in subtitles.

Pipeline:
  1. Per image → Ken Burns (slow zoom/pan) clip with fade in/out
  2. Concat all clips using ffmpeg concat filter (clean timestamps)
  3. Add narration audio (+ optional background music mix)
  4. Optionally burn ASS subtitles (proportionally timed from narration text)
  → Final MP4  1080×1920  H.264 + AAC  yuv420p  faststart
"""

import os
import re
import subprocess


# ── Internal helpers ───────────────────────────────────────────────────────────

def _run(cmd: list, log=print) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        log(f"  ffmpeg stderr:\n{result.stderr[-600:]}")
    return result


# ── Subtitle generation ────────────────────────────────────────────────────────

def _ass_timestamp(t: float) -> str:
    """Convert seconds to ASS timestamp  H:MM:SS.cc"""
    h  = int(t // 3600)
    m  = int((t % 3600) // 60)
    s  = t % 60
    cs = int((s % 1) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"


def generate_ass_subtitles(
    text:           str,
    total_duration: float,
    output_path:    str,
    width:          int = 1080,
    height:         int = 1920,
) -> str:
    """
    Split narration text into sentences, assign proportional timestamps,
    and write an ASS subtitle file styled for mobile horror content.
    Returns output_path.
    """
    # Split on sentence-ending punctuation followed by whitespace
    sentences = re.split(r'(?<=[.!?,;—])\s+', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        sentences = [text.strip()]

    total_chars = sum(len(s) for s in sentences) or 1

    # Font size ~5% of width for 1080p (readable on mobile)
    font_size   = max(40, int(width * 0.048))
    margin_v    = max(60, int(height * 0.05))

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "WrapStyle: 1\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        # White text, thick black outline, bottom-centre, bold
        f"Style: Default,Arial,{font_size},"
        "&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,4,2,2,40,40,{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    events = []
    current = 0.0
    for sentence in sentences:
        duration = (len(sentence) / total_chars) * total_duration
        end      = current + duration
        # Escape special ASS characters
        safe = sentence.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
        events.append(
            f"Dialogue: 0,{_ass_timestamp(current)},{_ass_timestamp(end)},"
            f"Default,,0,0,0,,{safe}"
        )
        current = end

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))

    return output_path


# ── Ken Burns clip ─────────────────────────────────────────────────────────────

def _make_ken_burns_clip(
    ffmpeg_exe:  str,
    image_path:  str,
    output_path: str,
    duration:    float,
    scene_index: int,
    width:       int   = 1080,
    height:      int   = 1920,
    fps:         int   = 25,
    log=print,
) -> None:
    """
    Render one Ken Burns video from a still image.
    Even scenes zoom in (1.0→1.25), odd scenes zoom out (1.25→1.0).
    Includes fade-in and fade-out.
    """
    n_frames   = int(duration * fps)
    zoom_range = 0.25
    step       = zoom_range / max(n_frames, 1)
    fade_dur   = min(0.6, duration * 0.12)
    fade_out_s = duration - fade_dur

    if scene_index % 2 == 0:
        zoom_expr = f"'min(zoom+{step:.8f},1.25)'"
    else:
        zoom_expr = f"'if(eq(on,0),1.25,max(zoom-{step:.8f},1.0))'"

    scale_w = width  * 2
    scale_h = height * 2

    vf = (
        f"scale={scale_w}:{scale_h}:force_original_aspect_ratio=increase,"
        f"crop={scale_w}:{scale_h},"
        f"zoompan=z={zoom_expr}"
        f":x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2'"
        f":d={n_frames}:s={width}x{height}:fps={fps},"
        f"fade=t=in:st=0:d={fade_dur:.2f},"
        f"fade=t=out:st={fade_out_s:.2f}:d={fade_dur:.2f},"
        f"setsar=1"
    )

    result = _run([
        ffmpeg_exe, "-y",
        "-loop", "1", "-i", image_path,
        "-vf", vf,
        "-t", str(duration),
        "-r", str(fps),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-an",
        output_path,
    ], log)
    if result.returncode != 0:
        raise RuntimeError(f"Ken Burns render failed for scene {scene_index + 1}")


# ── Main compose function ──────────────────────────────────────────────────────

def compose_video(
    ffmpeg_exe:      str,
    image_paths:     list,
    audio_path:      str,
    output_path:     str,
    scene_duration:  float,
    width:           int         = 1080,
    height:          int         = 1920,
    fps:             int         = 25,
    narration_text:  str | None  = None,   # provide to burn subtitles
    show_subtitles:  bool        = True,
    bg_music_path:   str | None  = None,
    music_volume:    float       = 0.12,
    log=print,
) -> str:
    """Full compose pipeline. Returns output_path on success."""

    clips_dir  = os.path.join(os.path.dirname(output_path), "_clips_tmp")
    os.makedirs(clips_dir, exist_ok=True)
    temp_clips = []

    try:
        # ── Step 1: Ken Burns clips ────────────────────────────────────────────
        log(f"\nRendering {len(image_paths)} scene clips ({scene_duration:.1f}s each)...")
        for i, img_path in enumerate(image_paths):
            clip_path = os.path.join(clips_dir, f"clip_{i:02d}.mp4")
            log(f"  Scene {i+1}/{len(image_paths)}: Ken Burns...")
            _make_ken_burns_clip(
                ffmpeg_exe, img_path, clip_path,
                scene_duration, i, width, height, fps, log
            )
            temp_clips.append(clip_path)

        # ── Step 2: Concat all clips ───────────────────────────────────────────
        log("\nConcatenating scenes...")
        n             = len(temp_clips)
        inputs_flat   = [a for p in temp_clips for a in ("-i", p)]
        filter_inputs = "".join(f"[{i}:v]" for i in range(n))
        video_only    = os.path.join(clips_dir, "_video_only.mp4")

        result = _run([
            ffmpeg_exe, "-y",
            *inputs_flat,
            "-filter_complex", f"{filter_inputs}concat=n={n}:v=1:a=0[v]",
            "-map", "[v]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            video_only,
        ], log)
        if result.returncode != 0:
            raise RuntimeError("Failed to concatenate scene clips")

        # ── Step 3: Audio mix + optional subtitles → final output ─────────────
        log("\nAdding audio and compositing final video...")

        # Build audio inputs / filter
        audio_inputs  = ["-i", audio_path]
        audio_map     = "-map 1:a"
        audio_filter  = None

        if bg_music_path and os.path.exists(bg_music_path):
            audio_inputs  = ["-i", audio_path, "-stream_loop", "-1", "-i", bg_music_path]
            audio_filter  = (
                f"[1:a]volume=1.0[narr];"
                f"[2:a]volume={music_volume:.2f}[music];"
                f"[narr][music]amix=inputs=2:duration=first:dropout_transition=2[a]"
            )

        # Build video filter (subtitles or plain copy)
        vf_arg = None
        if show_subtitles and narration_text:
            audio_dur   = _get_audio_duration_from_path(ffmpeg_exe, audio_path)
            ass_path    = os.path.join(clips_dir, "_subs.ass")
            generate_ass_subtitles(narration_text, audio_dur, ass_path, width, height)
            # Escape path for ffmpeg vf on Windows: backslash → / and colon → \:
            ass_escaped = ass_path.replace("\\", "/").replace(":", "\\:")
            vf_arg      = f"ass='{ass_escaped}'"

        # Assemble command
        cmd = [ffmpeg_exe, "-y", "-i", video_only, *audio_inputs]

        if audio_filter:
            cmd += ["-filter_complex", audio_filter]
            if vf_arg:
                cmd += ["-vf", vf_arg]
                cmd += ["-map", "0:v", "-map", "[a]"]
            else:
                cmd += ["-map", "0:v", "-map", "[a]", "-c:v", "copy"]
        else:
            if vf_arg:
                cmd += ["-vf", vf_arg]
                cmd += ["-map", "0:v", "-map", "1:a"]
            else:
                cmd += ["-map", "0:v", "-map", "1:a", "-c:v", "copy"]

        if not vf_arg:
            cmd += ["-c:v", "copy"]
        else:
            cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p"]

        cmd += [
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            output_path,
        ]

        result = _run(cmd, log)
        if result.returncode != 0:
            raise RuntimeError("Failed to add audio / subtitles to video")

    finally:
        for p in temp_clips:
            try: os.remove(p)
            except OSError: pass
        for name in ("_video_only.mp4", "_subs.ass"):
            try: os.remove(os.path.join(clips_dir, name))
            except OSError: pass
        try: os.rmdir(clips_dir)
        except OSError: pass

    if not os.path.exists(output_path):
        raise RuntimeError("Output video was not created")

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    log(f"\nVideo saved: {output_path}  ({size_mb:.1f} MB)")
    return output_path


def _get_audio_duration_from_path(ffmpeg_exe: str, path: str) -> float:
    result = subprocess.run(
        [ffmpeg_exe, "-i", path],
        capture_output=True, encoding="utf-8", errors="replace"
    )
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
    if not m:
        return 60.0
    h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mn * 60 + s
