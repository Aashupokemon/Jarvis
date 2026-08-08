"""
JARVIS — Minimal Voice UI
Full-screen dark glass, single glowing orb reacts to voice state.
No buttons, no transcript, no clutter — pure voice control.
"""
import os,sys,threading,time,queue,math,random,subprocess,platform
import datetime,tkinter as tk
from pathlib import Path

BASE_DIR=Path(__file__).parent
sys.path.insert(0,str(BASE_DIR))

class State:
    IDLE="IDLE";WAKE="WAKE";LISTENING="LISTENING"
    THINKING="THINKING";SPEAKING="SPEAKING"

# ── sounds ───────────────────────────────────────────────────────────────────
def _beep(f,ms):
    try:
        if platform.system()=="Windows":
            import winsound;winsound.Beep(max(37,min(32767,f)),ms)
    except:pass
def snd_wake():   threading.Thread(target=lambda:(_beep(440,60),time.sleep(.05),_beep(880,100)),daemon=True).start()
def snd_listen(): threading.Thread(target=lambda:_beep(1200,40),daemon=True).start()
def snd_done():   threading.Thread(target=lambda:(_beep(660,60),time.sleep(.04),_beep(440,80)),daemon=True).start()
def snd_err():    threading.Thread(target=lambda:_beep(180,180),daemon=True).start()

# ── voice ─────────────────────────────────────────────────────────────────────
class Voice:
    def __init__(self):
        self._lock=threading.Lock();self._mode=None;self._vid=None;self._init()
    def _init(self):
        try:
            import pyttsx3
            e=pyttsx3.init();vs=e.getProperty("voices") or []
            deep=["mark","david","richard","george","james","paul"]
            ch=next((v for v in vs if any(d in v.name.lower() for d in deep)),vs[0] if vs else None)
            self._vid=ch.id if ch else None;self._mode="pyttsx3"
            print(f"Voice: {ch.name if ch else 'default'}")
            try:e.stop()
            except:pass
        except Exception as ex:
            print(f"[Voice] {ex}");self._mode="powershell"
    def _clean(self,t):
        import re
        t=re.sub(r'\bJ\.A\.R\.V\.I\.S\b\.?','Jarvis',t,flags=re.I)
        t=re.sub(r'\b([A-Z])\.([A-Z])\.([A-Z])\.?\b',r'\1\2\3',t)
        t=re.sub(r'\b([A-Z])\.([A-Z])\.',r'\1\2 ',t)
        return t
    def speak(self,text,on_done=None):
        text=self._clean(text)
        def _r():
            with self._lock:
                if self._mode=="pyttsx3":
                    try:
                        import pyttsx3;e=pyttsx3.init()
                        if self._vid:e.setProperty("voice",self._vid)
                        e.setProperty("rate",145);e.setProperty("volume",1.0)
                        e.say(text);e.runAndWait()
                        try:e.stop()
                        except:pass
                        del e
                    except Exception as ex:
                        print(f"[Voice] {ex}");self._mode="powershell";self._ps(text)
                else:self._ps(text)
            if on_done:on_done()
        threading.Thread(target=_r,daemon=True).start()
    def _ps(self,t):
        s=t.replace("'"," ").replace('"',' ')
        subprocess.run(["powershell","-NoProfile","-Command",
            f"Add-Type -AssemblyName System.Speech;$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            f"try{{$s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Male)}}catch{{}};"
            f"$s.Rate=-2;$s.Volume=100;$s.Speak('{s}')"],check=False,timeout=60)

