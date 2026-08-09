"""
JARVIS — Artistic Voice Orb UI v3
Full-screen, no buttons, pure voice. Orb reacts with plasma, particles,
lightning arcs, ripple rings, and full colour transitions per state.
"""
import os,sys,threading,time,queue,math,random,subprocess,platform,datetime
import tkinter as tk
from pathlib import Path

BASE_DIR=Path(__file__).parent
sys.path.insert(0,str(BASE_DIR))

class State:
    IDLE="IDLE";WAKE="WAKE";LISTENING="LISTENING"
    THINKING="THINKING";SPEAKING="SPEAKING"

def _beep(f,ms):
    try:
        if platform.system()=="Windows":
            import winsound;winsound.Beep(max(37,min(32767,f)),ms)
    except:pass
def snd_wake():  threading.Thread(target=lambda:(_beep(440,60),time.sleep(.05),_beep(880,100)),daemon=True).start()
def snd_listen():threading.Thread(target=lambda:_beep(1200,40),daemon=True).start()
def snd_done():  threading.Thread(target=lambda:(_beep(660,60),time.sleep(.04),_beep(440,80)),daemon=True).start()
def snd_err():   threading.Thread(target=lambda:_beep(180,180),daemon=True).start()

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
        except Exception as ex:print(f"[Voice] {ex}");self._mode="powershell"
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

# ── colour config ─────────────────────────────────────────────────────────────
PALETTES={
    State.IDLE:     dict(c1=(0,51,255),    c2=(0,170,255),   c3=(68,221,255),  acc=(0,102,255)),
    State.WAKE:     dict(c1=(255,102,0),   c2=(255,170,0),   c3=(255,238,68),  acc=(255,204,0)),
    State.LISTENING:dict(c1=(0,204,68),    c2=(0,255,136),   c3=(136,255,204), acc=(0,255,102)),
    State.THINKING: dict(c1=(170,0,255),   c2=(255,0,204),   c3=(255,136,238), acc=(204,68,255)),
    State.SPEAKING: dict(c1=(0,204,255),   c2=(255,255,255), c3=(136,238,255), acc=(0,255,255)),
}

def lerp_rgb(a,b,t):
    t=max(0.,min(1.,t))
    return tuple(int(a[i]+(b[i]-a[i])*t) for i in range(3))

def rgb_hex(r,g,b,a=255):
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"

