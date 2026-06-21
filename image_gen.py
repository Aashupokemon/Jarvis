"""
JARVIS — Image Generation Feature

Listens for voice input describing an image, enhances the prompt using
Claude AI, then generates the image using one of several supported backends:

  1. Stable Diffusion (local, free, via diffusers — best quality, needs GPU/CPU)
  2. Pollinations.ai (free, no API key, cloud — fastest to get started)
  3. Hugging Face Inference API (free tier, needs HF token)
  4. OpenAI DALL-E (paid, best quality — needs OpenAI API key)

The system auto-detects which backend is available and uses the best one.
Generated images are saved to ~/Pictures/jarvis_images/ and auto-opened.

Trigger phrases (all routed here from CommandHandler):
  "generate an image of ..."
  "create an image of ..."
  "draw ..."
  "paint ..."
  "imagine ..."
  "make a picture of ..."
  "show me ..."  (visual intent)
  "generate image"  (prompts for voice description)
"""

import os
import io
import re
import json
import base64
import datetime
import platform
import subprocess
import threading
import webbrowser
import requests
from pathlib import Path


IMAGES_DIR = Path.home() / "Pictures" / "jarvis_images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


# ─── Prompt Enhancer ─────────────────────────────────────────────────────────
class PromptEnhancer:
    """Uses Claude to turn a short voice description into a rich image prompt."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def enhance(self, raw_prompt: str, style: str = "photorealistic") -> str:
        system = (
            "You are an expert AI image prompt engineer. "
            "Transform the user's short description into a detailed, vivid image generation prompt. "
            "Add relevant details about lighting, composition, style, quality, and atmosphere. "
            "Keep it under 120 words. Return ONLY the enhanced prompt — no explanation, "
            "no preamble, no quotes. Make it rich and specific."
        )
        user = f"Style: {style}\nDescription: {raw_prompt}\n\nEnhanced prompt:"
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 200,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
                timeout=10,
            )
            data = resp.json()
            enhanced = data["content"][0]["text"].strip()
            return enhanced
        except Exception:
            return raw_prompt  # fallback to original if Claude is unreachable


# ─── Backend: Pollinations.ai (free, no key) ──────────────────────────────────
class PollinationsBackend:
    name = "Pollinations.ai (free)"
    requires_key = False

    def is_available(self) -> bool:
        try:
            r = requests.get("https://pollinations.ai", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def generate(self, prompt: str, width: int = 1024, height: int = 1024,
                 seed: int = None) -> bytes:
        """Returns raw PNG bytes."""
        import urllib.parse
        encoded = urllib.parse.quote(prompt)
        seed_str = str(seed) if seed else str(int(datetime.datetime.now().timestamp()))
        url = (f"https://image.pollinations.ai/prompt/{encoded}"
               f"?width={width}&height={height}&seed={seed_str}&nologo=true&enhance=true")
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        return resp.content


# ─── Backend: Hugging Face Inference API (free tier) ─────────────────────────
class HuggingFaceBackend:
    name = "Hugging Face (free tier)"
    requires_key = True
    DEFAULT_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"

    def __init__(self, token: str = "", model: str = ""):
        self.token = token or os.environ.get("HF_TOKEN", "")
        self.model = model or self.DEFAULT_MODEL

    def is_available(self) -> bool:
        return bool(self.token)

    def generate(self, prompt: str, width: int = 1024, height: int = 1024,
                 negative_prompt: str = "") -> bytes:
        api_url = f"https://api-inference.huggingface.co/models/{self.model}"
        payload = {
            "inputs": prompt,
            "parameters": {
                "width": width,
                "height": height,
                "num_inference_steps": 30,
                "guidance_scale": 7.5,
            }
        }
        if negative_prompt:
            payload["parameters"]["negative_prompt"] = negative_prompt

        resp = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {self.token}"},
            json=payload,
            timeout=90,
        )
        resp.raise_for_status()
        return resp.content


# ─── Backend: OpenAI DALL-E 3 ────────────────────────────────────────────────
class DALLEBackend:
    name = "OpenAI DALL-E 3"
    requires_key = True

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, size: str = "1024x1024",
                 quality: str = "standard") -> bytes:
        resp = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "dall-e-3",
                "prompt": prompt,
                "n": 1,
                "size": size,
                "quality": quality,
                "response_format": "b64_json",
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return base64.b64decode(data["data"][0]["b64_json"])


# ─── Backend: Local Stable Diffusion (diffusers) ─────────────────────────────
class LocalSDBackend:
    name = "Local Stable Diffusion"
    requires_key = False

    def __init__(self, model_id: str = "runwayml/stable-diffusion-v1-5"):
        self.model_id = model_id
        self._pipe = None

    def is_available(self) -> bool:
        try:
            import torch
            import diffusers
            return True
        except ImportError:
            return False

    def _load(self):
        if self._pipe:
            return
        import torch
        from diffusers import StableDiffusionPipeline, DPMSolverMultistepScheduler

        print(f"[ImageGen] Loading local Stable Diffusion model '{self.model_id}'...")
        print("           (First load downloads ~5GB — subsequent loads are instant)")
        pipe = StableDiffusionPipeline.from_pretrained(
            self.model_id,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        )
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        pipe = pipe.to(device)
        print(f"[ImageGen] Model loaded on {device.upper()}.")
        self._pipe = pipe

    def generate(self, prompt: str, negative_prompt: str = "",
                 steps: int = 25, guidance: float = 7.5,
                 width: int = 512, height: int = 512) -> bytes:
        self._load()
        result = self._pipe(
            prompt,
            negative_prompt=negative_prompt or "blurry, low quality, deformed, ugly",
            num_inference_steps=steps,
            guidance_scale=guidance,
            width=width,
            height=height,
        )
        img = result.images[0]
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


# ─── Image Viewer ─────────────────────────────────────────────────────────────
def open_image(path: str):
    """Open the saved image with the system's default viewer."""
    os_name = platform.system()
    try:
        if os_name == "Darwin":
            subprocess.Popen(["open", path])
        elif os_name == "Linux":
            subprocess.Popen(["xdg-open", path])
        elif os_name == "Windows":
            os.startfile(path)
    except Exception:
        webbrowser.open(f"file://{path}")


