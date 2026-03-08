"""
YouTube Clip Extractor
----------------------
Reads an Excel file with columns:
    URL | Start Time | End Time   (row 1 = headers, data starts row 2)

Time format: HH:MM:SS, MM:SS, or plain seconds (e.g. 90)
Multiple ranges per row: comma-separate values in Start/End columns
    e.g. Start = "00:01:00, 00:03:00"  End = "00:01:30, 00:03:30"

Output filename: {video_title}_{start}_{end}.mp4
All clips are merged in order into merged_output.mp4

Dependencies (portable, no admin needed):
- yt-dlp    (pip install yt-dlp)
- openpyxl  (pip install openpyxl)
- ffmpeg    (./ffmpeg/ffmpeg.exe)
"""

import datetime
import os
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext
import openpyxl

# Ensure console can handle Unicode titles (emoji, etc.)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FFMPEG_DIR = os.path.join(SCRIPT_DIR, "ffmpeg")
FFMPEG_EXE = os.path.join(FFMPEG_DIR, "ffmpeg.exe")
INPUT_FILE = os.path.join(SCRIPT_DIR, "input.xlsx")
PYTHON     = sys.executable


# ── Helpers ────────────────────────────────────────────────────────────────────

def sanitize(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:80]


def normalize_time(t: str) -> str:
    """Return timestamp as HH:MM:SS."""
    t = t.strip()
    if re.fullmatch(r"\d+", t):
        secs = int(t)
        h, rem = divmod(secs, 3600)
        m, s   = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    parts = t.split(":")
    if len(parts) == 2:
        return f"00:{int(parts[0]):02d}:{int(parts[1]):02d}"
    if len(parts) == 3:
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}:{int(parts[2]):02d}"
    raise ValueError(f"Unrecognized time format: {t!r}")


def time_to_tag(hms: str) -> str:
    return hms.replace(":", "-")


def cell_to_str(v) -> str:
    if isinstance(v, datetime.time):
        return v.strftime("%H:%M:%S")
    return str(v).strip() if v is not None else ""


# ── Core extraction ────────────────────────────────────────────────────────────

def get_title(url: str, log=print) -> str:
    result = subprocess.run(
        [PYTHON, "-m", "yt_dlp", "--skip-download", "--print", "title",
         "--no-warnings", url],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    title = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "video"
    return title


def extract_clip(url: str, start: str, end: str, output_dir: str, log=print) -> str | None:
    title      = get_title(url, log)
    safe_title = sanitize(title)
    start_hms  = normalize_time(start)
    end_hms    = normalize_time(end)
    filename   = f"{safe_title}_{time_to_tag(start_hms)}_{time_to_tag(end_hms)}.mp4"
    out_path   = os.path.join(output_dir, filename)

    log(f"  Title   : {title}")
    log(f"  Segment : {start_hms} -> {end_hms}")
    log(f"  Output  : {out_path}")

    cmd = [
        PYTHON, "-m", "yt_dlp",
        "--ffmpeg-location", FFMPEG_DIR,
        "--download-sections", f"*{start_hms}-{end_hms}",
        "--force-keyframes-at-cuts",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", out_path,
        url,
    ]

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="replace"
    )
    for line in proc.stdout:
        log(line.rstrip())
    proc.wait()

    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp exited with code {proc.returncode}")

    if os.path.exists(out_path):
        size_mb = os.path.getsize(out_path) / 1024 / 1024
        log(f"  Saved   : {out_path}  ({size_mb:.1f} MB)")
        return out_path

    # yt-dlp sometimes changes extension — look for a close match
    base = os.path.splitext(filename)[0]
    matches = [f for f in os.listdir(output_dir) if f.startswith(base)]
    if matches:
        found = os.path.join(output_dir, matches[0])
        log(f"  Saved   : {found}")
        return found

    log("  WARNING : Output file not found - check yt-dlp output above.")
    return None


def probe_resolution(path: str) -> tuple[int, int] | None:
    """Return (width, height) of the first video stream, or None on failure."""
    result = subprocess.run(
        [FFMPEG_EXE, "-i", path],
        capture_output=True, encoding="utf-8", errors="replace"
    )
    m = re.search(r"(\d{2,5})x(\d{2,5})", result.stderr)
    return (int(m.group(1)), int(m.group(2))) if m else None