class Orb:
    def __init__(self,canvas,w,h):
        self.cv=canvas;self.w=w;self.h=h
        self.cx=w//2;self.cy=h//2
        self.state=State.IDLE;self.t=0.
        self.cur=dict(PALETTES[State.IDLE]);self.tgt=dict(PALETTES[State.IDLE]);self.blend=1.
        self.bars=[0.]*48;self.bar_tgt=[0.]*48
        self.particles=[];self.ripples=[];self.plasma_rings=[]
        self._items=[];self._alive=True;self._tick()

    def set_state(self,s):
        old=self.state;self.state=s
        self.tgt=dict(PALETTES.get(s,PALETTES[State.IDLE]));self.blend=0.
        if s in (State.WAKE,State.LISTENING,State.SPEAKING,State.THINKING):
            self._burst(24 if s==State.WAKE else 12)
            self.ripples.append([self.t,200 if s==State.WAKE else 140])

    def stop(self):self._alive=False

    def _burst(self,n):
        for _ in range(n):
            a=random.random()*math.pi*2;sp=3+random.random()*6
            self.particles.append([self.cx,self.cy,math.cos(a)*sp,math.sin(a)*sp,1.,2+random.random()*5])

    # ── lerp palette ─────────────────────────────────────────────────────────
    def _update_palette(self):
        if self.blend<1.:
            self.blend=min(1.,self.blend+.035)
            e=1-(1-self.blend)**2
            for k in ("c1","c2","c3","acc"):
                self.cur[k]=lerp_rgb(self.cur[k],self.tgt[k],e)

    # ── update bars ───────────────────────────────────────────────────────────
    def _update_bars(self):
        mag={"IDLE":.07,"WAKE":.92,"LISTENING":.78,"THINKING":.88,"SPEAKING":.92}.get(self.state,.07)
        spd={"IDLE":.015,"WAKE":.18,"LISTENING":.14,"THINKING":.20,"SPEAKING":.16}.get(self.state,.015)
        for i in range(48):
            self.bar_tgt[i]=max(0,min(1,mag*(0.35+0.65*math.sin(self.t*3+i*.36+random.random()*.5))))
            self.bars[i]+=(self.bar_tgt[i]-self.bars[i])*spd
            self.bars[i]=max(0,min(1,self.bars[i]))

    # ── main tick ─────────────────────────────────────────────────────────────
    def _tick(self):
        if not self._alive:return
        self.t+=.022
        self._update_palette();self._update_bars()
        if self.state==State.SPEAKING and random.random()<.07:
            self.plasma_rings.append([self.t,1.])
        self._draw()
        self.cv.after(28,self._tick)

    # ── draw ─────────────────────────────────────────────────────────────────
    def _draw(self):
        cv=self.cv;W=self.w;H=self.h;cx=self.cx;cy=self.cy;t=self.t
        sc=min(W,H)/700
        R=int(96*sc)
        c1,c2,c3,acc=self.cur["c1"],self.cur["c2"],self.cur["c3"],self.cur["acc"]
        acc_h=rgb_hex(*acc);c2_h=rgb_hex(*c2);c3_h=rgb_hex(*c3)

        for i in self._items:
            try:cv.delete(i)
            except:pass
        self._items=[]
        def O(x0,y0,x1,y1,**k):self._items.append(cv.create_oval(x0,y0,x1,y1,**k))
        def L(x0,y0,x1,y1,**k):self._items.append(cv.create_line(x0,y0,x1,y1,**k))
        def T(x,y,**k):self._items.append(cv.create_text(x,y,**k))
        def A(x0,y0,x1,y1,**k):self._items.append(cv.create_arc(x0,y0,x1,y1,**k))

        pulse=math.sin(t*{"IDLE":1.,"WAKE":5.,"LISTENING":2.5,"THINKING":3.5,"SPEAKING":3.}[self.state])*.5+.5

        # ── background ────────────────────────────────────────────────────────
        self._items.append(cv.create_rectangle(0,0,W,H,fill="#00000a",outline=""))

        # ambient nebula circles
        for i in range(3):
            nr=int((180+i*55)*sc)
            nx=cx+int(math.cos(t*.25+i*2.1)*70*sc)
            ny=cy+int(math.sin(t*.3+i*1.8)*45*sc)
            alpha=int(20+pulse*12)
            nc=rgb_hex(int(c1[0]*alpha/255),int(c1[1]*alpha/255),int(c1[2]*alpha/255))
            O(nx-nr,ny-nr,nx+nr,ny+nr,fill=nc,outline="")

        # grid lines
        gc=rgb_hex(int(c1[0]*.1),int(c1[1]*.1),int(c1[2]*.1))
        for gx in range(0,W,int(80*sc)):L(gx,0,gx,H,fill=gc,width=1)
        for gy in range(0,H,int(80*sc)):L(0,gy,W,gy,fill=gc,width=1)

        # corner brackets
        bs=int(38*sc)
        bc=rgb_hex(int(acc[0]*.55),int(acc[1]*.55),int(acc[2]*.55))
        for bx,by,dx,dy in [(18,18,1,1),(W-18,18,-1,1),(18,H-18,1,-1),(W-18,H-18,-1,-1)]:
            L(bx+dx*bs,by,bx,by,fill=bc,width=int(1.5*sc)+1)
            L(bx,by,bx,by+dy*bs,fill=bc,width=int(1.5*sc)+1)

        # ── hex ring ──────────────────────────────────────────────────────────
        hR=int((R+68)*sc)
        hspd={"IDLE":.003,"WAKE":.03,"LISTENING":.02,"THINKING":.04,"SPEAKING":.025}[self.state]
        hbase=t*hspd
        for i in range(6):
            a1=hbase+i*math.pi/3;a2=hbase+(i+1)*math.pi/3
            x1=cx+int(math.cos(a1)*hR);y1=cy+int(math.sin(a1)*hR)
            x2=cx+int(math.cos(a2)*hR);y2=cy+int(math.sin(a2)*hR)
            ha=int((0.18+pulse*.3)*255)
            hc=rgb_hex(int(acc[0]*ha/255),int(acc[1]*ha/255),int(acc[2]*ha/255))
            L(x1,y1,x2,y2,fill=hc,width=max(1,int(1.5*sc)))
            mx=(x1+x2)//2;my=(y1+y2)//2
            dr=max(2,int(3*sc))
            O(mx-dr,my-dr,mx+dr,my+dr,fill=acc_h,outline="")

        # ── energy bars ───────────────────────────────────────────────────────
        nb=48;brI=int((R+9)*sc)
        for i in range(nb):
            h=self.bars[i]
            if h<.03:continue
            a=i*(2*math.pi/nb)-math.pi/2
            bl=int((5+h*62)*sc)
            x1=cx+int(math.cos(a)*brI);y1=cy+int(math.sin(a)*brI)
            x2=cx+int(math.cos(a)*(brI+bl));y2=cy+int(math.sin(a)*(brI+bl))
            bc2=lerp_rgb(c2,c3,h)
            ba=int((0.35+h*.65)*255)
            bcc=rgb_hex(int(bc2[0]*ba/255),int(bc2[1]*ba/255),int(bc2[2]*ba/255))
            lw=max(1,int((1+h*3.5)*sc))
            L(x1,y1,x2,y2,fill=bcc,width=lw)
            if h>.72:
                dr=max(2,int(3*sc))
                O(x2-dr,y2-dr,x2+dr,y2+dr,fill=c3_h,outline="")

        # inner dash ring
        for i in range(24):
            a=-t*.012+i*math.pi/12
            ri=int((R+3)*sc);ro=ri+int(7*sc)
            x1=cx+int(math.cos(a)*ri);y1=cy+int(math.sin(a)*ri)
            x2=cx+int(math.cos(a)*ro);y2=cy+int(math.sin(a)*ro)
            dc=acc_h if i%3==0 else rgb_hex(int(c1[0]*.4),int(c1[1]*.4),int(c1[2]*.4))
            L(x1,y1,x2,y2,fill=dc,width=max(1,2 if i%3==0 else 1))

        # ── THINKING: orbiting blobs ───────────────────────────────────────────
        if self.state==State.THINKING:
            for i in range(6):
                a=t*1.85+i*math.pi/3
                orr=int((R*.55+14*sc*math.sin(t*2.5+i))*1)
                px=cx+int(math.cos(a)*orr);py=cy+int(math.sin(a)*orr)
                br=int(13*sc)
                fa=int((0.5+.5*math.sin(t+i))*255)
                fc=rgb_hex(int(c3[0]*fa/255),int(c3[1]*fa/255),int(c3[2]*fa/255))
                O(px-br,py-br,px+br,py+br,fill=fc,outline="")

        # ── WAKE: lightning arcs ───────────────────────────────────────────────
        if self.state==State.WAKE:
            for i in range(8):
                a=t*2.2+i*math.pi/4
                pts=[]
                steps=5
                for s in range(steps+1):
                    fr=s/steps
                    rr=(R*.4+fr*R*1.15)*sc
                    ja=a+(random.random()-.5)*.35
                    jit=int(18*sc*(1-fr)*random.random())
                    pts.extend([cx+int(math.cos(ja)*(rr+jit)),
                                 cy+int(math.sin(ja)*(rr+jit))])
                la=int((0.3+random.random()*.55)*255)
                lc=rgb_hex(int(acc[0]*la/255),int(acc[1]*la/255),int(acc[2]*la/255))
                if len(pts)>=4:
                    L(*pts,fill=lc,width=max(1,int((1+random.random()*2)*sc)),smooth=False)

        # ── ripples ────────────────────────────────────────────────────────────
        dead=[]
        for rp in self.ripples:
            birth,maxR=rp;age=t-birth;life=2.2
            if age>=life:dead.append(rp);continue
            fr=age/life;rr=int(maxR*sc*fr)
            ra=int((1-fr)*.6*255)
            rc=rgb_hex(int(acc[0]*ra/255),int(acc[1]*ra/255),int(acc[2]*ra/255))
            if rr>1:O(cx-rr,cy-rr,cx+rr,cy+rr,outline=rc,width=max(1,int((1-fr)*3.5*sc)+1),fill="")
        for d in dead:self.ripples.remove(d)

        # ── SPEAKING: outward plasma rings ────────────────────────────────────
        dead2=[]
        for pr in self.plasma_rings:
            birth,life=pr;age=t-birth
            if age>=life:dead2.append(pr);continue
            fr=age/life
            rr=int((R+fr*180)*sc)
            pa=int((1-fr)*.6*255)
            pc=rgb_hex(int(acc[0]*pa/255),int(acc[1]*pa/255),int(acc[2]*pa/255))
            lw=max(1,int((1-fr)*2.5*sc)+1)
            if rr>0:O(cx-rr,cy-rr,cx+rr,cy+rr,outline=pc,width=lw,fill="")
        for d in dead2:self.plasma_rings.remove(d)

        # ── outer glow layers ─────────────────────────────────────────────────
        for i,fr in enumerate([2.2,1.7,1.3]):
            gr=int(R*fr)
            ga=int((0.07+pulse*.1*(3-i))*255)
            gc2=rgb_hex(int(c2[0]*ga/255),int(c2[1]*ga/255),int(c2[2]*ga/255))
            O(cx-gr,cy-gr,cx+gr,cy+gr,fill=gc2,outline="")

        # ── orb body layers ───────────────────────────────────────────────────
        # outer body
        O(cx-R,cy-R,cx+R,cy+R,fill=rgb_hex(*c1),outline="")
        # mid layer
        m2=int(R*.82);mc=lerp_rgb(c1,c2,.55)
        O(cx-m2,cy-m2,cx+m2,cy+m2,fill=rgb_hex(*mc),outline="")
        # bright inner
        m3=int(R*.58);mc2=lerp_rgb(c2,c3,.6)
        O(cx-m3,cy-m3,cx+m3,cy+m3,fill=rgb_hex(*mc2),outline="")
        # core
        m4=int(R*.34);mc3=lerp_rgb(c3,(255,255,255),.4)
        O(cx-m4,cy-m4,cx+m4,cy+m4,fill=rgb_hex(*mc3),outline="")

        # pulsing hot spot
        pspd={"IDLE":1.2,"WAKE":6.,"LISTENING":3.,"THINKING":4.,"SPEAKING":3.5}[self.state]
        hp=math.sin(t*pspd)*.5+.5
        hs=int((R*.13+hp*R*.06))
        O(cx-hs,cy-hs,cx+hs,cy+hs,fill="#ffffff",outline="")

        # specular highlight
        sx=cx-int(R*.3);sy=cy-int(R*.35);sr=int(R*.35)
        sa=int(0.35*255);sc2=rgb_hex(int(lerp_rgb(c3,(255,255,255),.6)[0]*sa/255),
                                      int(lerp_rgb(c3,(255,255,255),.6)[1]*sa/255),
                                      int(lerp_rgb(c3,(255,255,255),.6)[2]*sa/255))
        O(sx-sr,sy-sr,sx+sr,sy+sr,fill=sc2,outline="")

        # rim shadow
        rim=int(R*.85)
        O(cx-R,cy-R,cx+R,cy+R,outline=rgb_hex(0,0,10),width=int(R*.2)+1,fill="")

        # ── particles ─────────────────────────────────────────────────────────
        dead3=[]
        for p in self.particles:
            p[0]+=p[2];p[1]+=p[3];p[2]*=.95;p[3]*=.95;p[4]-=.022
            if p[4]<=0:dead3.append(p);continue
            pr2=max(1,int(p[5]*p[4]*sc))
            pa=int(p[4]*200)
            pc2=rgb_hex(int(c3[0]*pa/255),int(c3[1]*pa/255),int(c3[2]*pa/255))
            O(int(p[0])-pr2,int(p[1])-pr2,int(p[0])+pr2,int(p[1])+pr2,fill=pc2,outline="")
        for d in dead3:self.particles.remove(d)

        # ── state label + clock ───────────────────────────────────────────────
        lbl={"IDLE":"STANDBY","WAKE":"ONLINE","LISTENING":"LISTENING",
             "THINKING":"PROCESSING","SPEAKING":"SPEAKING"}[self.state]
        T(cx,H-int(30*sc),text=f"◉  {lbl}",
          fill=acc_h,font=("Courier New",max(10,int(13*sc)),"bold"),anchor="center")
        T(cx,H-int(14*sc),
          text='Say "Hey Jarvis" to activate  ·  "Goodbye" to quit  ·  F11 fullscreen',
          fill=rgb_hex(int(c1[0]*.55),int(c1[1]*.55),int(c1[2]*.55)),
          font=("Courier New",max(7,int(9*sc))),anchor="center")
        now=datetime.datetime.now()
        T(W-int(16*sc),int(14*sc),text=now.strftime("%H:%M:%S"),
          fill=rgb_hex(int(acc[0]*.8),int(acc[1]*.8),int(acc[2]*.8)),
          font=("Courier New",max(8,int(11*sc)),"bold"),anchor="ne")
        T(W-int(16*sc),int(28*sc),text=now.strftime("%Y-%m-%d"),
          fill=rgb_hex(int(c1[0]*.45),int(c1[1]*.45),int(c1[2]*.45)),
          font=("Courier New",max(7,int(9*sc))),anchor="ne")

