#!/usr/bin/env python3
"""
Conversation Illustrator
מאזין לשיחה ויוצר איורים אוטומטית עם Gemini + Imagen (Nano Banana)
"""

import tkinter as tk
from tkinter import messagebox
import threading
import time
import io
import os

import speech_recognition as sr
from PIL import Image, ImageTk
from google import genai
from google.genai import types


# ─────────────────────────────────────────── Constants
DEFAULT_STYLE    = "colorful digital art illustration, vivid, detailed, professional"
GEMINI_MODEL     = "gemini-2.0-flash"
IMAGEN_MODEL     = "imagen-3.0-generate-001"
PLACEHOLDER_STYLE = "ברירת מחדל – ציור דיגיטלי צבעוני"


# ─────────────────────────────────────────── Main App
class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Conversation Illustrator")
        self.root.geometry("520x430")
        self.root.resizable(False, False)
        self.root.configure(bg="#0f0f23")

        self.running    = False
        self.client     = None
        self.recognizer = sr.Recognizer()
        self.img_win    = None
        self.img_label  = None

        self._build_ui()

    # ──────────────────────────────────────────── UI
    def _build_ui(self):
        # Header
        tk.Label(
            self.root, text="Conversation Illustrator",
            font=("Segoe UI", 18, "bold"), bg="#0f0f23", fg="#ffffff"
        ).pack(pady=(20, 2))
        tk.Label(
            self.root, text="מאזין לשיחה ויוצר איורים אוטומטית",
            font=("Segoe UI", 10), bg="#0f0f23", fg="#888888"
        ).pack(pady=(0, 14))

        # Form
        form = tk.Frame(self.root, bg="#1a1a3e", padx=20, pady=16)
        form.pack(fill=tk.X, padx=28)
        form.columnconfigure(1, weight=1)

        def lbl(row, text):
            tk.Label(form, text=text, font=("Segoe UI", 10),
                     bg="#1a1a3e", fg="#cccccc", anchor="e", width=16
                     ).grid(row=row, column=0, sticky=tk.E, padx=4, pady=6)

        def entry(row, var, show=None, width=32):
            kw = dict(textvariable=var, width=width,
                      bg="#2a2a5e", fg="white", insertbackground="white",
                      relief=tk.FLAT, highlightthickness=1,
                      highlightbackground="#444", highlightcolor="#76c7c0")
            if show:
                kw["show"] = show
            e = tk.Entry(form, **kw)
            e.grid(row=row, column=1, sticky=tk.W, padx=8, pady=6)
            return e

        # API key
        self.api_var = tk.StringVar(value=os.environ.get("GEMINI_API_KEY", ""))
        lbl(0, "Gemini API Key:")
        entry(0, self.api_var, show="*")

        # Interval
        self.interval_var = tk.StringVar(value="60")
        lbl(1, "מחזור (שניות):")
        entry(1, self.interval_var, width=10)

        # Style
        self.style_var = tk.StringVar(value="")
        lbl(2, "סגנון איור:")
        style_entry = entry(2, self.style_var)
        self._placeholder(style_entry, PLACEHOLDER_STYLE)

        # Status
        self.status_var = tk.StringVar(value="מוכן")
        tk.Label(self.root, textvariable=self.status_var,
                 font=("Segoe UI", 11), bg="#0f0f23", fg="#76c7c0"
                 ).pack(pady=(14, 0))

        # Timer
        self.timer_var = tk.StringVar(value="--:--")
        tk.Label(self.root, textvariable=self.timer_var,
                 font=("Segoe UI", 30, "bold"), bg="#0f0f23", fg="#e94560"
                 ).pack()

        # Last transcript preview
        self.transcript_var = tk.StringVar(value="")
        tk.Label(self.root, textvariable=self.transcript_var,
                 font=("Segoe UI", 9), bg="#0f0f23", fg="#555555",
                 wraplength=480
                 ).pack(pady=2)

        # Start / Stop button
        self.btn = tk.Button(
            self.root, text="▶   התחל",
            font=("Segoe UI", 13, "bold"),
            bg="#e94560", fg="white", relief=tk.FLAT,
            padx=28, pady=10, cursor="hand2",
            command=self.toggle
        )
        self.btn.pack(pady=14)

    def _placeholder(self, entry_widget, text):
        """Attach placeholder text behaviour to an Entry."""
        def on_in(_):
            if self.style_var.get() == text:
                self.style_var.set("")
                entry_widget.config(fg="white")

        def on_out(_):
            if not self.style_var.get():
                self.style_var.set(text)
                entry_widget.config(fg="#888888")

        self.style_var.set(text)
        entry_widget.config(fg="#888888")
        entry_widget.bind("<FocusIn>",  on_in)
        entry_widget.bind("<FocusOut>", on_out)

    # ──────────────────────────────────────── Control
    def toggle(self):
        if self.running:
            self._stop()
        else:
            self._start()

    def _start(self):
        api_key = self.api_var.get().strip()
        if not api_key:
            messagebox.showerror("שגיאה", "נא להזין Gemini API Key")
            return
        try:
            interval = int(self.interval_var.get())
            assert interval > 0
        except (ValueError, AssertionError):
            messagebox.showerror("שגיאה", "נא להזין מספר שניות חיובי")
            return

        self.client  = genai.Client(api_key=api_key)
        self.running = True
        self.btn.config(text="⏹   עצור", bg="#457b9d")
        threading.Thread(target=self._loop, daemon=True).start()

    def _stop(self):
        self.running = False
        self.btn.config(text="▶   התחל", bg="#e94560")
        self._status("עצר")
        self._timer(0, 0)

    # ──────────────────────────────────────── Core loop
    def _loop(self):
        interval = int(self.interval_var.get())
        while self.running:
            transcript = self._record(interval)
            if not self.running:
                break
            if transcript.strip():
                self._generate(transcript)
            else:
                self._status("לא זוהה דיבור – מאזין מחדש")

    # ──────────────────────────────────────── Recording
    def _record(self, duration: int) -> str:
        parts    = []
        end_time = time.time() + duration

        while time.time() < end_time and self.running:
            remaining = int(end_time - time.time())
            self._timer(*divmod(remaining, 60))
            self._status("מאזין לשיחה...")

            try:
                with sr.Microphone() as src:
                    self.recognizer.adjust_for_ambient_noise(src, duration=0.3)
                    timeout = min(5, max(1, remaining))
                    audio   = self.recognizer.listen(
                        src, timeout=timeout, phrase_time_limit=10
                    )

                # Try Hebrew first, then English
                text = ""
                for lang in ("iw-IL", "en-US"):
                    try:
                        text = self.recognizer.recognize_google(audio, language=lang)
                        break
                    except sr.UnknownValueError:
                        continue

                if text:
                    parts.append(text)
                    self._set_transcript(" | ".join(parts[-4:]))

            except sr.WaitTimeoutError:
                pass
            except Exception as exc:
                print(f"[record] {exc}")

        self._timer(0, 0)
        return " ".join(parts)

    # ──────────────────────────────────── Image generation
    def _generate(self, transcript: str):
        raw_style   = self.style_var.get().strip()
        style       = DEFAULT_STYLE if (not raw_style or raw_style == PLACEHOLDER_STYLE) else raw_style

        try:
            # ── Step 1: Gemini crafts the image prompt ──────────────────
            self._status("Gemini מנסח פרומפט לתמונה...")
            resp = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=(
                    "You are an expert image-prompt engineer.\n"
                    "Read the conversation transcript below and write ONE vivid, "
                    "detailed image-generation prompt in English that visually captures "
                    f"the main topic or theme. Art style: {style}.\n\n"
                    f"Transcript:\n{transcript}\n\n"
                    "Output ONLY the image prompt – no intro, no explanation, no quotes."
                )
            )
            image_prompt = resp.text.strip()
            print(f"[prompt] {image_prompt}")

            # ── Step 2: Imagen generates the image ──────────────────────
            self._status("מייצר תמונה עם Imagen (Nano Banana)...")
            result = self.client.models.generate_images(
                model=IMAGEN_MODEL,
                prompt=image_prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="16:9",
                )
            )

            if result.generated_images:
                raw_bytes = result.generated_images[0].image.image_bytes
                img       = Image.open(io.BytesIO(raw_bytes))
                self.root.after(0, lambda i=img: self._show_image(i))
                self._status("מציג איור ✓")
            else:
                self._status("לא נוצרה תמונה (ייתכן שנחסמה בפילטר בטיחות)")

        except Exception as exc:
            self._status(f"שגיאה: {str(exc)[:80]}")
            print(f"[generate] {exc}")

    # ──────────────────────────────────── Fullscreen window
    def _show_image(self, image: Image.Image):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        image = image.resize((sw, sh), Image.LANCZOS)
        photo = ImageTk.PhotoImage(image)

        # Create or reuse the fullscreen window
        if self.img_win is None or not self.img_win.winfo_exists():
            self.img_win   = tk.Toplevel(self.root)
            self.img_win.attributes("-fullscreen", True)
            self.img_win.configure(bg="black")
            self.img_win.bind("<Escape>", lambda _e: self.img_win.destroy())
            self.img_label = tk.Label(self.img_win, bg="black")
            self.img_label.pack(fill=tk.BOTH, expand=True)

        self.img_label.configure(image=photo)
        self.img_label.image = photo  # keep reference – prevent GC

    # ──────────────────────────────────────── Helpers
    def _status(self, msg: str):
        self.root.after(0, lambda: self.status_var.set(msg))

    def _timer(self, mins: int, secs: int):
        self.root.after(0, lambda: self.timer_var.set(f"{mins:02d}:{secs:02d}"))

    def _set_transcript(self, text: str):
        self.root.after(0, lambda: self.transcript_var.set(text))

    # ─────────────────────────────────────────── Run
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
