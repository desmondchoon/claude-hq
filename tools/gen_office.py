#!/usr/bin/env python3
"""
Claude HQ — office environment art generator (v3, high-detail).

Furniture is enlarged ~1.35x to match the 48px characters and carries much more
detail: dual code-glowing monitors, keyboards/mice, mugs, papers, sticky notes,
desk lamps and desk plants; richer tiles (subtle floor grain + woven rug);
plus new decor — whiteboard, bookshelf, printer — to fill the floor.

Outputs to src/assets/office/ (+ office.json atlas of sizes & draw anchors).
Anchors are [ax, ay] = the pixel inside the sprite that lines up with the
placement coordinate the renderer passes in.
"""
import json, os, random
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(ROOT, "src", "assets", "office")
PREV = os.path.join(ROOT, "tools", "_preview")
os.makedirs(OUT, exist_ok=True); os.makedirs(PREV, exist_ok=True)
random.seed(7)

def shade(rgb, f): return tuple(max(0,min(255,int(c*f))) for c in rgb[:3])

# ---- palette ----
FLOOR1=(238,232,214); FLOOR2=(228,221,201); GROUT=(210,202,180); GRAIN=(220,212,192)
RUG1=(56,104,142); RUG2=(70,124,162); RUG3=(48,92,128); RUGE=(33,70,104)
WOOD=(154,108,62); WOOD_HI=(182,134,84); WOOD_SH=(98,66,34); WOOD_SEAM=(132,90,50)
METAL=(170,170,182); METAL_SH=(108,108,120); METAL_HI=(210,210,220)
MON=(26,26,38); MON_HI=(58,58,82); BEZEL=(40,40,60)
SCR=(46,58,86); SCR_HI=(120,196,232)                      # screen base + glow
CODE=[(120,196,232),(130,210,150),(232,196,110),(208,128,170),(150,160,210)]
SOFA=(70,120,156); SOFA_HI=(98,152,186); SOFA_SH=(46,86,116); SOFA_CU=(86,138,172)
GREEN=(95,180,116); GREEN_D=(64,140,84); GREEN_HI=(146,214,156)
POT=(176,108,66); POT_SH=(132,78,44); POT_HI=(202,138,92)
PAPER=(238,234,222); PAPER_SH=(212,206,190)
MUGA=(206,92,80); MUGB=(110,170,120); MUGC=(120,150,210)
LAMP=(60,62,80); LAMP_HI=(232,214,150)
BLACK=(20,18,26); WHITEB=(238,238,244)

def new(w,h): return Image.new("RGBA",(w,h),(0,0,0,0))
def D(img): return ImageDraw.Draw(img)
def R(d,x0,y0,x1,y1,c): d.rectangle([x0,y0,x1,y1],fill=c)

# ============================ tiles ============================
def floor_tile():
    im=new(16,16); d=D(im)
    R(d,0,0,15,15,FLOOR1)
    R(d,8,0,15,7,FLOOR2); R(d,0,8,7,15,FLOOR2)        # subtle checker
    d.line([0,0,15,0],fill=GROUT); d.line([0,0,0,15],fill=GROUT)
    for (x,y) in [(4,11),(12,3),(6,6),(13,12)]: im.putpixel((x,y),GRAIN)
    im.save(f"{OUT}/floor.png"); return im

def rug_tile():
    im=new(16,16); d=D(im)
    R(d,0,0,15,15,RUG1)
    for x in range(0,16,4): d.line([x,0,x,15],fill=RUG2)   # warp
    for y in range(2,16,4): d.line([0,y,15,y],fill=RUG3)   # weft
    im.putpixel((6,9),RUG2); im.putpixel((13,5),RUG2)
    im.save(f"{OUT}/rug.png"); return im

def wall_tile():
    im=new(16,16); d=D(im)
    R(d,0,0,15,15,(26,22,32))
    d.line([0,0,15,0],fill=(52,46,62)); d.line([0,15,15,15],fill=(16,13,20))
    im.save(f"{OUT}/wall.png"); return im

# ======================= furniture helpers =======================
def wood_top(d,x0,y0,x1,y1):
    R(d,x0,y0,x1,y1,WOOD)
    d.line([x0,y0,x1,y0],fill=WOOD_HI); d.line([x0,y1,x1,y1],fill=WOOD_SH)
    d.line([x0,y0,x0,y1],fill=shade(WOOD,1.05)); d.line([x1,y0,x1,y1],fill=WOOD_SH)
    for yy in range(y0+4,y1,5): d.line([x0+1,yy,x1-1,yy],fill=WOOD_SEAM)

