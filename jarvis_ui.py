"""
JARVIS — Solar System UI v4
Jarvis is the sun at the centre. Each agent is an orbiting planet.
Planets glow and pulse brighter when their agent is actively working.
Fully voice controlled — no buttons, no transcript.
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

def lerp_rgb(a,b,t):
    t=max(0.,min(1.,t))
    return tuple(int(a[i]+(b[i]-a[i])*t) for i in range(3))
def rgb_hex(r,g,b):
    return f"#{max(0,min(255,int(r))):02x}{max(0,min(255,int(g))):02x}{max(0,min(255,int(b))):02x}"
def scale_c(c,f):
    return tuple(max(0,min(255,int(v*f))) for v in c)

# ── Sun palette per state ──────────────────────────────────────────────────────
SUN_PALETTES={
    State.IDLE:     dict(core=(60,140,255),  mid=(20,70,180),  glow=(0,40,120)),
    State.WAKE:     dict(core=(255,220,80),  mid=(255,160,20), glow=(180,90,0)),
    State.LISTENING:dict(core=(120,255,170), mid=(20,200,110), glow=(0,120,60)),
    State.THINKING: dict(core=(230,120,255), mid=(160,40,220), glow=(90,0,140)),
    State.SPEAKING: dict(core=(255,255,255), mid=(80,220,255), glow=(0,140,200)),
}

# ── Planets = the 7 agents. Orbit period in seconds (slow, Kepler-like) ────────
# ticks happen roughly every 28ms (~35.7 ticks/sec)
TICKS_PER_SEC=35.7
def _deg_per_tick(period_sec):
    return 360.0/(period_sec*TICKS_PER_SEC)

PLANETS=[
    dict(name="Research", color=(80,220,190),  r_orbit=100, size=7,
         speed=_deg_per_tick(48),  ring=False, moon=True,  bands=False),
    dict(name="File",     color=(90,160,255),  r_orbit=135, size=8,
         speed=_deg_per_tick(66),  ring=False, moon=False, bands=False),
    dict(name="System",   color=(255,180,70),  r_orbit=172, size=13,
         speed=_deg_per_tick(88),  ring=True,  moon=False, bands=True),
    dict(name="Image",    color=(255,120,140), r_orbit=210, size=7,
         speed=_deg_per_tick(118), ring=False, moon=False, bands=False),
    dict(name="Email",    color=(120,230,120), r_orbit=250, size=9,
         speed=_deg_per_tick(154), ring=False, moon=False, bands=False),
    dict(name="Web",      color=(210,120,255), r_orbit=292, size=11,
         speed=_deg_per_tick(198), ring=True,  moon=False, bands=True),
    dict(name="Code",     color=(160,140,255), r_orbit=335, size=8,
         speed=_deg_per_tick(248), ring=False, moon=False, bands=False),
]
ASTEROID_BELT_R=(228,236)  # sits between Image and Email

class SolarSystem:
    def __init__(self,canvas,w,h):
        self.cv=canvas;self.w=w;self.h=h;self.cx=w//2;self.cy=h//2
        self.state=State.IDLE;self.t=0.
        self.cur=dict(SUN_PALETTES[State.IDLE]);self.tgt=dict(self.cur);self.blend=1.
        self.bars=[0.]*40;self.bar_tgt=[0.]*40
        self.planets={p["name"]:dict(angle=random.random()*360,active=False,
                                      pulse=0.,status="idle",flash=0.,trail=[])
                      for p in PLANETS}
        self.moon_angle=random.random()*360
        self.mission_active=False
        self.stars=[(random.random(),random.random(),random.random()*1.6+.3) for _ in range(160)]
        self.asteroids=[dict(a=random.random()*360,
                              r=random.uniform(*ASTEROID_BELT_R),
                              sz=random.uniform(.7,1.6))
                         for _ in range(70)]
        # very slow whole-system rotation (one full turn ≈ 4 minutes)
        self.sys_rotation=0.
        self._sys_rot_speed=_deg_per_tick(240)
        self._items=[];self._alive=True;self._tick()

    def set_state(self,s):
        self.state=s;self.tgt=dict(SUN_PALETTES.get(s,SUN_PALETTES[State.IDLE]));self.blend=0.
        if s in (State.WAKE,State.LISTENING,State.SPEAKING):
            self._burst(16 if s==State.WAKE else 8)
            self.ripples=getattr(self,"ripples",[])
            self.ripples.append([self.t,170 if s==State.WAKE else 110])

    def agent_event(self,name,status):
        if name=="__mission__":
            self.mission_active=(status=="start")
            return
        p=self.planets.get(name)
        if not p:return
        if status=="start":
            p["active"]=True;p["status"]="active";p["flash"]=1.
        elif status=="done":
            p["active"]=False;p["status"]="done";p["flash"]=1.
        elif status=="error":
            p["active"]=False;p["status"]="error";p["flash"]=1.

    def stop(self):self._alive=False

    def _burst(self,n):
        if not hasattr(self,"particles"):self.particles=[]
        for _ in range(n):
            a=random.random()*math.pi*2;sp=2+random.random()*5
            self.particles.append([self.cx,self.cy,math.cos(a)*sp,math.sin(a)*sp,1.,2+random.random()*4])

    def _update_palette(self):
        if self.blend<1.:
            self.blend=min(1.,self.blend+.035)
            e=1-(1-self.blend)**2
            for k in ("core","mid","glow"):
                self.cur[k]=lerp_rgb(self.cur[k],self.tgt[k],e)

    def _update_bars(self):
        mag={"IDLE":.06,"WAKE":.85,"LISTENING":.7,"THINKING":.75,"SPEAKING":.9}.get(self.state,.06)
        spd={"IDLE":.02,"WAKE":.18,"LISTENING":.14,"THINKING":.16,"SPEAKING":.17}.get(self.state,.02)
        for i in range(40):
            self.bar_tgt[i]=max(0,min(1,mag*(.35+.65*math.sin(self.t*3+i*.4+random.random()*.4))))
            self.bars[i]+=(self.bar_tgt[i]-self.bars[i])*spd
            self.bars[i]=max(0,min(1,self.bars[i]))

    # ── orbital geometry ─────────────────────────────────────────────────────
    def _ellipse_point(self,r_orbit,angle_deg,tilt,rot_deg):
        """Compute a point on a tilted, globally-rotated elliptical orbit."""
        a=math.radians(angle_deg)
        rx=math.cos(a)*r_orbit
        ry=math.sin(a)*r_orbit*tilt
        rot=math.radians(rot_deg)
        cr,sr=math.cos(rot),math.sin(rot)
        fx=rx*cr-ry*sr
        fy=rx*sr+ry*cr
        return fx,fy

    def _tick(self):
        if not self._alive:return
        self.t+=.02
        self._update_palette();self._update_bars()
        self.sys_rotation=(self.sys_rotation+self._sys_rot_speed)%360
        self.moon_angle=(self.moon_angle+2.4)%360
        for name,p in self.planets.items():
            base_speed=next(pl["speed"] for pl in PLANETS if pl["name"]==name)
            mult=1.8 if p["active"] else 1.0
            p["angle"]=(p["angle"]+base_speed*mult)%360
            if p["flash"]>0:p["flash"]=max(0,p["flash"]-.012)
        if not hasattr(self,"ripples"):self.ripples=[]
        if not hasattr(self,"particles"):self.particles=[]
        self._draw()
        self.cv.after(28,self._tick)

    def _draw(self):
        cv=self.cv;W=self.w;H=self.h;cx=self.cx;cy=self.cy;t=self.t
        sc=min(W,H)/780
        core,mid,glow=self.cur["core"],self.cur["mid"],self.cur["glow"]
        tilt=0.42+0.05*math.sin(t*0.05)   # subtle breathing tilt for pseudo-3D life
        rot=self.sys_rotation

        for i in self._items:
            try:cv.delete(i)
            except:pass
        self._items=[]
        def O(x0,y0,x1,y1,**k):self._items.append(cv.create_oval(x0,y0,x1,y1,**k))
        def L(*a,**k):self._items.append(cv.create_line(*a,**k))
        def T(x,y,**k):self._items.append(cv.create_text(x,y,**k))
        def POLY(pts,**k):self._items.append(cv.create_polygon(pts,**k))

        pulse=math.sin(t*{"IDLE":1.,"WAKE":5.,"LISTENING":2.5,"THINKING":3.,"SPEAKING":2.8}[self.state])*.5+.5

        # ── space background ─────────────────────────────────────────────────
        self._items.append(cv.create_rectangle(0,0,W,H,fill="#00000c",outline=""))
        for sx,sy,sb in self.stars:
            x=sx*W;y=sy*H
            tw=.5+.5*math.sin(t*sb*2+sx*40)
            r=max(1,int(1.3*sc*tw))
            b=int(110+tw*140)
            O(x-r,y-r,x+r,y+r,fill=rgb_hex(b,b,b+15),outline="")

        bs=int(34*sc);bc=rgb_hex(*scale_c(core,.5))
        for bx,by,dx,dy in [(18,18,1,1),(W-18,18,-1,1),(18,H-18,1,-1),(W-18,H-18,-1,-1)]:
            L(bx+dx*bs,by,bx,by,fill=bc,width=max(1,int(1.5*sc)))
            L(bx,by,bx,by+dy*bs,fill=bc,width=max(1,int(1.5*sc)))

        # ── asteroid belt (behind orbit rings) ────────────────────────────────
        for ast in self.asteroids:
            ast["a"]=(ast["a"]+0.012)%360
            fx,fy=self._ellipse_point(ast["r"]*sc,ast["a"],tilt,rot)
            ax=cx+fx;ay=cy+fy
            asz=max(.6,ast["sz"]*sc*.6)
            ac=rgb_hex(*scale_c((150,140,120),.55))
            O(ax-asz,ay-asz,ax+asz,ay+asz,fill=ac,outline="")

        # ── orbit ellipses (tilted + rotated polylines) ───────────────────────
        for pl in PLANETS:
            p=self.planets[pl["name"]]
            steps=56;pts=[]
            for i in range(steps+1):
                ang=i*(360/steps)
                fx,fy=self._ellipse_point(pl["r_orbit"]*sc,ang,tilt,rot)
                pts.extend([cx+fx,cy+fy])
            ring_alpha=.4 if p["active"] else .13
            rc=rgb_hex(*scale_c(core,ring_alpha))
            if len(pts)>=4:
                L(*pts,fill=rc,width=1,smooth=True)

        # ── sun glow layers ──────────────────────────────────────────────────
        sunR=int((38+pulse*7)*sc)
        for i,fr in enumerate([3.2,2.4,1.8,1.35]):
            gr=int(sunR*fr)
            ga=(0.05+pulse*.06*(4-i))*(1.4 if self.state==State.SPEAKING else 1.)
            gc=rgb_hex(*scale_c(glow,ga*2.2))
            O(cx-gr,cy-gr,cx+gr,cy+gr,fill=gc,outline="")

        if self.state in (State.SPEAKING,State.WAKE):
            nrays=16
            for i in range(nrays):
                a=math.radians(i*(360/nrays)+t*20)
                h=self.bars[i%len(self.bars)]
                rlen=int((sunR*1.15+h*46*sc))
                x1=cx+math.cos(a)*sunR*.9;y1=cy+math.sin(a)*sunR*.9
                x2=cx+math.cos(a)*rlen;y2=cy+math.sin(a)*rlen
                rc2=rgb_hex(*scale_c(mid,.4+h*.6))
                L(x1,y1,x2,y2,fill=rc2,width=max(1,int((1+h*2)*sc)))

        if self.state==State.THINKING:
            for i in range(10):
                a=t*2.2+i*(2*math.pi/10)
                orr=sunR*1.6+8*sc*math.sin(t*3+i)
                px=cx+math.cos(a)*orr;py=cy+math.sin(a)*orr
                br=max(2,int(5*sc))
                fc=rgb_hex(*scale_c(mid,.6+.4*math.sin(t*2+i)))
                O(px-br,py-br,px+br,py+br,fill=fc,outline="")

        if self.state==State.WAKE:
            for i in range(6):
                a=t*2+i*math.pi/3
                pts=[]
                for s in range(5):
                    fr=s/4;rr=(sunR*.8+fr*sunR*1.6)
                    ja=a+(random.random()-.5)*.3
                    jit=int(14*sc*(1-fr)*random.random())
                    pts.extend([cx+math.cos(ja)*(rr+jit),cy+math.sin(ja)*(rr+jit)])
                lc=rgb_hex(*scale_c(core,.3+random.random()*.5))
                if len(pts)>=4:L(*pts,fill=lc,width=max(1,int(1.5*sc)))

        # ── sun body ──────────────────────────────────────────────────────────
        O(cx-sunR,cy-sunR,cx+sunR,cy+sunR,fill=rgb_hex(*mid),outline="")
        m2=int(sunR*.7);mc=lerp_rgb(mid,core,.6)
        O(cx-m2,cy-m2,cx+m2,cy+m2,fill=rgb_hex(*mc),outline="")
        m3=int(sunR*.4)
        O(cx-m3,cy-m3,cx+m3,cy+m3,fill=rgb_hex(*core),outline="")
        hp=math.sin(t*4)*.5+.5
        m4=int(sunR*(.16+hp*.06))
        O(cx-m4,cy-m4,cx+m4,cy+m4,fill="#ffffff",outline="")
        sx=cx-int(sunR*.3);sy=cy-int(sunR*.32);sr=int(sunR*.28)
        sc2=rgb_hex(*scale_c(lerp_rgb(core,(255,255,255),.6),.4))
        O(sx-sr,sy-sr,sx+sr,sy+sr,fill=sc2,outline="")

        dead=[]
        for rp in self.ripples:
            birth,maxr=rp;age=t-birth;life=1.8
            if age>=life:dead.append(rp);continue
            fr=age/life;r=int(maxr*sc*fr)
            ra=(1-fr)*.55
            rc3=rgb_hex(*scale_c(core,ra))
            if r>1:O(cx-r,cy-r,cx+r,cy+r,outline=rc3,width=max(1,int((1-fr)*3*sc)),fill="")
        for d in dead:self.ripples.remove(d)

        dead2=[]
        for p in self.particles:
            p[0]+=p[2];p[1]+=p[3];p[2]*=.95;p[3]*=.95;p[4]-=.02
            if p[4]<=0:dead2.append(p);continue
            r=max(1,int(p[5]*p[4]*sc))
            pc=rgb_hex(*scale_c(core,p[4]))
            O(p[0]-r,p[1]-r,p[0]+r,p[1]+r,fill=pc,outline="")
        for d in dead2:self.particles.remove(d)

        # ── planets (drawn back-to-front by orbit radius for depth) ───────────
        for pl in sorted(PLANETS,key=lambda pl:pl["r_orbit"]):
            name=pl["name"];pcol=pl["color"]
            p=self.planets[name]
            fx,fy=self._ellipse_point(pl["r_orbit"]*sc,p["angle"],tilt,rot)
            px=cx+fx;py=cy+fy
            psize=int(pl["size"]*sc)
            active=p["active"];flash=p["flash"];status=p["status"]

            # trail
            p["trail"].append((px,py))
            if len(p["trail"])>16:p["trail"].pop(0)
            for i in range(1,len(p["trail"])):
                x1,y1=p["trail"][i-1];x2,y2=p["trail"][i]
                fr=i/len(p["trail"])
                tc=rgb_hex(*scale_c(pcol,fr*.35))
                L(x1,y1,x2,y2,fill=tc,width=max(1,int(fr*2*sc)))

            if active:
                lc=rgb_hex(*scale_c(pcol,.5+.3*math.sin(t*6)))
                L(cx,cy,px,py,fill=lc,width=max(1,int(1.3*sc)))

            glow_amt=max(.15 if active else 0, flash*.5)
            if glow_amt>0:
                gr=int(psize*(2.2+flash))
                gcol=(255,80,80) if status=="error" else pcol
                gc2=rgb_hex(*scale_c(gcol,glow_amt))
                O(px-gr,py-gr,px+gr,py+gr,fill=gc2,outline="")

            # ring (behind planet, back half)
            if pl["ring"]:
                self._draw_ring(px,py,psize,pcol,tilt,rot,sc,behind=True)

            body_c=pcol
            if status=="error":body_c=lerp_rgb(pcol,(255,60,60),.6)
            elif active:body_c=lerp_rgb(pcol,(255,255,255),.2+.12*math.sin(t*8))
            psz2=int(psize*(1.25 if active else 1.0))

            # base sphere
            O(px-psz2,py-psz2,px+psz2,py+psz2,fill=rgb_hex(*body_c),
              outline=rgb_hex(*scale_c(pcol,1.3)),width=1)

            # gas-giant bands
            if pl["bands"]:
                for bi in range(-1,2):
                    by=py+bi*psz2*.42
                    bw=psz2*2*math.sqrt(max(0,1-(bi*.42)**2))
                    band_c=lerp_rgb(pcol,(0,0,0),.18 if bi%2==0 else 0)
                    O(px-bw/2,by-psz2*.16,px+bw/2,by+psz2*.16,
                      fill=rgb_hex(*band_c),outline="")

            # terminator / night-side shadow (away from sun)
            dx,dy=px-cx,py-cy
            dlen=math.hypot(dx,dy) or 1
            ndx,ndy=dx/dlen,dy/dlen
            shx=px+ndx*psz2*.32;shy=py+ndy*psz2*.32
            shr=int(psz2*.92)
            night=lerp_rgb(body_c,(0,0,10),.55)
            O(shx-shr,shy-shr,shx+shr,shy+shr,fill=rgb_hex(*night),outline="")
            # re-draw the lit crescent on top so shadow only covers far side
            O(px-psz2,py-psz2,px+psz2,py+psz2,fill="",outline=rgb_hex(*scale_c(pcol,1.3)),width=1)

            # specular highlight (sun-facing side)
            hs=max(1,int(psz2*.32))
            hlx=px-ndx*psz2*.28;hly=py-ndy*psz2*.28
            O(hlx-hs,hly-hs,hlx+hs,hly+hs,fill="rgba" if False else rgb_hex(*scale_c((255,255,255),.55)),outline="")

            # ring (front half, in front of planet)
            if pl["ring"]:
                self._draw_ring(px,py,psize,pcol,tilt,rot,sc,behind=False)

            # moon for innermost planet
            if pl["moon"]:
                ma=math.radians(self.moon_angle)
                mr=psize*2.6
                mx=px+math.cos(ma)*mr;my=py+math.sin(ma)*mr*tilt
                msz=max(1,int(psize*.28))
                O(mx-msz,my-msz,mx+msz,my+msz,fill=rgb_hex(200,200,210),outline="")

            if active or flash>.3:
                fcol=rgb_hex(*scale_c(pcol,.9))
                T(px,py-psz2-int(11*sc),text=name,fill=fcol,
                  font=("Courier New",max(7,int(8*sc)),"bold"),anchor="center")

        # ── mission banner ───────────────────────────────────────────────────
        if self.mission_active:
            bt=(math.sin(t*3)*.5+.5)
            bc2=rgb_hex(*scale_c((255,200,60),.6+bt*.4))
            T(cx,int(46*sc),text="◆ AGENTS ASSEMBLED — MISSION ACTIVE ◆",
              fill=bc2,font=("Courier New",max(9,int(11*sc)),"bold"),anchor="center")

        # ── HUD text ─────────────────────────────────────────────────────────
        lbl={"IDLE":"STANDBY","WAKE":"ONLINE","LISTENING":"LISTENING",
             "THINKING":"PROCESSING","SPEAKING":"SPEAKING"}[self.state]
        T(cx,H-int(30*sc),text=f"◉  JARVIS — {lbl}",
          fill=rgb_hex(*core),font=("Courier New",max(10,int(13*sc)),"bold"),anchor="center")
        T(cx,H-int(14*sc),
          text='Say "Hey Jarvis" to wake · "Agents assemble" for a mission · "Goodbye" to quit',
          fill=rgb_hex(*scale_c(mid,.7)),font=("Courier New",max(7,int(9*sc))),anchor="center")

        now=datetime.datetime.now()
        T(W-int(16*sc),int(14*sc),text=now.strftime("%H:%M:%S"),
          fill=rgb_hex(*scale_c(core,.85)),font=("Courier New",max(8,int(11*sc)),"bold"),anchor="ne")
        T(W-int(16*sc),int(28*sc),text=now.strftime("%Y-%m-%d"),
          fill=rgb_hex(*scale_c(mid,.5)),font=("Courier New",max(7,int(9*sc))),anchor="ne")

    def _draw_ring(self,px,py,psize,pcol,tilt,rot,sc,behind=True):
        """Draw a Saturn-like ring around a planet, split into back/front halves."""
        cv=self.cv
        def L(*a,**k):self._items.append(cv.create_line(*a,**k))
        ring_tilt=max(.18,tilt*.55)
        rr1=psize*1.5;rr2=psize*2.15
        steps=40
        for ri,rr in enumerate([rr1,rr1*1.25,rr1*1.5,rr2]):
            pts=[]
            for i in range(steps+1):
                ang=i*(360/steps)
                a=math.radians(ang+rot*.3)
                rx=math.cos(a)*rr
                ry=math.sin(a)*rr*ring_tilt
                is_back=math.sin(a)<0
                if is_back!=behind:continue
                pts.extend([px+rx,py+ry])
            if len(pts)>=4:
                alpha=.32-ri*.05
                rc=rgb_hex(*scale_c(pcol,max(.08,alpha)))
                L(*pts,fill=rc,width=1)

class JarvisSolarUI:
    def __init__(self):
        self.root=tk.Tk();self.root.title("J.A.R.V.I.S — Solar System")
        self.root.configure(bg="#00000c");self.root.geometry("1000x680")
        self.root.resizable(True,True)
        try:self.root.attributes("-alpha",.95)
        except:pass
        self._voice=Voice();self._run=True;self._state=State.IDLE
        self._mentor=False;self._handler=None
        self._wake_event=threading.Event();self._fs=False
        self._build();self._start_engine()
        self.root.protocol("WM_DELETE_WINDOW",self._close)
        self.root.bind("<F11>",self._toggle_fs)
        self.root.bind("<Escape>",lambda e:self.root.attributes("-fullscreen",False))

    def _toggle_fs(self,e=None):
        self._fs=not self._fs;self.root.attributes("-fullscreen",self._fs)

    def _build(self):
        self._cv=tk.Canvas(self.root,bg="#00000c",highlightthickness=0)
        self._cv.pack(fill="both",expand=True)
        self._cv.bind("<Configure>",self._on_resize)
        self._sys=SolarSystem(self._cv,1000,680)

    def _on_resize(self,event):
        self._sys.w=event.width;self._sys.h=event.height
        self._sys.cx=event.width//2;self._sys.cy=event.height//2

    def _set_state(self,s):
        self._state=s;self._sys.set_state(s)

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
            self._handler.agents.agent_event=self._sys.agent_event
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
        try:self._sys.stop()
        except:pass
        if hasattr(self,"_mem"):self._mem.save()
        try:self.root.destroy()
        except:pass

    def run(self):self.root.mainloop()

def main():
    print("""
╔═══════════════════════════════════════════════╗
║  J.A.R.V.I.S  ·  SOLAR SYSTEM  ·  v4        ║
║  Jarvis = Sun  ·  Agents = Planets          ║
║  F11 = fullscreen  ·  Esc = windowed        ║
╚═══════════════════════════════════════════════╝""")
    JarvisSolarUI().run()

if __name__=="__main__":
    main()
