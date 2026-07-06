"""
JARVIS — Iron Man HUD Interface
Real-time voice conversation with animated UI

Run this instead of jarvis.py for the full experience:
    python jarvis_ui.py

Features:
  - Dark futuristic Iron Man HUD design
  - Animated arc reactor / voice visualizer
  - Real-time transcript display
  - Sound effects (beep on wake, chime on response)
  - Deep male voice via Windows SAPI / pyttsx3
  - Continuous voice conversation — no button needed
  - Live status indicator (Idle / Listening / Thinking / Speaking)
"""

import os
import sys
import threading
import time
import queue
import math
import random
import subprocess
import platform
import datetime
import tkinter as tk
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

# ── Colour palette — Iron Man HUD ─────────────────────────────────────────────
BG          = "#050d1a"
BG2         = "#0a1628"
ACCENT      = "#00d4ff"
ACCENT2     = "#0088cc"
GOLD        = "#f5a623"
RED         = "#ff3b3b"
GREEN       = "#00ff88"
DIM         = "#1a3a5c"
TEXT        = "#b0d4f0"
TEXT_BRIGHT = "#e8f4ff"
TEXT_DIM    = "#3a6080"

class State:
    IDLE      = "IDLE"
    WAKE      = "WAKE"
    LISTENING = "LISTENING"
    THINKING  = "THINKING"
    SPEAKING  = "SPEAKING"

# ─── Sound effects ────────────────────────────────────────────────────────────
def _beep(freq, ms):
    try:
        if platform.system() == "Windows":
            import winsound
            winsound.Beep(max(37, min(32767, freq)), ms)
    except Exception:
        pass

def sound_wake():
    threading.Thread(target=lambda: (_beep(440,80), time.sleep(.06), _beep(660,120)), daemon=True).start()

def sound_listen():
    threading.Thread(target=lambda: _beep(880, 60), daemon=True).start()

def sound_done():
    threading.Thread(target=lambda: (_beep(660,80), time.sleep(.05), _beep(440,100)), daemon=True).start()

def sound_error():
    threading.Thread(target=lambda: _beep(200, 200), daemon=True).start()

# ─── Voice engine — deep male, Windows-safe ───────────────────────────────────
class VoiceEngine:
    """
    On Windows, pyttsx3 reuses a COM object that breaks when called from
    multiple threads or called twice quickly — causes letter-by-letter speech.
    Fix: create a FRESH engine instance for every single speak() call.
    This is slower to init but 100% reliable on Windows 10/11.
    """
    def __init__(self):
        self._lock   = threading.Lock()
        self._mode   = None
        self._voice_id = None
        self._init()

    def _init(self):
        try:
            import pyttsx3
            # Test init to find best voice — store voice ID only, not engine
            e = pyttsx3.init()
            voices = e.getProperty("voices") or []
            preferred = ["mark", "david", "richard", "george", "james", "paul"]
            chosen = None
            for v in voices:
                if any(p in v.name.lower() for p in preferred):
                    chosen = v; break
            if not chosen and voices:
                chosen = voices[0]
            self._voice_id = chosen.id if chosen else None
            self._mode = "pyttsx3"
            name = chosen.name if chosen else "default"
            print(f"🎙  Voice engine: pyttsx3 — {name}")
            # Properly shut down test instance
            try:
                e.stop()
            except Exception:
                pass
        except Exception as ex:
            print(f"[Voice] pyttsx3 unavailable ({ex}), using PowerShell")
            self._mode = "powershell"

    def _clean(self, text: str) -> str:
        """
        Prevent TTS from spelling out abbreviations letter by letter.
        J.A.R.V.I.S → Jarvis   J.A.R.V.I.S. → Jarvis.
        A.I. → AI
        """
        import re
        # J.A.R.V.I.S or J.A.R.V.I.S. at a word boundary
        cleaned = re.sub(
            r'\bJ\.A\.R\.V\.I\.S\b\.?', 'Jarvis', text, flags=re.IGNORECASE
        )
        # Generic 3-letter abbreviations like U.S.A.
        cleaned = re.sub(
            r'\b([A-Z])\.([A-Z])\.([A-Z])\.?\b', r'\1\2\3', cleaned
        )
        # Generic 2-letter abbreviations like A.I. — remove trailing dot too
        cleaned = re.sub(
            r'\b([A-Z])\.([A-Z])\.', r'\1\2 ', cleaned
        )
        return cleaned

    def speak(self, text: str, on_done=None):
        """Speak in background thread. Calls on_done() when finished."""
        text = self._clean(text)
        def _run():
            with self._lock:
                if self._mode == "pyttsx3":
                    try:
                        import pyttsx3
                        # Fresh engine every time — eliminates letter-by-letter bug
                        e = pyttsx3.init()
                        if self._voice_id:
                            e.setProperty("voice", self._voice_id)
                        e.setProperty("rate", 145)
                        e.setProperty("volume", 1.0)
                        e.say(text)
                        e.runAndWait()
                        try: e.stop()
                        except: pass
                        del e
                    except Exception as ex:
                        print(f"[Voice] pyttsx3 error: {ex} — falling back to PowerShell")
                        self._mode = "powershell"
                        self._ps(text)
                else:
                    self._ps(text)
            if on_done:
                on_done()
        threading.Thread(target=_run, daemon=True).start()

    def _ps(self, text: str):
        """Windows PowerShell built-in TTS — always works, no install needed."""
        safe = text.replace("'", " ").replace('"', ' ').replace('\n', ' ')
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Add-Type -AssemblyName System.Speech;"
                 f"$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                 f"try{{$s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Male)}}catch{{}};"
                 f"$s.Rate=-2;$s.Volume=100;$s.Speak('{safe}')"],
                check=False, timeout=60
            )
        except Exception as e:
            print(f"[Voice] PowerShell TTS failed: {e}")