def screen(d,x0,y0,x1,y1,lit=True):
    R(d,x0,y0,x1,y1,SCR if lit else (30,34,46))
    if lit:
        # a few "code" lines
        yy=y0+2; i=0
        while yy<y1-1:
            w=random.randint(4,max(5,(x1-x0)-4)); xx=x0+2
            R(d,xx,yy,min(x1-2,xx+w),yy,CODE[i%len(CODE)]); yy+=2; i+=1
        d.line([x0,y0,x1,y0],fill=shade(SCR_HI,1.0))     # top glow edge

def monitor(d,cx,top,w=30,h=20,lit=True):
    R(d,cx-w//2,top,cx+w//2,top+h,MON)
    d.line([cx-w//2,top,cx+w//2,top],fill=MON_HI)
    R(d,cx-w//2+2,top+2,cx+w//2-2,top+h-3,BEZEL)
    screen(d,cx-w//2+3,top+3,cx+w//2-3,top+h-4,lit)
    R(d,cx-1,top+h,cx+1,top+h+2,METAL_SH)                # stand neck
    R(d,cx-4,top+h+2,cx+4,top+h+3,METAL_SH)              # foot

def keyboard(d,cx,y,w=26):
    R(d,cx-w//2,y,cx+w//2,y+5,(44,44,58)); R(d,cx-w//2,y,cx+w//2,y,(64,64,82))
    for xx in range(cx-w//2+2,cx+w//2-1,3): d.point((xx,y+2),fill=(96,96,116))

def mug(d,x,y,col):
    R(d,x,y,x+5,y+5,col); R(d,x,y,x+5,y,shade(col,1.25))
    d.point((x+6,y+1),fill=col); d.point((x+6,y+2),fill=col)   # handle
    R(d,x+1,y+1,x+4,y+1,(248,244,236))                          # liquid/steam top

def papers(d,x,y):
    R(d,x,y,x+10,y+12,PAPER); R(d,x+2,y-2,x+12,y+10,PAPER)
    d.line([x+2,y-2,x+12,y-2],fill=PAPER_SH)
    for ln in range(y+1,y+9,2): d.line([x+4,ln,x+10,ln],fill=(176,172,158))

def sticky(d,x,y,col=(240,224,120)):
    R(d,x,y,x+6,y+6,col); R(d,x,y,x+6,y,shade(col,1.1))

def lamp(d,x,y):
    R(d,x,y+4,x+4,y+10,LAMP); R(d,x+1,y,x+6,y+3,LAMP)
    R(d,x+2,y+1,x+5,y+2,LAMP_HI)

def deskplant(d,x,y):
    R(d,x,y+4,x+5,y+8,POT); d.ellipse([x-2,y-3,x+7,y+5],fill=GREEN_D); d.ellipse([x,y-4,x+5,y+1],fill=GREEN)

def chair(d,cx,cy,col=METAL):
    R(d,cx-9,cy-9,cx+9,cy+8,col)
    d.line([cx-9,cy-9,cx+9,cy-9],fill=METAL_HI)
    R(d,cx-9,cy+5,cx+9,cy+8,METAL_SH)
    R(d,cx-9,cy-9,cx-9,cy+8,shade(col,0.85)); R(d,cx+9,cy-9,cx+9,cy+8,shade(col,0.85))

# ======================= furniture sprites =======================
def cubicle():
    W,H=120,90; im=new(W,H); d=D(im)                     # anchor (60,56)
    # partition wall behind (cubicle feel)
    R(d,4,2,W-4,12,METAL_SH); R(d,4,2,W-4,4,METAL)
    R(d,4,2,9,40,METAL_SH); R(d,W-9,2,W-4,40,METAL_SH)
    R(d,4,2,9,40,METAL_SH); d.line([6,4,6,40],fill=METAL)
    # pinned sticky notes on partition
    sticky(d,18,6,(240,224,120)); sticky(d,30,7,(150,210,170)); sticky(d,W-30,6,(210,160,210))
    # desk surface
    wood_top(d,10,30,W-10,56)
    # dual monitors
    monitor(d,W//2-18,10,34,22); monitor(d,W//2+20,12,30,20)
    keyboard(d,W//2,40,30)
    R(d,W//2+20,40,W//2+24,44,(44,44,58))                # mouse
    mug(d,24,38,MUGA); deskplant(d,W-22,34); lamp(d,18,28)
    papers(d,W-40,40)
    chair(d,W//2,70)
    im.save(f"{OUT}/cubicle.png"); return im,(60,56)

def desk():
    W,H=108,72; im=new(W,H); d=D(im)                     # anchor (54,42)
    wood_top(d,8,22,W-8,48)
    R(d,12,48,16,58,WOOD_SH); R(d,W-16,48,W-12,58,WOOD_SH)   # legs
    monitor(d,W//2-14,4,32,20); monitor(d,W//2+20,8,26,16)
    keyboard(d,W//2-4,32,28)
    papers(d,24,30); mug(d,W-30,28,MUGB); deskplant(d,W-20,24)
    chair(d,W//2,64)
    im.save(f"{OUT}/desk.png"); return im,(54,42)

def desk_front():
    # Drawn OVER a DOWN-facing seated agent: monitor backs toward viewer,
    # keyboard between agent & monitor, chair arms frame the agent.
    W,H=116,58; im=new(W,H); d=D(im); cx=W//2               # anchor (58,14)
    d.rounded_rectangle([2,2,16,30],3,fill=METAL_SH); d.rounded_rectangle([4,4,14,18],2,fill=METAL)
    d.rounded_rectangle([W-16,2,W-2,30],3,fill=METAL_SH); d.rounded_rectangle([W-14,4,W-4,18],2,fill=METAL)
    wood_top(d,10,16,W-10,34)
    keyboard(d,cx,20,34)
    mug(d,W-34,18,MUGB); papers(d,24,18); sticky(d,W-22,17)
    # two monitors seen from the back, near edge
    for mx,mw in ((cx-20,30),(cx+18,26)):
        R(d,mx-mw//2,34,mx+mw//2,52,shade(MON,0.9))
        R(d,mx-mw//2,34,mx+mw//2,35,SCR_HI)             # glow spill toward agent
        R(d,mx-mw//2+2,36,mx+mw//2-2,50,MON)
        R(d,mx-2,52,mx+2,54,METAL_SH)
    im.save(f"{OUT}/desk_front.png"); return im,(58,14)

def sofa():
    W,H=110,56; im=new(W,H); d=D(im)                     # anchor (55,32)
    d.rounded_rectangle([2,2,W-2,20],4,fill=SOFA_SH); R(d,2,2,W-2,5,SOFA_HI)
    d.rounded_rectangle([0,16,W,42],4,fill=SOFA)
    d.rounded_rectangle([0,10,12,46],4,fill=SOFA_HI)
    d.rounded_rectangle([W-12,10,W,46],4,fill=SOFA_HI)
    # two cushions
    d.rounded_rectangle([14,18,W//2-2,30],3,fill=SOFA_CU); d.rounded_rectangle([W//2+2,18,W-14,30],3,fill=SOFA_CU)
    d.line([W//2,18,W//2,40],fill=SOFA_SH)
    R(d,6,42,W-6,46,shade(SOFA_SH,0.7))                  # base shadow
    im.save(f"{OUT}/sofa.png"); return im,(55,32)

def table():
    W,H=200,200; im=new(W,H); d=D(im)                    # anchor (100,100)
    for cx,cy in [(56,22),(144,22),(56,H-22),(144,H-22),(20,72),(20,128),(W-20,72),(W-20,128)]:
        chair(d,cx,cy)
    d.rounded_rectangle([34,34,W-34,H-34],10,fill=WOOD_SH)
    d.rounded_rectangle([38,38,W-38,H-40],10,fill=WOOD)
    d.line([38,38,W-38,38],fill=WOOD_HI)
    for yy in range(46,H-40,6): d.line([42,yy,W-42,yy],fill=WOOD_SEAM)
    # centerpiece + laptops
    d.ellipse([W//2-14,H//2-10,W//2+14,H//2+16],fill=POT); d.ellipse([W//2-16,H//2-22,W//2+16,H//2+4],fill=GREEN_D)
    d.ellipse([W//2-10,H//2-24,W//2+8,H//2-6],fill=GREEN)
    for lx,ly in [(64,66),(120,120),(120,60)]:
        R(d,lx,ly,lx+22,ly+12,(44,44,58)); R(d,lx,ly,lx+22,ly+1,SCR_HI)
    im.save(f"{OUT}/table.png"); return im,(100,100)

def plant(big=False):
    W,H=(40,52) if big else (28,36); im=new(W,H); d=D(im); cx=W//2     # anchor (cx, H-2)
    d.polygon([(cx-9,H-2),(cx+9,H-2),(cx+6,H-16),(cx-6,H-16)],fill=POT)
    d.line([cx-6,H-16,cx+6,H-16],fill=POT_HI)
    d.polygon([(cx-9,H-2),(cx+9,H-2),(cx+7,H-7),(cx-7,H-7)],fill=POT_SH)
    top=H-16
    d.ellipse([cx-12,top-18,cx+12,top+3],fill=GREEN_D)
    d.ellipse([cx-9,top-22,cx+6,top-4],fill=GREEN)
    d.ellipse([cx-3,top-25,cx+10,top-10],fill=GREEN_HI)
    if big:
        d.ellipse([cx-14,top-10,cx-2,top+5],fill=GREEN)
        d.ellipse([cx+2,top-8,cx+14,top+7],fill=GREEN_D)
        d.ellipse([cx-2,top-28,cx+8,top-16],fill=GREEN_HI)
    im.save(f"{OUT}/{'plant_big' if big else 'plant'}.png"); return im,(cx,H-2)

def counter():
    W,H=300,120; im=new(W,H); d=D(im)                    # anchor (0,0)
    R(d,0,0,W,H,WOOD)
    R(d,0,0,W,4,WOOD_HI); R(d,0,H-5,W,H,WOOD_SH)
    for xx in range(0,W,46): d.line([xx,6,xx,H],fill=WOOD_SEAM)
    R(d,0,0,W,12,(236,232,220))                          # countertop strip
    R(d,0,0,W,2,(250,248,240))
    # coffee machine
    R(d,24,18,62,64,METAL_SH); R(d,24,18,62,22,METAL); R(d,28,24,58,40,BLACK)
    R(d,38,48,52,60,METAL_SH); R(d,40,52,50,58,(120,76,32))
    d.point((33,30),fill=SCR_HI)
    # sink
    R(d,96,22,150,60,METAL_SH); R(d,100,26,146,56,(150,160,172)); R(d,120,16,124,26,METAL)
    # microwave
    R(d,170,20,224,58,(60,60,74)); R(d,174,24,210,54,BLACK); R(d,178,28,206,50,(40,46,60)); R(d,214,26,220,52,(120,120,140))
    # snack bowl + plant
    d.ellipse([238,30,278,50],fill=WOOD_HI); d.ellipse([244,26,272,44],fill=(232,192,96))
    R(d,W-26,26,W-14,40,POT); d.ellipse([W-32,14,W-8,34],fill=GREEN_D); d.ellipse([W-28,12,W-12,28],fill=GREEN)
    im.save(f"{OUT}/counter.png"); return im,(0,0)

def pingpong():
    W,H=130,76; im=new(W,H); d=D(im)                     # anchor (65,38)
    R(d,6,8,W-6,H-8,(46,120,80)); R(d,6,8,W-6,11,(70,150,100))
    d.rectangle([8,11,W-8,H-11],outline=(236,236,236))
    d.line([W//2,11,W//2,H-11],fill=(236,236,236))
    R(d,W//2-1,4,W//2+1,H-4,(224,224,234))               # net
    d.ellipse([14,H-24,28,H-10],fill=(200,80,70)); d.ellipse([W-28,10,W-14,24],fill=(44,44,58))
    d.ellipse([W//2+14,H//2-2,W//2+19,H//2+3],fill=(240,150,60))   # ball
    im.save(f"{OUT}/pingpong.png"); return im,(65,38)

def door():
    W,H=22,72; im=new(W,H); d=D(im)                      # anchor (0,36)
    R(d,0,0,W,H,(14,12,20)); R(d,3,3,W-3,H-3,METAL_SH); R(d,5,5,W-5,H-5,(60,56,72))
    d.line([0,0,0,H],fill=METAL); R(d,W-8,H//2-3,W-6,H//2+3,METAL_HI)   # handle
    im.save(f"{OUT}/door.png"); return im,(0,36)

def watercooler():
    W,H=28,40; im=new(W,H); d=D(im)                      # anchor (14,H-1)
    R(d,5,16,23,H-1,(222,230,238)); R(d,5,16,23,19,(192,202,212))
    d.ellipse([3,0,25,20],fill=(150,200,230)); d.ellipse([8,3,20,13],fill=(186,220,240))
    R(d,10,H-9,18,H-2,(120,140,160)); d.point((14,H-12),fill=(90,110,130))
    im.save(f"{OUT}/watercooler.png"); return im,(14,H-1)

# ----------------------------- NEW decor -----------------------------
def whiteboard():
    W,H=84,52; im=new(W,H); d=D(im)                      # anchor (42, H-2) stands against wall
    R(d,4,2,W-4,40,(70,66,82)); R(d,6,4,W-6,36,WHITEB)   # frame + board
    # scribbles / diagram
    d.line([12,12,40,12],fill=(90,140,200)); d.line([12,18,32,18],fill=(120,180,140))
    d.line([12,24,44,24],fill=(210,150,90))
    d.rectangle([52,10,72,28],outline=(200,90,120)); d.line([62,10,62,28],fill=(200,90,120))
    R(d,10,38,W-10,42,(60,56,72))                        # tray
    R(d,16,42,20,H-2,(70,66,82)); R(d,W-20,42,W-16,H-2,(70,66,82))   # legs
    im.save(f"{OUT}/whiteboard.png"); return im,(42,H-2)

def bookshelf():
    W,H=64,80; im=new(W,H); d=D(im)                      # anchor (32, H-2)
    R(d,2,2,W-2,H-2,WOOD_SH); R(d,4,4,W-4,H-4,shade(WOOD,0.8))
    cols=[(196,92,80),(120,170,120),(120,150,210),(232,196,110),(150,160,210),(208,128,170),(110,180,170)]
    for si,sy in enumerate(range(8,H-10,18)):
        R(d,5,sy+13,W-5,sy+15,WOOD)                      # shelf board
        x=7
        while x<W-9:
            bw=random.randint(3,6); bh=random.randint(9,13); col=cols[(x+si)%len(cols)]
            R(d,x,sy+14-bh,x+bw,sy+13,col); R(d,x,sy+14-bh,x+bw,sy+14-bh,shade(col,1.2))
            x+=bw+1
    im.save(f"{OUT}/bookshelf.png"); return im,(32,H-2)

def printer():
    W,H=44,52; im=new(W,H); d=D(im)                      # anchor (22, H-2)
    R(d,4,12,W-4,H-2,(74,74,88)); R(d,4,12,W-4,16,(102,102,118))
    R(d,8,2,W-8,14,(60,60,74)); R(d,12,6,W-12,11,BLACK)  # top tray
    R(d,8,30,W-8,40,(40,40,52))                          # output slot
    R(d,10,32,W-10,33,PAPER)
    d.point((W-12,20),fill=(120,210,150)); d.point((W-16,20),fill=(232,150,60))
    im.save(f"{OUT}/printer.png"); return im,(22,H-2)

# ============================== build ==============================
def build():
    floor_tile(); rug_tile(); wall_tile()
    anchors={}
    for fn,name in [(cubicle,"cubicle"),(desk,"desk"),(desk_front,"desk_front"),
                    (sofa,"sofa"),(table,"table"),(counter,"counter"),
                    (pingpong,"pingpong"),(door,"door"),(watercooler,"watercooler"),
                    (whiteboard,"whiteboard"),(bookshelf,"bookshelf"),(printer,"printer")]:
        _,a=fn(); anchors[name]=a
    _,a=plant();     anchors["plant"]=a
    _,a=plant(True); anchors["plant_big"]=a
    atlas={"anchors":anchors,
           "tiles":{"floor":"floor.png","rug":"rug.png","wall":"wall.png"},
           "rugEdge":list(RUGE)}
    with open(f"{OUT}/office.json","w") as f: json.dump(atlas,f,indent=2)
    return atlas

def contact():
    files=["cubicle","desk","desk_front","sofa","table","plant","plant_big","counter",
           "pingpong","door","watercooler","whiteboard","bookshelf","printer"]
    scale=3; pad=12
    imgs=[(n,Image.open(f"{OUT}/{n}.png")) for n in files]
    totw=sum(i.size[0]*scale+pad for _,i in imgs)+pad
    maxh=max(i.size[1] for _,i in imgs)*scale
    canvas=Image.new("RGBA",(totw, maxh+40),(236,230,212,255))
    floor=Image.open(f"{OUT}/floor.png")
    for ty in range(0,canvas.size[1],16):
        for tx in range(0,canvas.size[0],16): canvas.paste(floor,(tx,ty))
    x=pad
    for n,i in imgs:
        big=i.resize((i.size[0]*scale,i.size[1]*scale),Image.NEAREST)
        canvas.paste(big,(x, 20),big); x+=i.size[0]*scale+pad
    canvas.save(f"{PREV}/office_contact.png"); print("office contact ->",canvas.size)

if __name__=="__main__":
    a=build(); contact()
    print("OK office v3. pieces:",list(a["anchors"].keys()))