# ── orb renderer ──────────────────────────────────────────────────────────────
class Orb:
    """
    Draws a glowing reactive orb on a tk.Canvas.
    States:
      IDLE      — slow dim blue pulse, tiny ring
      WAKE      — gold flash burst
      LISTENING — green ring expands with mic energy bars
      THINKING  — amber spinning petals
      SPEAKING  — cyan rings ripple outward, bars animate
    """
    COLORS={
        State.IDLE:     ("#001a2e","#003a5c","#0077aa","#00aadd"),
        State.WAKE:     ("#1a0e00","#3a2000","#cc7700","#ffcc00"),
        State.LISTENING:("#001a0e","#003a1c","#00aa55","#00ff88"),
        State.THINKING: ("#1a0800","#3a1500","#cc5500","#ff8800"),
        State.SPEAKING: ("#001520","#002a40","#0099cc","#00e5ff"),
    }
    def __init__(self,canvas,w,h):
        self.cv=canvas;self.w=w;self.h=h
        self.cx=w//2;self.cy=h//2
        self.state=State.IDLE
        self.t=0.0                   # master time counter
        self.ripples=[]              # [(birth_t, max_r)]
        self.bars=[0.0]*32           # voice energy bars
        self._items=[];self._alive=True
        self._tick()

    def set_state(self,s):
        old=self.state;self.state=s
        if s==State.WAKE and old!=State.WAKE:
            self.ripples.append((self.t,220))
        if s in (State.LISTENING,State.SPEAKING):
            self.ripples.append((self.t,160))

    def set_bars(self,bars):
        self.bars=bars[:32]+[0.0]*max(0,32-len(bars))

    def stop(self):self._alive=False

    # ── rendering ─────────────────────────────────────────────────────────────
    def _tick(self):
        if not self._alive:return
        self.t+=0.025
        # auto-animate bars in active states
        if self.state==State.SPEAKING:
            self.bars=[max(0,min(1,0.3+0.5*math.sin(self.t*4+i*0.4)+random.random()*0.2))
                       for i in range(32)]
        elif self.state==State.LISTENING:
            self.bars=[max(0,min(1,0.15+0.35*math.sin(self.t*3+i*0.6)+random.random()*0.25))
                       for i in range(32)]
        elif self.state==State.THINKING:
            self.bars=[max(0,min(1,0.5+0.5*math.sin(self.t*5+i*1.1)))
                       for i in range(32)]
        else:
            self.bars=[max(0,0.05*math.sin(self.t+i*0.3)) for i in range(32)]

        # add ripple on speaking beats
        if self.state==State.SPEAKING and random.random()<0.04:
            self.ripples.append((self.t,120+random.randint(0,60)))

        self._draw()
        self.cv.after(30,self._tick)

    def _draw(self):
        cv=self.cv;cx=self.cx;cy=self.cy;t=self.t
        cols=self.COLORS[self.state]
        bg,mid,bright,core=cols

        for i in self._items:
            try:cv.delete(i)
            except:pass
        self._items=[]

        def O(x0,y0,x1,y1,**kw):self._items.append(cv.create_oval(x0,y0,x1,y1,**kw))
        def L(x0,y0,x1,y1,**kw):self._items.append(cv.create_line(x0,y0,x1,y1,**kw))
        def T(x,y,**kw):self._items.append(cv.create_text(x,y,**kw))
        def A(x0,y0,x1,y1,**kw):self._items.append(cv.create_arc(x0,y0,x1,y1,**kw))

        # ── background subtle grid ────────────────────────────────────────────
        grid_col=self._dim(mid,.25)
        for gx in range(0,self.w,80):
            L(gx,0,gx,self.h,fill=grid_col,width=1)
        for gy in range(0,self.h,80):
            L(0,gy,self.w,gy,fill=grid_col,width=1)

        # ── corner brackets ───────────────────────────────────────────────────
        br_col=self._dim(bright,.5);bsz=36
        for bx,by,dx,dy in [(18,18,1,1),(self.w-18,18,-1,1),
                              (18,self.h-18,1,-1),(self.w-18,self.h-18,-1,-1)]:
            L(bx,by,bx+dx*bsz,by,fill=br_col,width=1)
            L(bx,by,bx,by+dy*bsz,fill=br_col,width=1)

        # ── clock top-right ────────────────────────────────────────────────────
        now=datetime.datetime.now()
        T(self.w-22,22,text=now.strftime("%H:%M:%S"),
          fill=self._dim(bright,.5),font=("Courier New",10,"bold"),anchor="ne")
        T(self.w-22,36,text=now.strftime("%Y-%m-%d"),
          fill=self._dim(mid,.5),font=("Courier New",8),anchor="ne")

        # ── state label bottom-centre ─────────────────────────────────────────
        lbl={"IDLE":"STANDBY","WAKE":"ONLINE","LISTENING":"LISTENING",
             "THINKING":"PROCESSING","SPEAKING":"SPEAKING"}.get(self.state,"")
        T(cx,self.h-28,text=f"◉  {lbl}",
          fill=self._dim(bright,.8),font=("Courier New",11,"bold"),anchor="center")
        T(cx,self.h-14,text='Say "Hey Jarvis" to wake · "Goodbye" to quit',
          fill=self._dim(mid,.5),font=("Courier New",8),anchor="center")

        # ── ripple rings ──────────────────────────────────────────────────────
        dead=[]
        for rb in self.ripples:
            birth,maxr=rb
            age=t-birth;lifetime=1.8
            if age>lifetime:dead.append(rb);continue
            frac=age/lifetime
            r=int(maxr*frac)
            alpha=1.0-frac
            rc=self._blend("#000000",bright,alpha*.5)
            if r>0:
                O(cx-r,cy-r,cx+r,cy+r,outline=rc,width=max(1,int(2*(1-frac))),fill="")
        for d in dead:self.ripples.remove(d)

        # ── outer halo rings ─────────────────────────────────────────────────
        pulse_spd={"IDLE":.8,"WAKE":2,"LISTENING":1.5,"THINKING":2,"SPEAKING":1.5}.get(self.state,1)
        for i,base_r in enumerate([115,95,80]):
            pulse=math.sin(t*pulse_spd+i*1.1)*.5+.5
            r=int(base_r+pulse*8*(1 if self.state!=State.IDLE else 3))
            alpha=(.15+pulse*.25)*(1 if self.state!=State.IDLE else .5)
            rc=self._blend("#000000",bright,alpha)
            if r>0:O(cx-r,cy-r,cx+r,cy+r,outline=rc,
                     width=3-i,fill="")

        # ── energy bars ring ─────────────────────────────────────────────────
        n_bars=32;bar_r=130
        for i in range(n_bars):
            a=math.radians(i*(360/n_bars)-90)
            h=self.bars[i] if i<len(self.bars) else 0
            bar_len=6+h*55
            x1=cx+math.cos(a)*bar_r;y1=cy+math.sin(a)*bar_r
            x2=cx+math.cos(a)*(bar_r+bar_len);y2=cy+math.sin(a)*(bar_r+bar_len)
            if h>0.05:
                bc=self._blend(mid,core,h)
                L(x1,y1,x2,y2,fill=bc,width=max(1,int(h*3+1)))

        # ── THINKING: spinning petals ─────────────────────────────────────────
        if self.state==State.THINKING:
            for i in range(8):
                a=math.radians(t*90+i*45)
                pr=55+20*math.sin(t*3+i)
                px=cx+math.cos(a)*pr;py=cy+math.sin(a)*pr
                ps=int(6+4*math.sin(t*2+i))
                O(px-ps,py-ps,px+ps,py+ps,
                  fill=self._blend("#000000",bright,.6+.4*math.sin(t+i)),
                  outline="")

        # ── orb core ─────────────────────────────────────────────────────────
        # outer soft glow
        for gr,ga in [(68,.08),(58,.12),(50,.18),(42,.26)]:
            gc=self._blend("#000000",bright,ga)
            O(cx-gr,cy-gr,cx+gr,cy+gr,fill=gc,outline="")

        # main sphere gradient illusion (3 concentric ovals)
        O(cx-38,cy-38,cx+38,cy+38,fill=mid,outline="")
        O(cx-28,cy-28,cx+28,cy+28,fill=self._blend(mid,bright,.4),outline="")
        O(cx-18,cy-18,cx+18,cy+18,fill=self._blend(bright,core,.5),outline="")

        # bright hot centre
        hp=math.sin(t*pulse_spd)*.5+.5
        O(cx-9,cy-9,cx+9,cy+9,
          fill=self._blend(bright,core,.6+hp*.4),outline="")
        O(cx-4,cy-4,cx+4,cy+4,
          fill=self._blend(core,"#ffffff",.4+hp*.4),outline="")

        # specular highlight
        O(cx-15,cy-22,cx-5,cy-14,
          fill=self._blend(bright,"#ffffff",.35),outline="")

        # ── WAKE: gold burst rays ─────────────────────────────────────────────
        if self.state==State.WAKE:
            for i in range(12):
                a=math.radians(t*60+i*30)
                rlen=60+30*math.sin(t*4+i*1.5)
                L(cx+math.cos(a)*22,cy+math.sin(a)*22,
                  cx+math.cos(a)*rlen,cy+math.sin(a)*rlen,
                  fill=self._blend("#000000","#ffcc00",.5+.5*math.sin(t*3+i)),
                  width=2)

    @staticmethod
    def _dim(c,f):
        h=c.lstrip("#")
        return"#{:02x}{:02x}{:02x}".format(
            int(int(h[0:2],16)*f),int(int(h[2:4],16)*f),int(int(h[4:6],16)*f))
    @staticmethod
    def _blend(c1,c2,t):
        t=max(0.,min(1.,t));h1=c1.lstrip("#");h2=c2.lstrip("#")
        return"#{:02x}{:02x}{:02x}".format(
            int(int(h1[0:2],16)*(1-t)+int(h2[0:2],16)*t),
            int(int(h1[2:4],16)*(1-t)+int(h2[2:4],16)*t),
            int(int(h1[4:6],16)*(1-t)+int(h2[4:6],16)*t))