# ─── Arc Reactor animator ─────────────────────────────────────────────────────
class ArcReactor:
    def __init__(self, canvas, cx, cy, r):
        self.canvas  = canvas
        self.cx, self.cy, self.r = cx, cy, r
        self.angle   = 0.0
        self.state   = State.IDLE
        self._pulse  = 0.0
        self._pd     = 1
        self._items  = []
        self._run    = True
        self._tick()

    def set_state(self, s): self.state = s

    def _col(self):
        return {State.IDLE:ACCENT2, State.WAKE:GOLD, State.LISTENING:GREEN,
                State.THINKING:GOLD, State.SPEAKING:ACCENT}.get(self.state, ACCENT)

    @staticmethod
    def _dim(c, f):
        c=c.lstrip("#")
        return f"#{int(int(c[0:2],16)*f):02x}{int(int(c[2:4],16)*f):02x}{int(int(c[4:6],16)*f):02x}"

    @staticmethod
    def _blend(c1, c2, t):
        t=max(0.,min(1.,t)); c1=c1.lstrip("#"); c2=c2.lstrip("#")
        return f"#{int(int(c1[0:2],16)*(1-t)+int(c2[0:2],16)*t):02x}{int(int(c1[2:4],16)*(1-t)+int(c2[2:4],16)*t):02x}{int(int(c1[4:6],16)*(1-t)+int(c2[4:6],16)*t):02x}"

    def _tick(self):
        if not self._run: return
        c=self.canvas; cx=self.cx; cy=self.cy; r=self.r; col=self._col()

        spd={"IDLE":.015,"WAKE":.05,"LISTENING":.07,"THINKING":.06,"SPEAKING":.08}.get(self.state,.02)
        self._pulse+=spd*self._pd
        if self._pulse>=1.: self._pd=-1
        if self._pulse<=0.: self._pd=1
        p=self._pulse

        for i in self._items:
            try: c.delete(i)
            except: pass
        self._items=[]

        def O(x0,y0,x1,y1,**kw): self._items.append(c.create_oval(x0,y0,x1,y1,**kw))
        def L(x0,y0,x1,y1,**kw): self._items.append(c.create_line(x0,y0,x1,y1,**kw))
        def A(x0,y0,x1,y1,**kw): self._items.append(c.create_arc(x0,y0,x1,y1,**kw))
        def T(x,y,**kw):         self._items.append(c.create_text(x,y,**kw))

        # outer glow rings
        for i,rr in enumerate([r+20,r+12,r+5]):
            O(cx-rr,cy-rr,cx+rr,cy+rr,outline=self._dim(col,.18-.05*i),width=1,fill="")

        # main ring
        O(cx-r,cy-r,cx+r,cy+r,outline=col,width=2,fill=BG2)

        # rotating tick marks
        rot_spd={"IDLE":.4,"WAKE":2,"LISTENING":2.5,"THINKING":4,"SPEAKING":2}.get(self.state,.5)
        for i in range(12):
            a=math.radians(self.angle+i*30); major=i%3==0
            x1=cx+math.cos(a)*(r-(8 if major else 4)); y1=cy+math.sin(a)*(r-(8 if major else 4))
            x2=cx+math.cos(a)*(r-1);                   y2=cy+math.sin(a)*(r-1)
            L(x1,y1,x2,y2,fill=col if major else self._dim(col,.4),width=2 if major else 1)

        # inner spinning segments
        sr=r-14
        for i in range(6):
            a0=self.angle*(1 if i%2==0 else -1)+i*60
            A(cx-sr,cy-sr,cx+sr,cy+sr,start=a0,extent=38,outline=self._dim(col,.5),width=1,style="arc")

        # core
        cr=int(r*.44)
        O(cx-cr,cy-cr,cx+cr,cy+cr,fill=self._blend(BG2,col,.12+p*.18),outline=col,width=2)
        dr=int(cr*.38)
        O(cx-dr,cy-dr,cx+dr,cy+dr,fill=self._blend(BG2,col,.35+p*.38),outline="")

        # state text
        lbl={"IDLE":"IDLE","WAKE":"LIVE","LISTENING":"HEAR","THINKING":"PROC","SPEAKING":"TALK"}.get(self.state,"")
        T(cx,cy,text=lbl,fill=col,font=("Courier",7,"bold"),anchor="center")

        # voice bars around reactor when active
        if self.state in (State.LISTENING, State.SPEAKING):
            nb=18
            for i in range(nb):
                ad=195+i*(150/(nb-1)); a=math.radians(ad)
                h=(0.25+p*.4+random.random()*.35) if self.state==State.SPEAKING else (0.15+random.random()*.5)
                h=min(1.,h)
                br=r+28
                bx=cx+math.cos(a)*br; by=cy+math.sin(a)*br
                bx2=cx+math.cos(a)*(br+5+h*18); by2=cy+math.sin(a)*(br+5+h*18)
                L(bx,by,bx2,by2,fill=self._blend(DIM,col,h),width=2)

        self.angle=(self.angle+rot_spd)%360
        c.after(33,self._tick)

    def stop(self): self._run=False

