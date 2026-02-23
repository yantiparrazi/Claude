#!/usr/bin/env python3
"""
Conversation Illustrator - מאזין לשיחה ויוצר איורים
=====================================================
מקשיב לשיחה דרך המיקרופון, מתמלל בזמן אמת, וכל X שניות
שולח את התמלול ל-Gemini שיוצר פרומפט ל-Imagen 3 שמייצר
איור המוצג במסך מלא.
"""

import io
import os
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk
import speech_recognition as sr

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DEFAULT_STYLE = "artistic watercolor illustration, colorful and detailed"


class ConversationIllustrator:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("מאזין לשיחה | Conversation Illustrator")
        self.root.configure(bg="#1a1a2e")
        self.root.geometry("740x660")
        self.root.resizable(True, True)

        # App state
        self.is_running = False
        self.transcript_parts: list[str] = []
        self.transcript_lock = threading.Lock()
        self.stop_listening_func = None
        self.current_photo = None
        self.image_window = None
        self.client = None

        # Speech recognizer
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8

        self._setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─── UI ─────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg="#1a1a2e", pady=16)
        hdr.pack(fill=tk.X)
        tk.Label(
            hdr, text="מאזין לשיחה",
            font=("Arial", 26, "bold"), bg="#1a1a2e", fg="white",
        ).pack()
        tk.Label(
            hdr, text="Conversation Illustrator",
            font=("Arial", 13), bg="#1a1a2e", fg="#888",
        ).pack()

        # Settings panel
        sf = tk.LabelFrame(
            self.root, text="  הגדרות  ",
            bg="#16213e", fg="#aaa", font=("Arial", 11, "bold"),
            padx=18, pady=12, bd=1, relief=tk.GROOVE,
        )
        sf.pack(fill=tk.X, padx=22, pady=8)

        # API Key
        self.api_key_var = tk.StringVar(value=GEMINI_API_KEY)
        self._setting_row(sf, "Gemini API Key:", self.api_key_var,
                          width=38, show="*")

        # Interval
        f_int = tk.Frame(sf, bg="#16213e")
        f_int.pack(fill=tk.X, pady=4)
        tk.Label(f_int, text="משך כל תקופה:", bg="#16213e", fg="#ccc",
                 width=22, anchor="w").pack(side=tk.LEFT)
        self.interval_var = tk.StringVar(value="60")
        tk.Entry(
            f_int, textvariable=self.interval_var, width=8,
            bg="#0f3460", fg="white", insertbackground="white",
        ).pack(side=tk.LEFT, padx=4)
        tk.Label(f_int, text="שניות", bg="#16213e", fg="#aaa").pack(side=tk.LEFT)

        # Language
        f_lang = tk.Frame(sf, bg="#16213e")
        f_lang.pack(fill=tk.X, pady=4)
        tk.Label(f_lang, text="שפת הדיבור:", bg="#16213e", fg="#ccc",
                 width=22, anchor="w").pack(side=tk.LEFT)
        self.lang_var = tk.StringVar(value="he-IL")
        cb = ttk.Combobox(f_lang, textvariable=self.lang_var,
                          width=14, state="readonly")
        cb["values"] = ["he-IL", "en-US", "ar-SA", "ru-RU", "fr-FR", "de-DE"]
        cb.pack(side=tk.LEFT, padx=4)

        # Style
        f_style = tk.Frame(sf, bg="#16213e")
        f_style.pack(fill=tk.X, pady=4)
        tk.Label(f_style, text="סגנון האיור:", bg="#16213e", fg="#ccc",
                 width=22, anchor="w").pack(side=tk.LEFT)
        self.style_var = tk.StringVar(value="")
        tk.Entry(
            f_style, textvariable=self.style_var, width=38,
            bg="#0f3460", fg="white", insertbackground="white",
        ).pack(side=tk.LEFT, padx=4)
        tk.Label(f_style, text="(ריק = ברירת מחדל)", bg="#16213e",
                 fg="#555", font=("Arial", 9)).pack(side=tk.LEFT)

        # Start/Stop button
        ctrl = tk.Frame(self.root, bg="#1a1a2e", pady=12)
        ctrl.pack()
        self.start_btn = tk.Button(
            ctrl, text="▶  התחל",
            command=self._toggle,
            font=("Arial", 13, "bold"),
            bg="#43a047", fg="white",
            padx=22, pady=9,
            relief=tk.FLAT, cursor="hand2",
            activebackground="#388e3c", activeforeground="white",
        )
        self.start_btn.pack()

        # Status + timer
        stf = tk.Frame(self.root, bg="#1a1a2e")
        stf.pack(fill=tk.X, padx=22)
        self.status_var = tk.StringVar(value="מוכן להתחלה")
        tk.Label(stf, textvariable=self.status_var,
                 font=("Arial", 12), bg="#1a1a2e", fg="#FFC107").pack()
        self.timer_var = tk.StringVar(value="")
        tk.Label(stf, textvariable=self.timer_var,
                 font=("Arial", 42, "bold"), bg="#1a1a2e", fg="white").pack()

        # Transcript display
        tf = tk.LabelFrame(
            self.root, text="  תמלול שוטף  ",
            bg="#16213e", fg="#aaa", font=("Arial", 11, "bold"),
            padx=10, pady=8, bd=1, relief=tk.GROOVE,
        )
        tf.pack(fill=tk.BOTH, expand=True, padx=22, pady=(4, 14))
        self.transcript_box = tk.Text(
            tf, height=6, bg="#0a1628", fg="#e0e0e0",
            font=("Arial", 11), wrap=tk.WORD,
            state=tk.DISABLED, relief=tk.FLAT,
        )
        sb = ttk.Scrollbar(tf, command=self.transcript_box.yview)
        self.transcript_box.configure(yscrollcommand=sb.set)
        self.transcript_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

    def _setting_row(self, parent, label, var, width=38, show=None):
        f = tk.Frame(parent, bg="#16213e")
        f.pack(fill=tk.X, pady=4)
        tk.Label(f, text=label, bg="#16213e", fg="#ccc",
                 width=22, anchor="w").pack(side=tk.LEFT)
        kw = {"textvariable": var, "width": width,
              "bg": "#0f3460", "fg": "white", "insertbackground": "white"}
        if show:
            kw["show"] = show
        tk.Entry(f, **kw).pack(side=tk.LEFT, padx=4)

    # ─── UI helpers (thread-safe) ────────────────────────────────────────────

    def _set_status(self, msg: str):
        self.root.after(0, self.status_var.set, msg)

    def _set_timer(self, msg: str):
        self.root.after(0, self.timer_var.set, msg)

    def _append_transcript(self, text: str):
        def _do():
            self.transcript_box.configure(state=tk.NORMAL)
            self.transcript_box.insert(tk.END, text + " ")
            self.transcript_box.see(tk.END)
            self.transcript_box.configure(state=tk.DISABLED)
        self.root.after(0, _do)

    def _clear_transcript_ui(self):
        def _do():
            self.transcript_box.configure(state=tk.NORMAL)
            self.transcript_box.delete("1.0", tk.END)
            self.transcript_box.configure(state=tk.DISABLED)
        self.root.after(0, _do)

    # ─── Control ─────────────────────────────────────────────────────────────

    def _toggle(self):
        if self.is_running:
            self._stop()
        else:
            self._start()

    def _start(self):
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showerror("שגיאה", "נא להזין Gemini API Key")
            return

        try:
            interval = int(self.interval_var.get())
            assert interval >= 5
        except Exception:
            messagebox.showerror("שגיאה", "נא להזין מספר שניות תקין (מינימום 5)")
            return

        try:
            from google import genai  # noqa: F401 – validate import
            self.client = genai.Client(api_key=api_key)
        except ImportError:
            messagebox.showerror(
                "שגיאה",
                "חסרה ספרייה: הרץ  pip install google-genai",
            )
            return

        self.is_running = True
        self.start_btn.config(
            text="⏹  עצור", bg="#e53935", activebackground="#c62828"
        )
        self.transcript_parts = []
        self._start_listening()
        threading.Thread(target=self._cycle_loop, daemon=True).start()

    def _stop(self):
        self.is_running = False
        if self.stop_listening_func:
            self.stop_listening_func(wait_for_stop=False)
            self.stop_listening_func = None
        self.start_btn.config(
            text="▶  התחל", bg="#43a047", activebackground="#388e3c"
        )
        self._set_status("עצר")
        self._set_timer("")

    # ─── Background speech recognition ──────────────────────────────────────

    def _start_listening(self):
        lang = self.lang_var.get()

        def callback(recognizer, audio):
            try:
                text = recognizer.recognize_google(audio, language=lang)
                if text:
                    with self.transcript_lock:
                        self.transcript_parts.append(text)
                    self._append_transcript(text)
            except sr.UnknownValueError:
                pass
            except Exception as exc:
                print(f"[SR] {exc}")

        try:
            mic = sr.Microphone()
            with mic as src:
                self.recognizer.adjust_for_ambient_noise(src, duration=0.5)
            self.stop_listening_func = self.recognizer.listen_in_background(
                mic, callback, phrase_time_limit=12
            )
        except Exception as exc:
            messagebox.showerror("שגיאה", f"לא ניתן לגשת למיקרופון:\n{exc}")
            self._stop()

    # ─── Main cycle ──────────────────────────────────────────────────────────

    def _cycle_loop(self):
        """
        Each iteration:
          1. Count down the interval while background SR accumulates text.
          2. Grab the transcript, clear the buffer.
          3. Generate an image (blocking) – SR keeps running in parallel.
          4. Display the image fullscreen.
        """
        while self.is_running:
            interval = int(self.interval_var.get())
            self._set_status("🎙  מקליט...")

            end = time.time() + interval
            while time.time() < end and self.is_running:
                remaining = int(end - time.time())
                self._set_timer(
                    f"{remaining // 60:02d}:{remaining % 60:02d}"
                )
                time.sleep(0.4)

            if not self.is_running:
                break

            # Collect transcript for this window
            with self.transcript_lock:
                transcript = " ".join(self.transcript_parts)
                self.transcript_parts = []
            self._clear_transcript_ui()
            self._set_timer("")

            if transcript.strip():
                self._set_status("🤔  מנתח שיחה...")
                image = self._generate_image(transcript)
                if image and self.is_running:
                    self.root.after(0, self._show_image, image)
                    self._set_status(
                        "🖼  מציג איור | 🎙 מקשיב לתקופה הבאה..."
                    )
                elif self.is_running:
                    self._set_status("⚠  לא הצלחנו ליצור איור, ממשיך להקליט...")
            else:
                self._set_status("🔇  לא זוהה דיבור, ממשיך להקליט...")

    # ─── Image generation ────────────────────────────────────────────────────

    def _generate_image(self, transcript: str):
        from google import genai  # noqa: F811
        from google.genai import types

        style = self.style_var.get().strip() or DEFAULT_STYLE

        try:
            # Step 1: Ask Gemini to write a focused Imagen prompt
            self._set_status("🤔  בונה פרומפט לאיור...")
            prompt_resp = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=(
                    "You are an image prompt writer. "
                    "Based on the conversation transcript below, "
                    "write a vivid image generation prompt in English "
                    "(60–90 words) that visually captures the main topic or "
                    f"theme discussed. Illustration style: {style}.\n\n"
                    f"Conversation transcript:\n{transcript}\n\n"
                    "Return ONLY the image prompt, no other text."
                ),
            )
            img_prompt = prompt_resp.text.strip()
            print(f"[Prompt] {img_prompt[:140]}...")

            # Step 2: Generate image with Imagen 3
            self._set_status("🎨  מייצר איור עם Imagen 3...")
            img_resp = self.client.models.generate_images(
                model="imagen-3.0-generate-002",
                prompt=img_prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="16:9",
                    safety_filter_level="BLOCK_MEDIUM_AND_ABOVE",
                    person_generation="ALLOW_ADULT",
                ),
            )

            if img_resp.generated_images:
                raw = img_resp.generated_images[0].image.image_bytes
                return Image.open(io.BytesIO(raw))

            self._set_status("⚠  Imagen לא החזיר תמונה")
            return None

        except Exception as exc:
            err = str(exc)
            print(f"[Image gen] {err}")
            self._set_status(f"⚠  שגיאה: {err[:90]}")
            return None

    # ─── Fullscreen image display ────────────────────────────────────────────

    def _show_image(self, pil_image: Image.Image):
        # Close previous image window if open
        if self.image_window and self.image_window.winfo_exists():
            self.image_window.destroy()

        win = tk.Toplevel(self.root)
        self.image_window = win
        win.title("איור")
        win.attributes("-fullscreen", True)
        win.configure(bg="black")
        win.focus_set()

        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        ratio = min(sw / pil_image.width, sh / pil_image.height)
        resized = pil_image.resize(
            (int(pil_image.width * ratio), int(pil_image.height * ratio)),
            Image.LANCZOS,
        )
        self.current_photo = ImageTk.PhotoImage(resized)

        tk.Label(win, image=self.current_photo, bg="black").pack(expand=True)

        tk.Label(
            win,
            text="ESC / Space → סגור | ההקלטה לתקופה הבאה מתבצעת ברקע",
            font=("Arial", 11), bg="black", fg="#444",
        ).place(relx=0.5, rely=0.97, anchor="center")

        win.bind("<Escape>", lambda _: win.destroy())
        win.bind("<space>", lambda _: win.destroy())

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    def _on_close(self):
        self._stop()
        if self.image_window and self.image_window.winfo_exists():
            self.image_window.destroy()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ConversationIllustrator()
    app.run()