# ── main window ───────────────────────────────────────────────────────────────
class JarvisVoiceUI:
    def __init__(self):
        self.root=tk.Tk()
        self.root.title("J.A.R.V.I.S")
        self.root.configure(bg="#020c18")
        # start windowed but allow fullscreen with F11
        self.root.geometry("900x600")
        self.root.resizable(True,True)
        try:self.root.attributes("-alpha",.93)
        except:pass

        self._voice=Voice()
        self._uiq=queue.Queue()
        self._run=True
        self._state=State.IDLE
        self._mentor=False
        self._handler=None
        self._wake_event=threading.Event()

        self._build()
        self._start_engine()
        self._poll()

        self.root.protocol("WM_DELETE_WINDOW",self._close)
        self.root.bind("<F11>",self._toggle_fullscreen)
        self.root.bind("<Escape>",lambda e:self.root.attributes("-fullscreen",False))
        self._fs=False

    def _toggle_fullscreen(self,event=None):
        self._fs=not self._fs
        self.root.attributes("-fullscreen",self._fs)

    def _build(self):
        self._cv=tk.Canvas(self.root,bg="#020c18",highlightthickness=0)
        self._cv.pack(fill="both",expand=True)
        self._cv.bind("<Configure>",self._on_resize)
        W,H=900,600
        self._orb=Orb(self._cv,W,H)

    def _on_resize(self,event):
        W,H=event.width,event.height
        self._orb.w=W;self._orb.h=H
        self._orb.cx=W//2;self._orb.cy=H//2

    def _set_state(self,s):
        self._state=s;self._orb.set_state(s)

    # ── engine ────────────────────────────────────────────────────────────────
    def _start_engine(self):
        threading.Thread(target=self._engine,daemon=True).start()

    def _engine(self):
        print("[Jarvis] Loading core...")
        try:import jarvis as core
        except Exception as e:print(f"ERROR: {e}");return

        api=os.environ.get("ANTHROPIC_API_KEY","")
        if not api:print("⚠  No ANTHROPIC_API_KEY set")

        self._core=core
        mem=core.Memory();skills=core.SkillsManager()
        plugins=core.PluginManager();ai=core.JarvisAI(api,mem)

        def on_wake():self._wake_event.set()
        wd=core.WakeWordDetector(on_wake,core.CONFIG)

        def _speak(text,wake_det=None):
            if not text or not text.strip():return
            ev=threading.Event()
            self._set_state(State.SPEAKING)
            self._voice.speak(text,on_done=lambda:(self._set_state(State.IDLE),ev.set()))
            ev.wait(timeout=60)
            if wake_det:wake_det.resume()
        core.speak=_speak

        self._handler=core.CommandHandler(ai,mem,skills,plugins,wd)
        if self._handler.agents:
            self._handler.agents.speak_fn=lambda t:(_speak(t),None)[1]
        self._mem=mem;self._wd=wd

        vok=core.load_whisper_model()
        self._listen_fn=core.listen_microphone
        if vok:wd.start();print("[Jarvis] Wake word active")
        else:print("[Jarvis] Whisper unavailable")

        # startup greeting
        self._set_state(State.SPEAKING);snd_wake()
        greet="Jarvis online. All systems operational. How may I assist you today, sir?"
        ev=threading.Event()
        self._voice.speak(greet,on_done=lambda:(self._set_state(State.IDLE),ev.set()))
        ev.wait(timeout=25)

        # main loop
        while self._run:
            if self._wake_event.wait(timeout=0.2):
                self._wake_event.clear();self._wake_cycle(wd)

    def _wake_cycle(self,wd):
        self._set_state(State.WAKE);snd_wake()
        greets=[
            "Hello sir, I'm Jarvis, your personal assistant. How may I help you?",
            "Jarvis here. What can I do for you, sir?",
            "Online and ready. What's the mission?",
            "Yes sir. Go ahead.",
        ]
        g=greets[0] if not hasattr(self,"_greeted") else random.choice(greets[1:])
        self._greeted=True
        ev=threading.Event();self._set_state(State.SPEAKING)
        self._voice.speak(g,on_done=lambda:(self._set_state(State.IDLE),ev.set()))
        ev.wait(timeout=15)
        cont=self._turn(wd)
        follow=0
        while self._run and cont and (self._mentor or follow<3):
            time.sleep(0.3);cont=self._turn(wd);follow+=1
        self._set_state(State.IDLE)

    def _turn(self,wd=None):
        if not hasattr(self,"_listen_fn"):return False
        self._set_state(State.LISTENING);snd_listen()
        if wd:wd.pause()
        txt=self._listen_fn()
        if not txt:
            self._set_state(State.IDLE);snd_err()
            if wd:wd.resume();return False
        # ack
        acks=["I got you.","Got it.","On it.","Sure thing.",
              "Right away, sir.","Understood.","Of course.","Leave it to me."]
        ack=random.choice(acks)
        ev=threading.Event();self._set_state(State.SPEAKING)
        self._voice.speak(ack,on_done=lambda:(self._set_state(State.THINKING),ev.set()))
        ev.wait(timeout=8)
        self._set_state(State.THINKING)
        try:resp=self._handler.handle(txt)
        except Exception as e:resp=f"I hit an error — {e}"

        if resp=="SHUTDOWN":
            byes=["Goodbye sir, take care!","See you later sir.",
                  "Signing off. Stay brilliant, sir.","Goodbye!"]
            ev=threading.Event();self._set_state(State.SPEAKING)
            self._voice.speak(random.choice(byes),on_done=lambda:ev.set())
            ev.wait(timeout=12);snd_done()
            self._run=False;self.root.after(800,self.root.destroy);return False

        if resp=="AGENTS_ASSEMBLE":
            self._do_agents(wd);return False

        if resp:
            ev=threading.Event();self._set_state(State.SPEAKING)
            self._voice.speak(resp,on_done=lambda:(self._set_state(State.IDLE),ev.set()))
            ev.wait(timeout=90);snd_done()
            if wd:wd.resume();return True
        self._set_state(State.IDLE)
        if wd:wd.resume();return False

    def _do_agents(self,wd=None):
        msg="Agents standing by, sir. What's the mission?"
        ev=threading.Event();self._set_state(State.SPEAKING)
        self._voice.speak(msg,on_done=lambda:(self._set_state(State.IDLE),ev.set()))
        ev.wait(timeout=10)
        self._set_state(State.LISTENING);snd_listen()
        if wd:wd.pause()
        mission=self._listen_fn() if hasattr(self,"_listen_fn") else None
        if mission and self._handler and self._handler.agents:
            def _run():
                briefing=self._handler.agents.assemble(mission)
                ev2=threading.Event();self._set_state(State.SPEAKING)
                self._voice.speak(briefing,on_done=lambda:(self._set_state(State.IDLE),ev2.set()))
                ev2.wait(timeout=90);snd_done()
                if wd:wd.resume()
            threading.Thread(target=_run,daemon=True).start()
        else:
            self._set_state(State.IDLE)
            if wd:wd.resume()

    def _poll(self):
        self.root.after(80,self._poll)

    def _close(self):
        self._run=False
        try:self._orb.stop()
        except:pass
        if hasattr(self,"_mem"):self._mem.save()
        try:self.root.destroy()
        except:pass

    def run(self):self.root.mainloop()

def main():
    print("""
╔══════════════════════════════════════════╗
║  J.A.R.V.I.S  ·  VOICE-ONLY  ·  ORB   ║
║  F11 = fullscreen  ·  Esc = windowed   ║
╚══════════════════════════════════════════╝""")
    JarvisVoiceUI().run()

if __name__=="__main__":
    main()