def merge_clips(clip_paths: list, output_dir: str, log=print) -> None:
    valid = [p for p in clip_paths if p and os.path.exists(p)]
    if len(valid) < 2:
        log("  (Skipping merge - fewer than 2 valid clips.)")
        return

    merged_path = os.path.join(output_dir, "merged_output.mp4")
    n = len(valid)

    # Probe target resolution from the first clip so all clips are scaled to
    # the same size. The concat filter requires uniform resolution.
    res = probe_resolution(valid[0])
    if res:
        w, h = res
        log(f"  Target resolution: {w}x{h} (from first clip)")
    else:
        w, h = 1920, 1080
        log(f"  Could not probe resolution, defaulting to {w}x{h}")

    inputs = []
    for p in valid:
        inputs += ["-i", p]

    # Scale+pad each clip to target resolution, resample audio to 44100 Hz,
    # then concat. This ensures consistent resolution/sample-rate across clips
    # so the concat filter produces a clean, playable output.
    parts = []
    for i in range(n):
        parts.append(
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setpts=PTS-STARTPTS[v{i}];"
            f"[{i}:a]aresample=44100,asetpts=PTS-STARTPTS[a{i}]"
        )
    filter_chain  = ";".join(parts)
    concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(n))
    filter_complex = f"{filter_chain};{concat_inputs}concat=n={n}:v=1:a=1[v][a]"

    log(f"\nMerging {n} clips -> {merged_path}")
    cmd = [
        FFMPEG_EXE, "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        merged_path
    ]
    result = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")

    if result.returncode == 0 and os.path.exists(merged_path):
        size_mb = os.path.getsize(merged_path) / 1024 / 1024
        log(f"  Merged  : {merged_path}  ({size_mb:.1f} MB)")
    else:
        log(f"  ERROR   : Merge failed.\n{result.stderr[-800:]}")


# ── Input parsing ──────────────────────────────────────────────────────────────