# ─── Transcript panel ─────────────────────────────────────────────────────────
class Transcript:
    def __init__(self, parent):
        self.text=tk.Text(parent,bg=BG2,fg=TEXT,font=("Courier",10),
                          relief="flat",bd=0,wrap="word",state="disabled",
                          padx=10,pady=8,spacing1=2,spacing3=4)
        self.text.pack(fill="both",expand=True)
        self.text.tag_config("you",    foreground=GREEN, font=("Courier",10,"bold"))
        self.text.tag_config("jarvis", foreground=ACCENT,font=("Courier",10))
        self.text.tag_config("sys",    foreground=TEXT_DIM,font=("Courier",9,"italic"))
        self.text.tag_config("ly",     foreground=GREEN,font=("Courier",10,"bold"))
        self.text.tag_config("lj",     foreground=GOLD, font=("Courier",10,"bold"))
        self.text.tag_config("ts",     foreground=TEXT_DIM,font=("Courier",8))
        self._n=0

    def add(self, spk, msg):
        self.text.configure(state="normal")
        ts=datetime.datetime.now().strftime("%H:%M:%S")
        if spk=="YOU":
            self.text.insert("end",f"\n[{ts}] ","ts")
            self.text.insert("end","YOU  › ","ly")
            self.text.insert("end",msg+"\n","you")
        elif spk=="JARVIS":
            self.text.insert("end",f"[{ts}] ","ts")
            self.text.insert("end","JARVIS › ","lj")
            self.text.insert("end",msg+"\n","jarvis")
        else:
            self.text.insert("end",f"  ··· {msg}\n","sys")
        self._n+=1
        if self._n>100: self.text.delete("1.0","3.0")
        self.text.configure(state="disabled")
        self.text.see("end")

