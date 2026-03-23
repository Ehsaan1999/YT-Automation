"""
Horror Video Generator  —  main.py
Run:  python horror_gen/main.py
"""

import json
import os
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
FFMPEG_EXE  = os.path.join(PROJECT_DIR, "ffmpeg", "ffmpeg.exe")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

sys.path.insert(0, SCRIPT_DIR)
import script_gen     as sg
import image_gen      as ig
import tts_gen        as tg
import video_composer as vc


# ── Config ─────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_config(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def sanitize(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\n\r\t]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:60]


# ── Pipeline ───────────────────────────────────────────────────────────────────

def run_generation(cfg: dict, log=print) -> None:
    topic      = cfg["topic"]
    num_scenes = cfg["num_scenes"]
    output_dir = cfg["output_dir"]

    log("=" * 48)
    log(f"  Topic  : {topic}")
    log(f"  Scenes : {num_scenes}")
    log("=" * 48)

    # 1. Script
    log("\n[1/4] Writing horror script...")
    data      = sg.generate_horror_script(topic, num_scenes, cfg["unturf_key"])
    title     = data["title"]
    narration = data["narration"]
    prompts   = data["image_prompts"]
    log(f"  Title  : {title}")
    log(f"  Words  : {len(narration.split())}  Scenes: {len(prompts)}")

    work_dir = os.path.join(output_dir, sanitize(title))
    os.makedirs(work_dir, exist_ok=True)
    with open(os.path.join(work_dir, "narration.txt"), "w", encoding="utf-8") as f:
        f.write(f"{title}\n\n{narration}")

    # 2. Images
    log(f"\n[2/4] Generating {len(prompts)} images...")
    image_paths = ig.generate_images(
        prompts    = prompts,
        output_dir = work_dir,
        hf_token   = cfg.get("hf_token", ""),
        hf_model   = cfg.get("hf_model", "stabilityai/stable-diffusion-xl-base-1.0"),
        horde_key  = cfg.get("horde_key", "").strip() or ig.HORDE_ANON_KEY,
        log        = log,
    )

    # 3. Narration audio
    log("\n[3/4] Generating narration (Edge TTS)...")
    audio_path = os.path.join(work_dir, "narration.mp3")
    tg.generate_narration(
        text        = narration,
        output_path = audio_path,
        provider    = "edge",
        voice       = tg.EDGE_VOICES.get(cfg["voice"], "en-US-AndrewNeural"),
        rate        = tg.RATES.get(cfg["speed"], "-3%"),
        pitch       = tg.PITCHES.get(cfg.get("pitch", "Slightly deep"), "-5Hz"),
        log         = log,
    )
    duration = tg.get_audio_duration(FFMPEG_EXE, audio_path)
    log(f"  Audio  : {duration:.1f}s")

    # 4. Compose video
    log("\n[4/4] Composing video...")
    scene_dur   = max(4.0, duration / len(image_paths))
    output_path = os.path.join(output_dir, sanitize(title) + ".mp4")
    vc.compose_video(
        ffmpeg_exe     = FFMPEG_EXE,
        image_paths    = image_paths,
        audio_path     = audio_path,
        output_path    = output_path,
        scene_duration = scene_dur,
        narration_text = narration if cfg["subtitles"] else None,
        show_subtitles = cfg["subtitles"],
        log            = log,
    )

    log("\n" + "=" * 48)
    log("  Done!")
    log(f"  Saved : {output_path}")
    log("=" * 48)
    return output_path


# ── Icon ───────────────────────────────────────────────────────────────────────

def _set_icon(root: tk.Tk) -> None:
    """Set a simple horror-themed app icon using PIL if available."""
    try:
        from PIL import Image, ImageDraw
        import tempfile

        size = 64
        img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d    = ImageDraw.Draw(img)
        d.ellipse([2, 2, size - 2, size - 2], fill=(139, 0, 0, 255))
        # Simple cross mark
        m = size // 2
        d.line([m - 12, m - 12, m + 12, m + 12], fill="white", width=5)
        d.line([m + 12, m - 12, m - 12, m + 12], fill="white", width=5)

        ico_path = os.path.join(tempfile.gettempdir(), "_horror_icon.png")
        img.save(ico_path)
        photo = tk.PhotoImage(file=ico_path)
        root.iconphoto(True, photo)
        root._icon_ref = photo  # prevent GC
    except Exception:
        pass


# ── GUI ────────────────────────────────────────────────────────────────────────