def parse_input(path: str, log=print) -> list:
    """
    Returns list of (url, start, end) tuples.
    Rows with comma-separated times produce multiple entries.
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = iter(ws.rows)

    try:
        headers = [str(c.value).strip().lower() if c.value else "" for c in next(rows)]
    except StopIteration:
        log("ERROR: Excel file is empty.")
        return []

    def find_col(keywords):
        for i, h in enumerate(headers):
            if any(k in h for k in keywords):
                return i
        return None

    col_url   = find_col(["url", "link"])
    col_start = find_col(["start"])
    col_end   = find_col(["end"])

    if any(c is None for c in [col_url, col_start, col_end]):
        log("ERROR: Could not find required columns.")
        log(f"  Headers found : {headers}")
        log("  Expected      : 'url', 'start', 'end'")
        return []

    entries = []
    for rowno, row in enumerate(rows, 2):
        cells = [c.value for c in row]
        while len(cells) <= max(col_url, col_start, col_end):
            cells.append(None)

        url   = cells[col_url]
        start = cells[col_start]
        end   = cells[col_end]

        if not url and not start and not end:
            continue
        if not url:
            log(f"  [!] Row {rowno} skipped - missing URL")
            continue

        start_str = cell_to_str(start)
        end_str   = cell_to_str(end)

        # Support comma-separated multiple ranges
        starts = [s.strip() for s in start_str.split(",") if s.strip()]
        ends   = [e.strip() for e in end_str.split(",")   if e.strip()]

        if not starts or not ends:
            log(f"  [!] Row {rowno} skipped - missing start or end time")
            continue

        if len(starts) != len(ends):
            log(f"  [!] Row {rowno}: {len(starts)} start(s) vs {len(ends)} end(s) - using matched pairs")

        for s, e in zip(starts, ends):
            entries.append((str(url).strip(), s, e))

    wb.close()
    return entries


# ── Orchestration ──────────────────────────────────────────────────────────────

def run_extraction(input_file: str, output_dir: str, log=print) -> None:
    if not os.path.exists(input_file):
        log(f"ERROR: {input_file} not found.")
        return

    entries = parse_input(input_file, log)
    if not entries:
        log("No valid entries found.")
        return

    log(f"Found {len(entries)} clip(s) to extract.\n")
    os.makedirs(output_dir, exist_ok=True)
    log(f"Saving to: {output_dir}\n")

    ok, fail = 0, 0
    saved_paths = []

    for i, (url, start, end) in enumerate(entries, 1):
        log(f"-- Clip {i}/{len(entries)} " + "-" * 40)
        log(f"  URL     : {url}")
        try:
            path = extract_clip(url, start, end, output_dir, log)
            saved_paths.append(path)
            ok += 1
        except Exception as e:
            log(f"  ERROR   : {e}")
            saved_paths.append(None)
            fail += 1
        log("")

    log("=" * 50)
    log(f"Extraction complete - {ok} succeeded, {fail} failed.")

    if ok >= 2:
        merge_clips(saved_paths, output_dir, log)

    log("\nAll done.")


# ── Tkinter GUI ────────────────────────────────────────────────────────────────

def gui() -> None:
    root = tk.Tk()
    root.title("YouTube Clip Extractor")
    root.minsize(680, 480)

    # -- File inputs -----------------------------------------------------------
    frame_top = tk.Frame(root, padx=12, pady=10)
    frame_top.pack(fill=tk.X)
    frame_top.columnconfigure(1, weight=1)

    tk.Label(frame_top, text="Input Excel:", anchor="w").grid(
        row=0, column=0, sticky="w", pady=3)
    input_var = tk.StringVar()
    tk.Entry(frame_top, textvariable=input_var).grid(
        row=0, column=1, sticky="ew", padx=6)
    tk.Button(
        frame_top, text="Browse...",
        command=lambda: input_var.set(
            filedialog.askopenfilename(
                filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")]
            ) or input_var.get()
        )
    ).grid(row=0, column=2)

    tk.Label(frame_top, text="Output Folder:", anchor="w").grid(
        row=1, column=0, sticky="w", pady=3)
    output_var = tk.StringVar(value=os.path.join(SCRIPT_DIR, "clips"))
    tk.Entry(frame_top, textvariable=output_var).grid(
        row=1, column=1, sticky="ew", padx=6)
    tk.Button(
        frame_top, text="Browse...",
        command=lambda: output_var.set(
            filedialog.askdirectory() or output_var.get()
        )
    ).grid(row=1, column=2)

    # -- Log area --------------------------------------------------------------
    log_box = scrolledtext.ScrolledText(
        root, state="disabled", wrap=tk.WORD,
        font=("Consolas", 9), padx=5, pady=5
    )
    log_box.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 0))

    # -- Bottom bar ------------------------------------------------------------
    frame_bot = tk.Frame(root, padx=12, pady=8)
    frame_bot.pack(fill=tk.X)

    status_var = tk.StringVar(value="Ready")
    tk.Label(frame_bot, textvariable=status_var, anchor="w").pack(
        side=tk.LEFT, expand=True, fill=tk.X)

    run_btn = tk.Button(frame_bot, text="Run", width=14)
    run_btn.pack(side=tk.RIGHT)

    # -- Helpers ---------------------------------------------------------------
    def log(msg: str) -> None:
        def _append():
            log_box.config(state="normal")
            log_box.insert(tk.END, msg + "\n")
            log_box.see(tk.END)
            log_box.config(state="disabled")
        root.after(0, _append)

    def on_run() -> None:
        inp = input_var.get().strip()
        out = output_var.get().strip()
        if not inp:
            status_var.set("Please select an input Excel file.")
            return
        if not out:
            status_var.set("Please select an output folder.")
            return

        run_btn.config(state="disabled")
        status_var.set("Running...")
        log_box.config(state="normal")
        log_box.delete("1.0", tk.END)
        log_box.config(state="disabled")

        def worker() -> None:
            try:
                run_extraction(inp, out, log)
            except Exception as e:
                log(f"FATAL: {e}")
            finally:
                root.after(0, lambda: run_btn.config(state="normal"))
                root.after(0, lambda: status_var.set("Done"))

        threading.Thread(target=worker, daemon=True).start()

    run_btn.config(command=on_run)
    root.mainloop()


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--cli" in sys.argv:
        output_dir = input("Output folder (press Enter for './clips'): ").strip()
        if not output_dir:
            output_dir = os.path.join(SCRIPT_DIR, "clips")
        run_extraction(INPUT_FILE, output_dir)
    else:
        gui()