class JarvisVoiceUI:
    def __init__(self):
        self.root=tk.Tk();self.root.title("J.A.R.V.I.S")
        self.root.configure(bg="#00000a");self.root.geometry("960x620")
        self.root.resizable(True,True)
        try:self.root.attributes("-alpha",.95)
        except:pass
        self._voice=Voice();self._uiq=queue.Queue()
        self._run=True;self._state=State.IDLE
        self._mentor=False;self._handler=None
        self._wake_event=threading.Event();self._fs=False
        self._build();self._start_engine()
        self.root.protocol("WM_DELETE_WINDOW",self._close)
        self.root.bind("<F11>",self._toggle_fs)
        self.root.bind("<Escape>",lambda e:self.root.attributes("-fullscreen",False))

    def _toggle_fs(self,e=None):
        self._fs=not self._fs;self.root.attributes("-fullscreen",self._fs)

    def _build(self):
        self._cv=tk.Canvas(self.root,bg="#00000a",highlightthickness=0)
        self._cv.pack(fill="both",expand=True)
        self._cv.bind("<Configure>",self._on_resize)
        self._orb=Orb(self._cv,960,620)

    def _on_resize(self,event):
        self._orb.w=event.width;self._orb.h=event.height
        self._orb.cx=event.width//2;self._orb.cy=event.height//2

    def _set_state(self,s):
        self._state=s;self._orb.set_state(s)

    def _start_engine(self):
        threading.Thread(target=self._engine,daemon=True).start()

    def _engine(self):
        print("[Jarvis] Loading core...")
        try:import jarvis as core
        except Exception as e:print(f"ERROR: {e}");return
        api=os.environ.get("ANTHROPIC_API_KEY","")
        if not api:print("⚠  No ANTHROPIC_API_KEY")
        self._core=core
        mem=core.Memory();skills=core.SkillsManager()
        plugins=core.PluginManager();ai=core.JarvisAI(api,mem)
        def on_wake():self._wake_event.set()
        wd=core.WakeWordDetector(on_wake,core.CONFIG)
        def _speak(text,wake_det=None):
            if not text or not text.strip():return
            ev=threading.Event();self._set_state(State.SPEAKING)
            self._voice.speak(text,on_done=lambda:(self._set_state(State.IDLE),ev.set()))
            ev.wait(timeout=60)
            if wake_det:wake_det.resume()
        core.speak=_speak
        self._handler=core.CommandHandler(ai,mem,skills,plugins,wd)
        if self._handler.agents:
            self._handler.agents.speak_fn=lambda t:(_speak(t),None)[1]
        self._mem=mem;self._wd=wd
        vok=core.load_whisper_model();self._listen_fn=core.listen_microphone
        if vok:wd.start();print("[Jarvis] Wake word active")
        else:print("[Jarvis] Whisper unavailable")
        self._set_state(State.SPEAKING);snd_wake()
        greet="Jarvis online. All systems operational. How may I assist you today, sir?"
        ev=threading.Event()
        self._voice.speak(greet,on_done=lambda:(self._set_state(State.IDLE),ev.set()))
        ev.wait(timeout=25)
        while self._run:
            if self._wake_event.wait(timeout=0.2):
                self._wake_event.clear();self._wake_cycle(wd)

    def _wake_cycle(self,wd):
        self._set_state(State.WAKE);snd_wake()
        greets=["Hello sir, I'm Jarvis, your personal assistant. How may I help you?",
                "Jarvis here. What can I do for you, sir?",
                "Online and ready. What's the mission?","Yes sir. Go ahead."]
        g=greets[0] if not hasattr(self,"_greeted") else random.choice(greets[1:])
        self._greeted=True
        ev=threading.Event();self._set_state(State.SPEAKING)
        self._voice.speak(g,on_done=lambda:(self._set_state(State.IDLE),ev.set()))
        ev.wait(timeout=15)
        cont=self._turn(wd);follow=0
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
        acks=["I got you.","Got it.","On it.","Sure thing.",
              "Right away, sir.","Understood.","Of course.","Leave it to me."]
        ack=random.choice(acks)
        ev=threading.Event();self._set_state(State.SPEAKING)
        self._voice.speak(ack,on_done=lambda:(self._set_state(State.THINKING),ev.set()))
        ev.wait(timeout=8);self._set_state(State.THINKING)
        try:resp=self._handler.handle(txt)
        except Exception as e:resp=f"I hit an error — {e}"
        if resp=="SHUTDOWN":
            byes=["Goodbye sir, take care!","See you later sir.","Signing off. Stay brilliant, sir.","Goodbye!"]
            ev=threading.Event();self._set_state(State.SPEAKING)
            self._voice.speak(random.choice(byes),on_done=lambda:ev.set())
            ev.wait(timeout=12);snd_done();self._run=False
            self.root.after(800,self.root.destroy);return False
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
        ev.wait(timeout=10);self._set_state(State.LISTENING);snd_listen()
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
╔═══════════════════════════════════════════════╗
║  J.A.R.V.I.S  ·  ARTISTIC VOICE ORB  v3     ║
║  F11 = fullscreen  ·  Esc = windowed         ║
╚═══════════════════════════════════════════════╝""")
    JarvisVoiceUI().run()

if __name__=="__main__":
    main()