def build_gui() -> None:
    cfg = load_config()

    root = tk.Tk()
    root.title("Horror Video Generator")
    root.resizable(True, True)
    root.minsize(720, 520)
    root.configure(bg="#1a1a1a")
    _set_icon(root)

    # Colour palette
    BG      = "#1a1a1a"
    PANEL   = "#1e1e1e"
    ACCENT  = "#8B0000"
    FG      = "#e8e8e8"
    FG_DIM  = "#666666"
    BORDER  = "#2c2c2c"
    ENTRY   = "#2a2a2a"
    LOG_BG  = "#0d0d0d"
    LOG_FG  = "#00cc44"

    # ttk styles
    style = ttk.Style()
    style.theme_use("default")
    style.configure("Dark.TCombobox",
                    fieldbackground=ENTRY, background=ENTRY,
                    foreground=FG, selectbackground=ACCENT,
                    arrowcolor=FG_DIM)
    style.configure("TSpinbox",
                    fieldbackground=ENTRY, background=ENTRY,
                    foreground=FG, arrowcolor=FG_DIM)

    # ── Root layout ──────────────────────────────────────────────────────────

    # Header bar
    hdr = tk.Frame(root, bg=ACCENT, pady=8)
    hdr.pack(fill=tk.X, side=tk.TOP)
    tk.Label(hdr, text="HORROR VIDEO GENERATOR",
             bg=ACCENT, fg="white", font=("Segoe UI", 12, "bold")).pack()
    tk.Label(hdr, text="AI-generated cinematic horror shorts",
             bg=ACCENT, fg="#ffbbbb", font=("Segoe UI", 8)).pack()

    # Status bar (bottom)
    status_var = tk.StringVar(value="Ready")
    tk.Label(root, textvariable=status_var, bg="#0f0f0f", fg=FG_DIM,
             font=("Consolas", 8), anchor="w", padx=10).pack(
        side=tk.BOTTOM, fill=tk.X, ipady=3)

    # Body: 25 | 75
    body = tk.Frame(root, bg=BG)
    body.pack(fill=tk.BOTH, expand=True, side=tk.TOP)
    body.columnconfigure(0, weight=1, minsize=210)
    body.columnconfigure(1, weight=3)
    body.rowconfigure(0, weight=1)

    # Divider
    tk.Frame(body, bg=BORDER, width=1).grid(row=0, column=0, sticky="nse")

    # Left settings panel
    left = tk.Frame(body, bg=PANEL)
    left.grid(row=0, column=0, sticky="nsew")

    # Right log panel
    right = tk.Frame(body, bg=LOG_BG)
    right.grid(row=0, column=1, sticky="nsew")
    right.rowconfigure(0, weight=1)
    right.columnconfigure(0, weight=1)

    # ── Log box ──────────────────────────────────────────────────────────────
    log_box = scrolledtext.ScrolledText(
        right, state="disabled", wrap=tk.WORD,
        font=("Consolas", 9),
        bg=LOG_BG, fg=LOG_FG, insertbackground=LOG_FG,
        relief="flat", highlightthickness=0,
        padx=12, pady=10)
    log_box.grid(row=0, column=0, sticky="nsew")

    # ── Left panel helpers ───────────────────────────────────────────────────

    def section(text: str) -> None:
        tk.Label(left, text=text, bg=PANEL, fg=ACCENT,
                 font=("Segoe UI", 7, "bold"), anchor="w").pack(
            fill=tk.X, padx=14, pady=(12, 1))
        tk.Frame(left, bg=BORDER, height=1).pack(fill=tk.X, padx=14, pady=(0, 6))

    def field(label: str) -> tk.Label:
        return tk.Label(left, text=label, bg=PANEL, fg=FG,
                        font=("Segoe UI", 9), anchor="w")

    def mk_entry(var, show="") -> tk.Entry:
        return tk.Entry(left, textvariable=var, show=show,
                        bg=ENTRY, fg=FG, insertbackground=FG,
                        relief="flat", highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=ACCENT)

    def mk_combo(var, values) -> ttk.Combobox:
        return ttk.Combobox(left, textvariable=var, values=values,
                            state="readonly", style="Dark.TCombobox")

    # ── YOUR VIDEO ───────────────────────────────────────────────────────────
    section("YOUR VIDEO")

    topic_var = tk.StringVar(value=cfg.get("last_topic", ""))
    field("Topic / Theme").pack(anchor="w", padx=14)
    mk_entry(topic_var).pack(fill=tk.X, padx=14, pady=(2, 2))
    tk.Label(left, text='e.g. "haunted lighthouse"',
             bg=PANEL, fg=FG_DIM, font=("Segoe UI", 7)).pack(
        anchor="w", padx=14, pady=(0, 6))

    sc_row = tk.Frame(left, bg=PANEL)
    sc_row.pack(fill=tk.X, padx=14, pady=(0, 4))
    field("Scenes").pack(in_=sc_row, side=tk.LEFT)
    scenes_var = tk.IntVar(value=cfg.get("default_scenes", 6))
    ttk.Spinbox(sc_row, from_=3, to=12, textvariable=scenes_var,
                width=4).pack(side=tk.LEFT, padx=(8, 0))

    sub_var = tk.BooleanVar(value=cfg.get("subtitles", True))
    tk.Checkbutton(left, text="Burn subtitles (centred)", variable=sub_var,
                   bg=PANEL, fg=FG, selectcolor=ENTRY,
                   activebackground=PANEL, activeforeground=FG,
                   font=("Segoe UI", 9)).pack(anchor="w", padx=14, pady=(4, 0))

    # ── NARRATION VOICE ──────────────────────────────────────────────────────
    section("NARRATION VOICE  (free)")

    voice_keys = list(tg.EDGE_VOICES.keys())
    saved_voice = cfg.get("voice", voice_keys[0])
    if saved_voice not in voice_keys:
        saved_voice = voice_keys[0]
    voice_var = tk.StringVar(value=saved_voice)

    speed_keys = list(tg.RATES.keys())
    saved_speed = cfg.get("speed", speed_keys[0])
    if saved_speed not in speed_keys:
        saved_speed = speed_keys[0]
    speed_var = tk.StringVar(value=saved_speed)

    pitch_keys = list(tg.PITCHES.keys())
    saved_pitch = cfg.get("pitch", "Slightly deep")
    if saved_pitch not in pitch_keys:
        saved_pitch = pitch_keys[1] if len(pitch_keys) > 1 else pitch_keys[0]
    pitch_var = tk.StringVar(value=saved_pitch)

    field("Voice").pack(anchor="w", padx=14)
    mk_combo(voice_var, voice_keys).pack(fill=tk.X, padx=14, pady=(2, 6))

    spd_row = tk.Frame(left, bg=PANEL)
    spd_row.pack(fill=tk.X, padx=14, pady=(0, 6))
    tk.Label(spd_row, text="Speed", bg=PANEL, fg=FG,
             font=("Segoe UI", 9), width=6, anchor="w").pack(side=tk.LEFT)
    ttk.Combobox(spd_row, textvariable=speed_var, values=speed_keys,
                 state="readonly", style="Dark.TCombobox",
                 width=14).pack(side=tk.LEFT, padx=(4, 0))

    pit_row = tk.Frame(left, bg=PANEL)
    pit_row.pack(fill=tk.X, padx=14, pady=(0, 4))
    tk.Label(pit_row, text="Pitch", bg=PANEL, fg=FG,
             font=("Segoe UI", 9), width=6, anchor="w").pack(side=tk.LEFT)
    ttk.Combobox(pit_row, textvariable=pitch_var, values=pitch_keys,
                 state="readonly", style="Dark.TCombobox",
                 width=14).pack(side=tk.LEFT, padx=(4, 0))

    # ── STABLE HORDE KEY ─────────────────────────────────────────────────────
    section("STABLE HORDE KEY  (optional — portrait images)")

    horde_key_var = tk.StringVar(value=cfg.get("horde_key", ""))
    tk.Entry(left, textvariable=horde_key_var, bg=ENTRY, fg=FG,
             insertbackground=FG, relief="flat",
             highlightthickness=1, highlightbackground=BORDER).pack(
        fill=tk.X, padx=14, pady=(0, 2))
    tk.Label(left, text="Free at stablehorde.net/register  —  unlocks 9:16 portrait",
             bg=PANEL, fg=FG_DIM, font=("Segoe UI", 7)).pack(
        anchor="w", padx=14, pady=(0, 4))

    # ── GROQ API KEY ─────────────────────────────────────────────────────────
    section("GROQ API KEY  (free — script generation)")

    unturf_var = tk.StringVar(value=cfg.get("unturf_key", ""))
    key_row = tk.Frame(left, bg=PANEL)
    key_row.pack(fill=tk.X, padx=14, pady=(0, 2))
    key_entry = tk.Entry(key_row, textvariable=unturf_var, show="*",
                         bg=ENTRY, fg=FG, insertbackground=FG,
                         relief="flat", highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=ACCENT)
    key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def toggle_key():
        key_entry.config(show="" if key_entry.cget("show") else "*")
    tk.Button(key_row, text="Show", bg=BORDER, fg=FG_DIM, relief="flat",
              command=toggle_key, font=("Segoe UI", 7),
              padx=6, pady=2, bd=0, cursor="hand2").pack(side=tk.LEFT, padx=(4, 0))

    tk.Label(left, text="console.groq.com  —  no credit card needed",
             bg=PANEL, fg=FG_DIM, font=("Segoe UI", 7)).pack(
        anchor="w", padx=14, pady=(0, 4))

    # ── OUTPUT FOLDER ────────────────────────────────────────────────────────
    section("OUTPUT FOLDER")

    out_var = tk.StringVar(value=cfg.get("output_dir",
                            os.path.join(PROJECT_DIR, "horror_videos")))
    out_row = tk.Frame(left, bg=PANEL)
    out_row.pack(fill=tk.X, padx=14, pady=(0, 4))
    tk.Entry(out_row, textvariable=out_var, bg=ENTRY, fg=FG,
             insertbackground=FG, relief="flat",
             highlightthickness=1, highlightbackground=BORDER).pack(
        side=tk.LEFT, fill=tk.X, expand=True)
    tk.Button(out_row, text="…", bg=BORDER, fg=FG_DIM, relief="flat",
              command=lambda: out_var.set(filedialog.askdirectory() or out_var.get()),
              font=("Segoe UI", 9), padx=6, pady=2, bd=0,
              cursor="hand2").pack(side=tk.LEFT, padx=(4, 0))

    # ── GENERATE BUTTON ──────────────────────────────────────────────────────
    tk.Frame(left, bg=BORDER, height=1).pack(fill=tk.X, padx=14, pady=(14, 8))
    gen_btn = tk.Button(left, text="▶  GENERATE",
                        bg=ACCENT, fg="white", relief="flat",
                        font=("Segoe UI", 11, "bold"),
                        pady=10, cursor="hand2", bd=0,
                        activebackground="#6b0000", activeforeground="white")
    gen_btn.pack(fill=tk.X, padx=14, pady=(0, 6))

    last_video_path = [None]   # mutable container so worker thread can set it

    open_btn = tk.Button(left, text="▶  OPEN VIDEO",
                         bg="#1a3a1a", fg="#00cc44", relief="flat",
                         font=("Segoe UI", 9),
                         pady=6, cursor="hand2", bd=0, state="disabled",
                         activebackground="#0d2a0d", activeforeground="#00cc44")
    open_btn.pack(fill=tk.X, padx=14, pady=(0, 14))

    def open_last_video():
        path = last_video_path[0]
        if path and os.path.exists(path):
            subprocess.Popen(["start", "", path], shell=True)
        else:
            status_var.set("No video found.")

    open_btn.config(command=open_last_video)

    # ── Logic ────────────────────────────────────────────────────────────────

    def log(msg: str) -> None:
        def _do():
            log_box.config(state="normal")
            log_box.insert(tk.END, msg + "\n")
            log_box.see(tk.END)
            log_box.config(state="disabled")
        root.after(0, _do)

    def on_generate():
        topic = topic_var.get().strip()
        ukey  = unturf_var.get().strip()

        if not topic:
            status_var.set("Enter a topic first.")
            return
        if not ukey:
            status_var.set("Groq API key required  (console.groq.com — free)")
            return
        if not os.path.exists(FFMPEG_EXE):
            status_var.set(f"ffmpeg not found: {FFMPEG_EXE}")
            return

        current_cfg = {
            **load_config(),
            "topic":          topic,
            "num_scenes":     scenes_var.get(),
            "subtitles":      sub_var.get(),
            "voice":          voice_var.get(),
            "speed":          speed_var.get(),
            "pitch":          pitch_var.get(),
            "output_dir":     out_var.get().strip(),
            "unturf_key":     ukey,
            "horde_key":      horde_key_var.get().strip(),
            "last_topic":     topic,
            "default_scenes": scenes_var.get(),
        }
        save_config(current_cfg)

        gen_btn.config(state="disabled", text="Generating…")
        status_var.set("Running...")
        log_box.config(state="normal")
        log_box.delete("1.0", tk.END)
        log_box.config(state="disabled")

        def worker():
            try:
                video_path = run_generation(current_cfg, log)
                last_video_path[0] = video_path
                root.after(0, lambda: status_var.set("Done!"))
                root.after(0, lambda: open_btn.config(state="normal", bg="#1a3a1a"))
            except Exception as e:
                msg = str(e)
                log(f"\nERROR: {msg}")
                root.after(0, lambda m=msg: status_var.set(f"Error: {m}"))
            finally:
                root.after(0, lambda: gen_btn.config(
                    state="normal", text="▶  GENERATE"))

        threading.Thread(target=worker, daemon=True).start()

    gen_btn.config(command=on_generate)
    root.mainloop()


if __name__ == "__main__":
    build_gui()