# ─── Main ImageGenerator class ────────────────────────────────────────────────
class ImageGenerator:
    """
    Orchestrates prompt enhancement → backend selection → generation → save/open.
    Auto-picks the best available backend.
    Priority: Local SD > DALL-E > HuggingFace > Pollinations
    """

    TRIGGER_PHRASES = [
        "generate an image", "generate image", "create an image", "create image",
        "draw a", "draw an", "draw me", "paint a", "paint an", "paint me",
        "imagine a", "imagine an", "make a picture", "make an image",
        "generate a picture", "create a picture", "sketch a", "sketch an",
        "render a", "render an", "visualize a", "visualize an",
    ]

    STYLE_MAP = {
        "realistic":      "photorealistic, 8k, ultra-detailed",
        "photorealistic": "photorealistic, 8k, DSLR quality",
        "anime":          "anime style, Studio Ghibli, vibrant",
        "cartoon":        "cartoon style, colorful, fun",
        "oil painting":   "oil painting, classical art, textured brushwork",
        "watercolor":     "watercolor painting, soft colors, artistic",
        "digital art":    "digital art, concept art, vibrant colors",
        "sketch":         "pencil sketch, black and white, detailed linework",
        "fantasy":        "fantasy art, epic, magical, cinematic",
        "cyberpunk":      "cyberpunk, neon lights, futuristic, dark atmosphere",
        "minimalist":     "minimalist, clean, simple, flat design",
    }

    def __init__(self, anthropic_api_key: str, config: dict = None):
        self.enhancer = PromptEnhancer(anthropic_api_key)
        self.config   = config or {}
        self.backend  = self._pick_backend()
        self._generating = False  # prevent double-triggers

    def _pick_backend(self):
        """Select best available backend in priority order."""
        candidates = [
            LocalSDBackend(),
            DALLEBackend(self.config.get("openai_api_key", "")),
            HuggingFaceBackend(self.config.get("hf_token", "")),
            PollinationsBackend(),
        ]
        for b in candidates:
            if b.is_available():
                print(f"[ImageGen] Using backend: {b.name}")
                return b
        return PollinationsBackend()  # always available as last resort

    def is_image_command(self, text: str) -> bool:
        t = text.lower().strip()
        return any(phrase in t for phrase in self.TRIGGER_PHRASES)

    def extract_prompt(self, text: str) -> str:
        """Strip the trigger phrase and extract the actual description."""
        t = text.strip()
        for phrase in sorted(self.TRIGGER_PHRASES, key=len, reverse=True):
            idx = t.lower().find(phrase)
            if idx != -1:
                after = t[idx + len(phrase):].strip()
                # Remove leading "of", "a", "an", "the"
                after = re.sub(r"^(of|a|an|the)\s+", "", after, flags=re.I)
                if after:
                    return after
        return t  # fallback: use full text as prompt

    def detect_style(self, text: str) -> tuple[str, str]:
        """Return (style_label, style_suffix) if a style keyword is found."""
        t = text.lower()
        for style_key, style_suffix in self.STYLE_MAP.items():
            if style_key in t:
                return style_key, style_suffix
        return "photorealistic", self.STYLE_MAP["photorealistic"]

    def generate(self, raw_prompt: str, speak_fn=None, style: str = None) -> str:
        """
        Full pipeline: enhance prompt → generate → save → open → return status.
        speak_fn: optional callback to narrate progress (passed from CommandHandler)
        Returns a user-facing response string.
        """
        if self._generating:
            return "I'm already generating an image. Please wait."

        self._generating = True

        def _run():
            try:
                # Detect style from prompt if not explicitly set
                style_key, style_suffix = self.detect_style(raw_prompt)
                effective_style = style or style_key

                if speak_fn:
                    speak_fn(f"Got it. Enhancing your prompt and generating a {effective_style} image.")

                # 1. Enhance prompt with Claude
                enhanced = self.enhancer.enhance(raw_prompt, effective_style)
                full_prompt = f"{enhanced}, {style_suffix}"
                print(f"\n[ImageGen] Raw prompt:      {raw_prompt}")
                print(f"[ImageGen] Enhanced prompt: {full_prompt}")

                if speak_fn:
                    speak_fn("Generating now — this may take a moment.")

                # 2. Generate
                image_bytes = self.backend.generate(full_prompt)

                # 3. Save
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = re.sub(r"[^a-z0-9]+", "_", raw_prompt.lower())[:40]
                filename = f"jarvis_{safe_name}_{ts}.png"
                filepath = IMAGES_DIR / filename
                filepath.write_bytes(image_bytes)

                print(f"[ImageGen] Saved to {filepath}")

                # 4. Open the image
                open_image(str(filepath))

                if speak_fn:
                    speak_fn(f"Done! Your image has been generated and saved to the Pictures folder.")

                return str(filepath)

            except requests.exceptions.Timeout:
                msg = "Image generation timed out. The server might be busy — try again."
                if speak_fn:
                    speak_fn(msg)
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 503:
                    msg = "The image model is loading. Give it 20 seconds and try again."
                else:
                    msg = f"Image generation failed: {e}"
                if speak_fn:
                    speak_fn(msg)
            except Exception as e:
                msg = f"Couldn't generate the image. Error: {e}"
                print(f"[ImageGen] Error: {e}")
                if speak_fn:
                    speak_fn(msg)
            finally:
                self._generating = False

        # Run in a background thread so the voice response returns immediately
        t = threading.Thread(target=_run, daemon=True)
        t.start()

        # Return immediately — the thread will speak when done
        return f"On it! Generating a {style or 'photorealistic'} image of: {raw_prompt}."

    def list_recent_images(self, n: int = 5) -> str:
        """List recently generated images."""
        files = sorted(IMAGES_DIR.glob("jarvis_*.png"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            return "No images generated yet."
        names = [f.name for f in files[:n]]
        return f"Recent images in {IMAGES_DIR}: " + ", ".join(names)

    def open_last_image(self) -> str:
        """Open the most recently generated image."""
        files = sorted(IMAGES_DIR.glob("jarvis_*.png"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            return "No images generated yet."
        open_image(str(files[0]))
        return f"Opening the last image: {files[0].name}"

    def open_images_folder(self) -> str:
        """Open the images folder in the file manager."""
        open_image(str(IMAGES_DIR))
        return f"Opening images folder: {IMAGES_DIR}"

    def switch_backend(self, name: str) -> str:
        """Manually switch backend by keyword."""
        name = name.lower()
        if "pollinations" in name or "free" in name:
            self.backend = PollinationsBackend()
        elif "hugging" in name or "hf" in name:
            self.backend = HuggingFaceBackend(self.config.get("hf_token", ""))
        elif "dalle" in name or "openai" in name or "dall-e" in name:
            self.backend = DALLEBackend(self.config.get("openai_api_key", ""))
        elif "local" in name or "stable diffusion" in name or "sd" in name:
            self.backend = LocalSDBackend()
        else:
            return f"Unknown backend '{name}'. Options: pollinations, huggingface, dalle, local."
        return f"Switched to {self.backend.name}."


# ─── Router helper (called from CommandHandler) ───────────────────────────────
def route_image_command(text: str, generator: ImageGenerator, speak_fn=None) -> str | None:
    """
    Returns a response string if the text is an image command, else None.
    speak_fn is passed so the background thread can narrate progress.
    """
    t = text.lower().strip()

    # Show recent images
    if any(k in t for k in ["show my images", "list images", "my generated images", "recent images"]):
        return generator.list_recent_images()

    # Open last generated image
    if any(k in t for k in ["open last image", "show last image", "view last image"]):
        return generator.open_last_image()

    # Open images folder
    if any(k in t for k in ["open images folder", "images folder", "where are my images"]):
        return generator.open_images_folder()

    # Switch backend
    if "switch image backend" in t or "use pollinations" in t or "use dalle" in t \
            or "use hugging" in t or "use local" in t:
        backend_name = t.replace("switch image backend to", "").replace("use", "").strip()
        return generator.switch_backend(backend_name)

    # Image generation trigger
    if generator.is_image_command(text):
        prompt = generator.extract_prompt(text)
        if not prompt or len(prompt) < 3:
            return ("What would you like me to generate? Say something like: "
                    "'generate an image of a sunset over the ocean'.")
        return generator.generate(prompt, speak_fn=speak_fn)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION SNIPPET — already wired into jarvis.py's CommandHandler
# via the str_replace step below. No manual edits needed.
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Quick standalone test
    import sys
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("Set ANTHROPIC_API_KEY to test.")
        sys.exit(1)

    gen = ImageGenerator(api_key)
    print("Backend:", gen.backend.name)
    print("Trigger test:", gen.is_image_command("generate an image of a dragon"))
    print("Prompt extract:", gen.extract_prompt("draw me a sunset over the mountains"))

    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        print(f"Generating: {prompt}")
        result = gen.generate(prompt, speak_fn=print)
        input("Press Enter after generation completes...")
