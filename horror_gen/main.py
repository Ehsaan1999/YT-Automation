"""
Horror Video Generator  —  main.py
Run:  python horror_gen/main.py
"""

import json
import os
import re
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

    log("=" * 50)
    log(f"  Topic  : {topic}")
    log(f"  Scenes : {num_scenes}")
    log("=" * 50)

    # 1. Script
    log("\n[1/4] Writing horror script...")
    data      = sg.generate_horror_script(topic, num_scenes, cfg["unturf_key"])
    title     = data["title"]
    narration = data["narration"]
    prompts   = data["image_prompts"]
    log(f"  Title : {title}  ({len(narration.split())} words, {len(prompts)} scenes)")

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
        hf_model   = cfg.get("hf_model", "black-forest-labs/FLUX.1-dev"),
        log        = log,
    )

    # 3. Narration audio
    log("\n[3/4] Generating narration (Edge TTS)...")
    audio_path = os.path.join(work_dir, "narration.mp3")
    tg.generate_narration(
        text        = narration,
        output_path = audio_path,
        provider    = "edge",
        voice       = tg.EDGE_VOICES[cfg["voice"]],
        rate        = tg.RATES[cfg["speed"]],
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

    log("\n" + "=" * 50)
    log("  Done!")
    log(f"  Saved : {output_path}")
    log("=" * 50)


# ── GUI ────────────────────────────────────────────────────────────────────────

def build_gui() -> None:
    cfg = load_config()

    root = tk.Tk()
    root.title("Horror Video Generator")
    root.resizable(True, True)
    root.minsize(560, 600)
    root.configure(bg="#1a1a1a")

    # Colour palette
    BG      = "#1a1a1a"
    CARD    = "#242424"
    ACCENT  = "#8B0000"
    FG      = "#e8e8e8"
    FG_DIM  = "#888888"
    BORDER  = "#333333"
    ENTRY   = "#2e2e2e"

    pad = dict(padx=16, pady=6)

    def card(parent, title=None):
        outer = tk.Frame(parent, bg=BORDER, pady=1)
        outer.pack(fill=tk.X, padx=14, pady=5)
        inner = tk.Frame(outer, bg=CARD, padx=14, pady=10)
        inner.pack(fill=tk.X)
        inner.columnconfigure(1, weight=1)
        if title:
            tk.Label(inner, text=title.upper(), bg=CARD, fg=FG_DIM,
                     font=("Segoe UI", 8, "bold")).grid(
                row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        return inner

    def row(parent, label, widget_fn, r, hint=None):
        offset = 1 if parent.grid_size()[1] > 0 else 0
        tk.Label(parent, text=label, bg=CARD, fg=FG, anchor="w", width=14).grid(
            row=r + offset, column=0, sticky="w", pady=4)
        w = widget_fn(parent)
        w.grid(row=r + offset, column=1, sticky="ew", padx=(8, 0), pady=4)
        if hint:
            tk.Label(parent, text=hint, bg=CARD, fg=FG_DIM, font=("Segoe UI", 8)).grid(
                row=r + offset + 1, column=1, sticky="w", padx=(8, 0))
        return w

    def entry(parent, var, show=""):
        e = tk.Entry(parent, textvariable=var, bg=ENTRY, fg=FG,
                     insertbackground=FG, relief="flat",
                     highlightthickness=1, highlightbackground=BORDER,
                     show=show)
        return e

    def combo(parent, var, values):
        c = ttk.Combobox(parent, textvariable=var, values=values,
                         state="readonly", width=30)
        c.configure(style="Dark.TCombobox")
        return c

    style = ttk.Style()
    style.theme_use("default")
    style.configure("Dark.TCombobox",
                    fieldbackground=ENTRY, background=ENTRY,
                    foreground=FG, selectbackground=ACCENT,
                    arrowcolor=FG)

    # ── Header ──────────────────────────────────────────────────────────────────
    hdr = tk.Frame(root, bg=ACCENT, pady=14)
    hdr.pack(fill=tk.X)
    tk.Label(hdr, text="HORROR VIDEO GENERATOR", bg=ACCENT, fg="white",
             font=("Segoe UI", 14, "bold")).pack()
    tk.Label(hdr, text="AI-generated cinematic horror shorts", bg=ACCENT, fg="#ffaaaa",
             font=("Segoe UI", 9)).pack()

    scroll_canvas = tk.Canvas(root, bg=BG, highlightthickness=0)
    vsb = ttk.Scrollbar(root, orient="vertical", command=scroll_canvas.yview)
    scroll_canvas.configure(yscrollcommand=vsb.set)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    body = tk.Frame(scroll_canvas, bg=BG)
    body_id = scroll_canvas.create_window((0, 0), window=body, anchor="nw")
    body.bind("<Configure>", lambda e: scroll_canvas.configure(
        scrollregion=scroll_canvas.bbox("all")))
    scroll_canvas.bind("<Configure>", lambda e: scroll_canvas.itemconfig(
        body_id, width=e.width))

    # ── Topic ───────────────────────────────────────────────────────────────────
    c1 = card(body, "Your Video")
    topic_var = tk.StringVar(value=cfg.get("last_topic", ""))
    tk.Label(c1, text="Topic / Theme", bg=CARD, fg=FG, anchor="w").grid(
        row=1, column=0, columnspan=2, sticky="w", pady=(0, 2))
    te = tk.Entry(c1, textvariable=topic_var, bg=ENTRY, fg=FG,
                  insertbackground=FG, relief="flat",
                  highlightthickness=1, highlightbackground=BORDER,
                  font=("Segoe UI", 11))
    te.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 6))
    tk.Label(c1, text='e.g.  "alone at a gas station at night"  •  "haunted lighthouse"',
             bg=CARD, fg=FG_DIM, font=("Segoe UI", 8)).grid(
        row=3, column=0, columnspan=3, sticky="w")

    tk.Label(c1, text="Scenes", bg=CARD, fg=FG, anchor="w").grid(
        row=4, column=0, sticky="w", pady=(10, 4))
    scenes_var = tk.IntVar(value=cfg.get("default_scenes", 6))
    ttk.Spinbox(c1, from_=3, to=12, textvariable=scenes_var, width=5).grid(
        row=4, column=1, sticky="w", padx=(8, 0))

    sub_var = tk.BooleanVar(value=cfg.get("subtitles", True))
    tk.Checkbutton(c1, text="Burn subtitles into video", variable=sub_var,
                   bg=CARD, fg=FG, selectcolor=ENTRY, activebackground=CARD,
                   activeforeground=FG).grid(row=5, column=0, columnspan=2,
                                              sticky="w", pady=(6, 0))

    # ── Voice ───────────────────────────────────────────────────────────────────
    c2 = card(body, "Narration Voice  —  free, no key needed")
    voice_var = tk.StringVar(value=cfg.get("voice", list(tg.EDGE_VOICES.keys())[0]))
    speed_var = tk.StringVar(value=cfg.get("speed", "Slow (eerie)"))

    tk.Label(c2, text="Voice", bg=CARD, fg=FG, anchor="w", width=10).grid(
        row=1, column=0, sticky="w", pady=4)
    ttk.Combobox(c2, textvariable=voice_var, values=list(tg.EDGE_VOICES.keys()),
                 state="readonly").grid(row=1, column=1, sticky="ew", padx=(8, 0))

    tk.Label(c2, text="Speed", bg=CARD, fg=FG, anchor="w", width=10).grid(
        row=2, column=0, sticky="w", pady=4)
    ttk.Combobox(c2, textvariable=speed_var, values=list(tg.RATES.keys()),
                 state="readonly", width=20).grid(row=2, column=1, sticky="w", padx=(8, 0))

    # ── API Key ─────────────────────────────────────────────────────────────────
    c3 = card(body, "API Key  —  script generation only")
    unturf_var = tk.StringVar(value=cfg.get("unturf_key", ""))

    tk.Label(c3, text="Groq API Key", bg=CARD, fg=FG, anchor="w", width=14).grid(
        row=1, column=0, sticky="w", pady=4)
    key_entry = tk.Entry(c3, textvariable=unturf_var, show="*", bg=ENTRY, fg=FG,
                         insertbackground=FG, relief="flat",
                         highlightthickness=1, highlightbackground=BORDER)
    key_entry.grid(row=1, column=1, sticky="ew", padx=(8, 4))
    def toggle_key():
        key_entry.config(show="" if key_entry.cget("show") else "*")
    tk.Button(c3, text="Show", bg=BORDER, fg=FG, relief="flat", command=toggle_key,
              padx=8).grid(row=1, column=2)

    tk.Label(c3, text="Free  —  get your key at  console.groq.com  (no credit card needed)",
             bg=CARD, fg=FG_DIM, font=("Segoe UI", 8)).grid(
        row=2, column=0, columnspan=3, sticky="w", pady=(0, 4))

    def on_save_key():
        save_config({**load_config(),
                     "unturf_key": unturf_var.get().strip(),
                     "hf_token":   cfg.get("hf_token", ""),
                     "hf_model":   cfg.get("hf_model", "black-forest-labs/FLUX.1-dev")})
        status_var.set("Key saved.")
    tk.Button(c3, text="Save Key", bg=ACCENT, fg="white", relief="flat",
              command=on_save_key, padx=10).grid(row=3, column=1, sticky="e", pady=4)

    # ── Output folder ───────────────────────────────────────────────────────────
    c4 = card(body, "Output")
    out_var = tk.StringVar(value=cfg.get("output_dir",
                            os.path.join(PROJECT_DIR, "horror_videos")))
    tk.Label(c4, text="Save to", bg=CARD, fg=FG, anchor="w", width=10).grid(
        row=1, column=0, sticky="w", pady=4)
    tk.Entry(c4, textvariable=out_var, bg=ENTRY, fg=FG, insertbackground=FG,
             relief="flat", highlightthickness=1, highlightbackground=BORDER).grid(
        row=1, column=1, sticky="ew", padx=(8, 4))
    tk.Button(c4, text="Browse", bg=BORDER, fg=FG, relief="flat",
              command=lambda: out_var.set(filedialog.askdirectory() or out_var.get()),
              padx=8).grid(row=1, column=2)

    # ── Generate button ─────────────────────────────────────────────────────────
    btn_frame = tk.Frame(body, bg=BG)
    btn_frame.pack(fill=tk.X, padx=14, pady=8)
    gen_btn = tk.Button(btn_frame, text="GENERATE HORROR VIDEO",
                        bg=ACCENT, fg="white", relief="flat",
                        font=("Segoe UI", 12, "bold"),
                        pady=12, cursor="hand2")
    gen_btn.pack(fill=tk.X)

    # ── Log ─────────────────────────────────────────────────────────────────────
    log_frame = tk.Frame(body, bg=BG)
    log_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 6))
    log_box = scrolledtext.ScrolledText(
        log_frame, state="disabled", wrap=tk.WORD,
        font=("Consolas", 8), height=12,
        bg="#0d0d0d", fg="#00cc44", insertbackground=FG,
        relief="flat", highlightthickness=1, highlightbackground=BORDER)
    log_box.pack(fill=tk.BOTH, expand=True)

    # ── Status bar ──────────────────────────────────────────────────────────────
    status_var = tk.StringVar(value="Ready")
    tk.Label(root, textvariable=status_var, bg="#111", fg=FG_DIM,
             font=("Segoe UI", 8), anchor="w", padx=10).pack(
        side=tk.BOTTOM, fill=tk.X)

    # ── Logic ───────────────────────────────────────────────────────────────────
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
            status_var.set("Please enter a topic.")
            return
        if not ukey:
            status_var.set("Please enter your Groq API key (free at console.groq.com).")
            return
        if not os.path.exists(FFMPEG_EXE):
            status_var.set(f"ffmpeg not found: {FFMPEG_EXE}")
            return

        current_cfg = {
            **load_config(),
            "topic":       topic,
            "num_scenes":  scenes_var.get(),
            "subtitles":   sub_var.get(),
            "voice":       voice_var.get(),
            "speed":       speed_var.get(),
            "output_dir":  out_var.get().strip(),
            "unturf_key":  ukey,
            "last_topic":  topic,
            "default_scenes": scenes_var.get(),
        }
        save_config(current_cfg)

        gen_btn.config(state="disabled", text="Generating...")
        status_var.set("Running...")
        log_box.config(state="normal"); log_box.delete("1.0", tk.END); log_box.config(state="disabled")

        def worker():
            try:
                run_generation(current_cfg, log)
                root.after(0, lambda: status_var.set("Done!"))
            except Exception as e:
                msg = str(e)
                log(f"\nERROR: {msg}")
                root.after(0, lambda m=msg: status_var.set(f"Error: {m}"))
            finally:
                root.after(0, lambda: gen_btn.config(state="normal", text="GENERATE HORROR VIDEO"))

        threading.Thread(target=worker, daemon=True).start()

    gen_btn.config(command=on_generate)
    root.mainloop()


if __name__ == "__main__":
    build_gui()