# ─── Main HUD window ──────────────────────────────────────────────────────────
class JarvisHUD:
    def __init__(self):
        self.root=tk.Tk()
        self.root.title("J.A.R.V.I.S — Stark Industries")
        self.root.configure(bg=BG)
        self.root.geometry("920x660")
        self.root.minsize(780,540)
        try: self.root.attributes("-alpha",0.97)
        except: pass

        self._state   = State.IDLE
        self._voice   = VoiceEngine()
        self._ui_q    = queue.Queue()
        self._running = True
        self._mentor  = False
        self._handler = None
        self._thinking_active = False
        self._thinking_id     = 0
        self._session_turns   = 0

        self._build()
        self._start_engine()
        self._poll()
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self):
        r=self.root

        # ── top bar ──
        top=tk.Frame(r,bg=BG,height=50); top.pack(fill="x"); top.pack_propagate(False)
        tk.Label(top,text="  J.A.R.V.I.S",bg=BG,fg=ACCENT,font=("Courier",20,"bold")).pack(side="left")
        tk.Label(top,text="  STARK INDUSTRIES · PERSONAL AI ASSISTANT",bg=BG,fg=TEXT_DIM,font=("Courier",9)).pack(side="left")
        self._clk=tk.Label(top,text="",bg=BG,fg=TEXT_DIM,font=("Courier",10)); self._clk.pack(side="right",padx=14)
        self._tick_clock()
        tk.Frame(r,bg=DIM,height=1).pack(fill="x")

        # ── body ──
        body=tk.Frame(r,bg=BG); body.pack(fill="both",expand=True)

        # LEFT column
        left=tk.Frame(body,bg=BG,width=290); left.pack(side="left",fill="y"); left.pack_propagate(False)

        # reactor
        cv_size=230
        self._cv=tk.Canvas(left,width=cv_size,height=cv_size,bg=BG,highlightthickness=0)
        self._cv.pack(pady=(18,6))
        self._reactor=ArcReactor(self._cv,cv_size//2,cv_size//2,84)

        self._stvar=tk.StringVar(value="INITIALISING")
        tk.Label(left,textvariable=self._stvar,bg=BG,fg=ACCENT,font=("Courier",11,"bold")).pack()

        tk.Frame(left,bg=DIM,height=1).pack(fill="x",padx=14,pady=10)

        # sys info
        inf=tk.Frame(left,bg=BG2); inf.pack(fill="x",padx=12,pady=2)
        self._inf={}
        for k in ["CPU","RAM","BAT","TIME","SESS"]:
            row=tk.Frame(inf,bg=BG2); row.pack(fill="x",padx=8,pady=2)
            tk.Label(row,text=f"{k}:",bg=BG2,fg=TEXT_DIM,font=("Courier",9),width=5,anchor="w").pack(side="left")
            lbl=tk.Label(row,text="—",bg=BG2,fg=TEXT,font=("Courier",9),anchor="w"); lbl.pack(side="left")
            self._inf[k]=lbl
        self._inf["SESS"].config(text="0 turns")
        self._tick_sys()

        tk.Frame(left,bg=DIM,height=1).pack(fill="x",padx=14,pady=10)

        # buttons
        bc=dict(bg=BG2,fg=ACCENT,font=("Courier",9,"bold"),relief="flat",bd=0,
                padx=10,pady=7,cursor="hand2",activebackground=DIM,activeforeground=TEXT_BRIGHT)
        self._mic_btn=tk.Button(left,text="🎤  LISTEN NOW",command=self._manual_listen,**bc)
        self._mic_btn.pack(fill="x",padx=14,pady=3)
        self._mtr_btn=tk.Button(left,text="🧠  MENTOR MODE",command=self._toggle_mentor,**bc)
        self._mtr_btn.pack(fill="x",padx=14,pady=3)
        tk.Button(left,text="🗑   CLEAR MEMORY",command=self._clear_mem,**bc).pack(fill="x",padx=14,pady=3)
        tk.Button(left,text="✕   QUIT",command=self._close,**{**bc,"fg":RED}).pack(fill="x",padx=14,pady=(12,3))

        # RIGHT column
        right=tk.Frame(body,bg=BG); right.pack(side="left",fill="both",expand=True)

        hdr=tk.Frame(right,bg=BG2,height=30); hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr,text="  CONVERSATION LOG",bg=BG2,fg=TEXT_DIM,font=("Courier",9,"bold"),anchor="w").pack(side="left")
        self._mtr_lbl=tk.Label(hdr,text="",bg=BG2,fg=GOLD,font=("Courier",9,"bold")); self._mtr_lbl.pack(side="right",padx=10)

        tf=tk.Frame(right,bg=BG2,bd=1,relief="flat"); tf.pack(fill="both",expand=True,padx=6,pady=4)
        self._log=Transcript(tf)

        # input bar
        inp=tk.Frame(right,bg=BG,height=46); inp.pack(fill="x",pady=(0,6),padx=6); inp.pack_propagate(False)
        tk.Label(inp,text="›",bg=BG,fg=ACCENT,font=("Courier",15,"bold")).pack(side="left",padx=(8,4))
        self._ivar=tk.StringVar()
        entry=tk.Entry(inp,textvariable=self._ivar,bg=BG2,fg=TEXT_BRIGHT,
                       insertbackground=ACCENT,font=("Courier",11),relief="flat",bd=0)
        entry.pack(side="left",fill="both",expand=True,ipady=7)
        entry.bind("<Return>",self._type_submit)
        tk.Button(inp,text="SEND",command=self._type_submit,bg=ACCENT2,fg=BG,
                  font=("Courier",9,"bold"),relief="flat",bd=0,padx=14,pady=7,
                  cursor="hand2").pack(side="right",padx=4)

        tk.Frame(r,bg=DIM,height=1).pack(fill="x")
        bot=tk.Frame(r,bg=BG,height=24); bot.pack(fill="x"); bot.pack_propagate(False)
        tk.Label(bot,text='  Say "Hey Jarvis" anytime',bg=BG,fg=TEXT_DIM,font=("Courier",8)).pack(side="left")
        self._wlbl=tk.Label(bot,text="● WAKE WORD ACTIVE",bg=BG,fg=GREEN,font=("Courier",8,"bold"))
        self._wlbl.pack(side="right",padx=10)

    # ── clock & sys info ─────────────────────────────────────────────────────
    def _tick_clock(self):
        self._clk.config(text=datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.root.after(1000,self._tick_clock)

    def _tick_sys(self):
        try:
            import psutil
            cpu=psutil.cpu_percent(interval=None)
            ram=psutil.virtual_memory()
            bat=psutil.sensors_battery()
            self._inf["CPU"].config(text=f"{cpu:.0f}%",fg=RED if cpu>80 else ACCENT)
            self._inf["RAM"].config(text=f"{ram.percent:.0f}%",fg=RED if ram.percent>85 else TEXT)
            if bat:
                ch="⚡" if bat.power_plugged else "🔋"
                self._inf["BAT"].config(text=f"{ch}{bat.percent:.0f}%",fg=RED if bat.percent<15 else TEXT)
            else:
                self._inf["BAT"].config(text="desktop")
            self._inf["TIME"].config(text=datetime.datetime.now().strftime("%H:%M"))
        except Exception:
            pass
        self.root.after(5000,self._tick_sys)

    # ── state ────────────────────────────────────────────────────────────────
    def _set_state(self,s):
        self._state=s
        self._reactor.set_state(s)
        lbl,col={"IDLE":("STANDBY",TEXT_DIM),"WAKE":("ONLINE",GOLD),
                  "LISTENING":("LISTENING",GREEN),"THINKING":("PROCESSING",GOLD),
                  "SPEAKING":("SPEAKING",ACCENT)}.get(s,("—",TEXT_DIM))
        self.root.after(0,lambda: self._stvar.set(lbl))

    # ── engine ───────────────────────────────────────────────────────────────
    def _start_engine(self):
        threading.Thread(target=self._engine_thread,daemon=True).start()

    def _engine_thread(self):
        self._ui("sys","Initialising Jarvis core...")
        try:
            import jarvis as core
        except Exception as e:
            self._ui("sys",f"ERROR importing jarvis.py — {e}"); return

        api_key=os.environ.get("ANTHROPIC_API_KEY","")
        if not api_key:
            self._ui("sys","⚠  No ANTHROPIC_API_KEY — AI answers disabled. Run: setx ANTHROPIC_API_KEY \"your-key\"")

        self._core=core
        mem=core.Memory(); skills=core.SkillsManager(); plugins=core.PluginManager()
        ai=core.JarvisAI(api_key,mem)

        # Store wake event on self — cross-thread access requires it to be on
        # an object, not a closure variable, to avoid stale reference issues
        self._wake_event = threading.Event()
        def on_wake():
            print("[HUD] Wake word received — triggering conversation cycle")
            self._wake_event.set()
        wd=core.WakeWordDetector(on_wake,core.CONFIG)

        # Patch speak() so core engine uses our voice + UI
        def _speak(text,wake_det=None):
            if not text or not text.strip(): return
            self._ui("JARVIS",text)
            ev=threading.Event()
            self._set_state(State.SPEAKING)
            self._voice.speak(text,on_done=lambda:(self._set_state(State.IDLE),ev.set()))
            ev.wait(timeout=60)
            if wake_det: wake_det.resume()
        core.speak=_speak

        self._handler=core.CommandHandler(ai,mem,skills,plugins,wd)
        self._mem_ref=mem
        self._session_turns=0

        # Report which voice mode was detected
        self._ui("sys",f"Voice engine: {self._voice._mode}")

        voice_ok=core.load_whisper_model()
        self._core_listen=core.listen_microphone

        if voice_ok:
            wd.start()
            self._ui("sys","Whisper ready. Say 'Hey Jarvis' anytime.")
        else:
            self._ui("sys","Whisper unavailable — use the text input below.")
            self.root.after(0,lambda: self._wlbl.config(text="● WAKE WORD INACTIVE",fg=RED))

        # Startup greeting
        greet="Jarvis online. All systems operational. How may I assist you today, sir?"
        self._ui("JARVIS",greet)
        self._set_state(State.SPEAKING)
        sound_wake()
        ev=threading.Event()
        self._voice.speak(greet,on_done=lambda:(self._set_state(State.IDLE),ev.set()))
        ev.wait(timeout=25)

        # Update session counter in UI
        self._update_session_ui()

        # Main wake-word loop
        while self._running:
            if self._wake_event.wait(timeout=0.2):
                self._wake_event.clear()
                self._wake_cycle(wd)

    def _wake_cycle(self,wd):
        """Full conversation cycle: wake → greet → listen → respond → keep listening."""
        self._set_state(State.WAKE); sound_wake()

        greetings=[
            "Hello sir, I'm Jarvis, your personal assistant at work. How may I help you?",
            "Yes sir, I'm listening. What can I do for you?",
            "Jarvis here. Go ahead sir.",
            "Online and ready. What do you need?",
        ]
        # First wake always gets the full intro; subsequent ones are shorter
        g = greetings[0] if self._session_turns == 0 else random.choice(greetings[1:])
        self._ui("JARVIS",g)
        ev=threading.Event()
        self._set_state(State.SPEAKING)
        self._voice.speak(g,on_done=lambda:(self._set_state(State.IDLE),ev.set()))
        ev.wait(timeout=15)

        # First turn
        should_continue = self._one_turn(wd)

        # Auto-listen: keep the conversation flowing for up to 4 more turns
        # without needing "Hey Jarvis" again, as long as Jarvis got a response
        follow_up_count = 0
        while self._running and should_continue and follow_up_count < 4:
            # Small pause so it doesn't feel like it's rushing
            time.sleep(0.4)
            # Check if mentor mode wants to keep going indefinitely
            if self._mentor:
                should_continue = self._one_turn(wd)
            else:
                # In normal mode: offer one follow-up, then go idle
                if follow_up_count == 0:
                    self._ui("sys","Still listening for follow-up...")
                should_continue = self._one_turn(wd)
                follow_up_count += 1

        # Go fully idle — reactor slows down
        self._set_state(State.IDLE)

    def _one_turn(self,wd=None) -> bool:
        """
        Listen → ack → process → speak one full turn.
        Returns True if a real response was given (so caller can chain turns),
        False if nothing was heard or user said goodbye.
        """
        if not hasattr(self,"_core_listen"): return False

        self._set_state(State.LISTENING); sound_listen()
        self._ui("sys","Listening...")
        if wd: wd.pause()

        text=self._core_listen()

        if not text:
            self._set_state(State.IDLE); sound_error()
            self._ui("sys","Nothing heard — going idle. Say 'Hey Jarvis' to start again.")
            if wd: wd.resume()
            return False

        self._ui("YOU",text)
        self._session_turns+=1
        self._update_session_ui()

        # Instant "I got you" acknowledgement before any processing
        acks=["I got you.","Got it.","On it.","Sure thing.","Right away sir.",
              "Understood.","Of course.","Leave it to me."]
        ack=random.choice(acks)
        ev=threading.Event()
        self._set_state(State.SPEAKING)
        self._voice.speak(ack,on_done=lambda:(self._set_state(State.THINKING),ev.set()))
        ev.wait(timeout=8)

        # Show thinking dots in transcript
        self._show_thinking()

        try:
            resp=self._handler.handle(text)
        except Exception as e:
            resp=f"I ran into a snag — {e}"

        # Remove thinking dots
        self._hide_thinking()

        # Shutdown
        if resp=="SHUTDOWN":
            byes=["Goodbye sir, take care!","See you later sir. It was a pleasure.",
                  "Signing off. Stay brilliant, sir.","Goodbye! I'll be here when you need me."]
            bye=random.choice(byes)
            self._ui("JARVIS",bye)
            ev=threading.Event()
            self._set_state(State.SPEAKING)
            self._voice.speak(bye,on_done=lambda:ev.set())
            ev.wait(timeout=12)
            sound_done()
            self._running=False
            self.root.after(800,self.root.destroy)
            return False

        if resp:
            ev=threading.Event()
            self._set_state(State.SPEAKING)
            self._voice.speak(resp,on_done=lambda:(self._set_state(State.IDLE),ev.set()))
            ev.wait(timeout=90)
            sound_done()
            if wd: wd.resume()
            return True   # got a real response — caller may chain
        else:
            self._set_state(State.IDLE)
            if wd: wd.resume()
            return False

    # ── Thinking indicator ────────────────────────────────────────────────────
    def _show_thinking(self):
        """Add animated thinking indicator while processing."""
        self._thinking_active=True
        self._thinking_id=id(self)+self._session_turns
        self._ui("sys","··· thinking")
        self._animate_thinking(self._thinking_id, 0)

    def _animate_thinking(self, tid, step):
        if not hasattr(self,"_thinking_active") or not self._thinking_active:
            return
        if tid!=self._thinking_id: return
        dots=["··· thinking","···· thinking ·","····· thinking ··"]
        # Just pulse the status label — transcript entry already added
        if self._state==State.THINKING:
            self._stvar.set(["PROCESSING","PROCESSING ·","PROCESSING ··"][step%3])
        self.root.after(400, lambda: self._animate_thinking(tid, step+1))

    def _hide_thinking(self):
        self._thinking_active=False

    # ── Session counter ───────────────────────────────────────────────────────
    def _update_session_ui(self):
        turns=getattr(self,"_session_turns",0)
        label=f"{turns} turn" if turns==1 else f"{turns} turns"
        self.root.after(0, lambda: self._inf["SESS"].config(text=label))

    # ── Manual listen button ──────────────────────────────────────────────────
    def _manual_listen(self):
        if self._state not in (State.IDLE, State.WAKE):
            return  # don't double-trigger
        threading.Thread(target=lambda: self._one_turn(None), daemon=True).start()

    def _type_submit(self,event=None):
        text=self._ivar.get().strip()
        if not text: return
        if self._state in (State.LISTENING, State.THINKING):
            return  # busy — ignore
        self._ivar.set("")
        self._ui("YOU",text)
        self._session_turns+=1
        self._update_session_ui()

        def _run():
            self._set_state(State.THINKING)
            self._thinking_active=True
            self._show_thinking()
            try:
                resp=self._handler.handle(text)
            except Exception as e:
                resp=f"Error: {e}"
            self._hide_thinking()

            if resp and resp!="SHUTDOWN":
                ev=threading.Event()
                self._set_state(State.SPEAKING)
                self._voice.speak(resp,on_done=lambda:(self._set_state(State.IDLE),ev.set()))
                ev.wait(timeout=90)
                sound_done()
            elif resp=="SHUTDOWN":
                bye=random.choice(["Goodbye sir!","See you later!","Signing off."])
                self._ui("JARVIS",bye)
                ev=threading.Event()
                self._voice.speak(bye,on_done=lambda:ev.set()); ev.wait(timeout=8)
                self._running=False; self.root.after(600,self.root.destroy)
            else:
                self._set_state(State.IDLE)
        threading.Thread(target=_run,daemon=True).start()

    def _toggle_mentor(self):
        self._mentor=not self._mentor
        if self._handler:
            self._handler.mentor_mode=self._mentor
            if hasattr(self._handler,"ai"): self._handler.ai.mentor_active=self._mentor
        if self._mentor:
            self._mtr_btn.config(fg=GOLD)
            self._mtr_lbl.config(text="● MENTOR MODE")
            msg=("Mentor mode on. I'm here as your friend. "
                 "Talk freely — I'll keep listening turn after turn without you needing to say hey Jarvis.")
        else:
            self._mtr_btn.config(fg=ACCENT)
            self._mtr_lbl.config(text="")
            msg="Back to standard mode. Say hey Jarvis whenever you need me."
        self._ui("JARVIS",msg)
        ev=threading.Event()
        self._voice.speak(msg,on_done=lambda:ev.set())

    def _clear_mem(self):
        if hasattr(self,"_mem_ref"): self._mem_ref.clear()
        self._session_turns=0
        self._update_session_ui()
        self._ui("sys","Memory cleared.")
        self._voice.speak("Memory wiped. Starting fresh, sir.")

    # ── UI queue ─────────────────────────────────────────────────────────────
    def _ui(self,spk,msg):
        self._ui_q.put((spk,msg))

    def _poll(self):
        while not self._ui_q.empty():
            try:
                spk,msg=self._ui_q.get_nowait()
                self._log.add(spk,msg)
            except queue.Empty:
                break
        self.root.after(80,self._poll)

    # ── close ─────────────────────────────────────────────────────────────────
    def _close(self):
        self._running=False
        try: self._reactor.stop()
        except: pass
        if hasattr(self,"_mem_ref"): self._mem_ref.save()
        try: self.root.destroy()
        except: pass

    def run(self): self.root.mainloop()

def main():
    print("""
╔══════════════════════════════════════════════════╗
║   J.A.R.V.I.S  —  Iron Man HUD  Interface       ║
║   Real-time voice · Deep voice · Arc Reactor    ║
╚══════════════════════════════════════════════════╝
    """)
    JarvisHUD().run()

if __name__=="__main__":
    main()
