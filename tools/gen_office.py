#!/usr/bin/env python3
"""
Claude HQ — office environment art generator.

Outputs to src/assets/office/:
  floor.png      16x16  tileable warm floor
  rug.png        16x16  tileable blue carpet
  wall.png       16x16  tileable dark wall (border ring)
  cubicle.png           desk + partition + monitor (faces top wall)
  desk.png              free-standing desk + monitor + keyboard
  sofa.png              2-seat sofa (blue)
  table.png             conference table + 4 chairs
  plant.png             potted plant (small)
  plant_big.png         potted plant (large, lounge/decor)
  counter.png           kitchenette counter + coffee machine + snacks
  pingpong.png          ping-pong table (lounge flair)
  door.png              door frame on the left wall
  office.json           atlas: sizes + draw anchors (top-left offset) for each piece

Anchors are stored as [ax, ay] = the pixel inside the sprite that should line
up with the placement coordinate the renderer passes in.
"""
import json, os
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(ROOT, "src", "assets", "office")
PREV = os.path.join(ROOT, "tools", "_preview")
os.makedirs(OUT, exist_ok=True); os.makedirs(PREV, exist_ok=True)

def shade(rgb, f):
    return tuple(max(0,min(255,int(c*f))) for c in rgb[:3])

# palette (matches renderer PAL)
FLOOR1=(236,230,212); FLOOR2=(220,212,190); GROUT=(206,198,176)
RUG1=(58,106,144); RUG2=(74,130,168); RUGE=(35,72,106)
WALL=(26,22,32); WALLHI=(52,46,62); WALLSH=(16,13,20)
WOOD=(150,104,60); WOOD_HI=(176,128,80); WOOD_SH=(96,64,32)
METAL=(168,168,180); METAL_SH=(106,106,118); METAL_HI=(206,206,216)
MON=(28,28,40); BEZEL=(44,44,64); SCREEN=(86,150,196); SCREEN2=(120,190,150)
SOFA=(70,120,156); SOFA_HI=(96,150,184); SOFA_SH=(46,86,116)
GREEN=(95,180,116); GREEN_D=(64,140,84); GREEN_HI=(140,210,150)
POT=(150,96,60); POT_SH=(110,68,40)
BLACK=(20,18,26)

def new(w,h): return Image.new("RGBA",(w,h),(0,0,0,0))
def D(img): return ImageDraw.Draw(img)

# ---------- tiles ----------
def floor_tile():
    im=new(16,16); d=D(im)
    d.rectangle([0,0,15,15],fill=FLOOR1)
    # subtle 8x8 checker
    d.rectangle([8,0,15,7],fill=FLOOR2)
    d.rectangle([0,8,7,15],fill=FLOOR2)
    # grout lines on top/left for seamless tile grid
    d.line([0,0,15,0],fill=GROUT); d.line([0,0,0,15],fill=GROUT)
    # speck of grain
    im.putpixel((4,11),GROUT); im.putpixel((12,3),GROUT)
    im.save(f"{OUT}/floor.png"); return im

def rug_tile():
    im=new(16,16); d=D(im)
    d.rectangle([0,0,15,15],fill=RUG1)
    for x in range(0,16,2): d.line([x,0,x,15],fill=RUG2)  # weave
    im.save(f"{OUT}/rug.png"); return im

def wall_tile():
    im=new(16,16); d=D(im)
    d.rectangle([0,0,15,15],fill=WALL)
    d.line([0,0,15,0],fill=WALLHI)     # top highlight
    d.line([0,15,15,15],fill=WALLSH)   # bottom shadow
    im.save(f"{OUT}/wall.png"); return im

# ---------- furniture helpers ----------
def wood_top(d,x0,y0,x1,y1):
    d.rectangle([x0,y0,x1,y1],fill=WOOD)
    d.line([x0,y0,x1,y0],fill=WOOD_HI)
    d.line([x0,y1,x1,y1],fill=WOOD_SH)
    # plank seams
    for yy in range(y0+3,y1,4):
        d.line([x0,yy,x1,yy],fill=shade(WOOD,0.9))

def monitor(d,cx,top,w=24,h=14,glow=SCREEN):
    d.rectangle([cx-w//2,top,cx+w//2,top+h],fill=MON)
    d.rectangle([cx-w//2+2,top+2,cx+w//2-2,top+h-3],fill=BEZEL)
    d.rectangle([cx-w//2+3,top+3,cx+w//2-3,top+h-4],fill=glow)
    d.line([cx-w//2+3,top+3,cx+w//2-3,top+3],fill=shade(glow,1.3))
    # stand
    d.rectangle([cx-1,top+h,cx+1,top+h+2],fill=METAL_SH)

def chair(d,cx,cy,col=METAL):
    d.rectangle([cx-7,cy-7,cx+7,cy+6],fill=col)
    d.line([cx-7,cy-7,cx+7,cy-7],fill=METAL_HI)
    d.rectangle([cx-7,cy+4,cx+7,cy+6],fill=METAL_SH)

# ---------- furniture sprites ----------
def cubicle():
    # 88 x 64, anchor at (44, 40) -> placement = seat (x,y)
    W,H=88,64; im=new(W,H); d=D(im)
    # partition (L behind desk)
    d.rectangle([6,2,W-6,8],fill=METAL_SH)
    d.rectangle([6,2,W-6,3],fill=METAL)
    d.rectangle([6,2,9,30],fill=METAL_SH)
    d.rectangle([W-9,2,W-6,30],fill=METAL_SH)
    # desk against partition
    wood_top(d,8,24,W-8,42)
    # monitor on desk
    monitor(d,W//2,8,28,16,SCREEN)
    # keyboard + mouse
    d.rectangle([W//2-12,30,W//2+8,36],fill=(40,40,52))
    d.rectangle([W//2+12,31,W//2+16,35],fill=(40,40,52))
    # mug
    d.ellipse([18,28,24,34],fill=(200,90,80))
    # chair below
    chair(d,W//2,50)
    im.save(f"{OUT}/cubicle.png"); return im,(44,40)

def desk():
    # 80 x 52, anchor (40, 30)
    W,H=80,52; im=new(W,H); d=D(im)
    # desktop
    wood_top(d,6,16,W-6,36)
    # legs
    d.rectangle([8,36,11,42],fill=WOOD_SH); d.rectangle([W-11,36,W-8,42],fill=WOOD_SH)
    # monitor (far edge)
    monitor(d,W//2,2,26,14,SCREEN)
    # keyboard + papers
    d.rectangle([W//2-12,24,W//2+8,30],fill=(40,40,52))
    d.rectangle([18,22,30,30],fill=(238,234,220)); d.line([18,22,30,22],fill=(210,205,188))
    # mug
    d.ellipse([W-26,20,W-20,26],fill=(120,170,120))
    # chair
    chair(d,W//2,46)
    im.save(f"{OUT}/desk.png"); return im,(40,30)

def desk_front():
    # Desk for a DOWN-facing worker: drawn OVER the agent so they read as
    # sitting behind it. Monitor shown from the BACK (toward viewer), keyboard
    # between agent and monitor, chair armrests framing the agent's sides.
    # 84 x 42, anchor (42, 10) -> placement = seat (x,y).
    W,H=84,42; im=new(W,H); d=D(im); cx=W//2
    # chair armrests (frame the seated agent)
    d.rounded_rectangle([2,2,12,22],3,fill=METAL_SH); d.rounded_rectangle([3,3,11,13],2,fill=METAL)
    d.rounded_rectangle([W-12,2,W-2,22],3,fill=METAL_SH); d.rounded_rectangle([W-11,3,W-3,13],2,fill=METAL)
    # desk surface (in front of the agent's lap)
    wood_top(d,8,12,W-8,26)
    # keyboard near the agent
    d.rectangle([cx-14,15,cx+14,21],fill=(40,40,52)); d.rectangle([cx-14,15,cx+14,16],fill=(60,60,76))
    d.rectangle([W-26,15,W-16,21],fill=(120,170,120))  # mug
    # monitor seen from behind, at the near (front) edge
    d.rectangle([cx-16,26,cx+16,40],fill=shade(MON,0.85))
    d.rectangle([cx-16,26,cx+16,27],fill=SCREEN)        # screen glow spilling up toward agent
    d.rectangle([cx-14,28,cx+14,39],fill=MON)
    d.rectangle([cx-3,40,cx+3,42],fill=METAL_SH)        # stand foot
    im.save(f"{OUT}/desk_front.png"); return im,(42,10)

def sofa():
    # 80 x 40, anchor (40, 24) ; faces "down" (back at top)
    W,H=80,40; im=new(W,H); d=D(im)
    # backrest
    d.rounded_rectangle([2,2,W-2,14],3,fill=SOFA_SH)
    d.rectangle([2,2,W-2,4],fill=SOFA_HI)
    # seat
    d.rounded_rectangle([0,12,W,30],3,fill=SOFA)
    # arms
    d.rounded_rectangle([0,8,8,32],3,fill=SOFA_HI)
    d.rounded_rectangle([W-8,8,W,32],3,fill=SOFA_HI)
    # cushions seam
    d.line([W//2,14,W//2,28],fill=SOFA_SH)
    d.line([8,14,W-8,14],fill=SOFA_HI)
    # base shadow
    d.rectangle([4,30,W-4,33],fill=shade(SOFA_SH,0.7))
    im.save(f"{OUT}/sofa.png"); return im,(40,24)

def table():
    # conference: 150 x 150 with 4 chairs, anchor (75, 75) = table center
    W,H=150,150; im=new(W,H); d=D(im)
    # chairs around (top,bottom,left,right) drawn first (under table edges)
    chair(d,40,18); chair(d,110,18)        # top
    chair(d,40,H-18); chair(d,110,H-18)    # bottom
    chair(d,16,55); chair(d,16,95)         # left
    chair(d,W-16,55); chair(d,W-16,95)     # right
    # table top
    d.rounded_rectangle([26,26,W-26,H-26],8,fill=WOOD_SH)
    d.rounded_rectangle([29,29,W-29,H-30],8,fill=WOOD)
    d.line([29,29,W-29,29],fill=WOOD_HI)
    for yy in range(36,H-30,6): d.line([30,yy,W-30,yy],fill=shade(WOOD,0.92))
    # centerpiece plant
    d.ellipse([W//2-10,H//2-8,W//2+10,H//2+12],fill=POT)
    d.ellipse([W//2-12,H//2-16,W//2+12,H//2+2],fill=GREEN_D)
    d.ellipse([W//2-8,H//2-18,W//2+6,H//2-4],fill=GREEN)
    # laptops on table
    d.rectangle([46,52,66,62],fill=(40,40,52)); d.rectangle([46,52,66,53],fill=SCREEN)
    d.rectangle([90,90,110,100],fill=(40,40,52)); d.rectangle([90,99,110,100],fill=SCREEN)
    im.save(f"{OUT}/table.png"); return im,(75,75)

def plant(big=False):
    W,H=(28,34) if big else (20,26); im=new(W,H); d=D(im)
    cx=W//2
    # pot
    d.polygon([(cx-7,H-2),(cx+7,H-2),(cx+5,H-12),(cx-5,H-12)],fill=POT)
    d.line([cx-5,H-12,cx+5,H-12],fill=shade(POT,1.2))
    d.polygon([(cx-7,H-2),(cx+7,H-2),(cx+6,H-5),(cx-6,H-5)],fill=POT_SH)
    # foliage
    top=H-12
    d.ellipse([cx-9,top-14,cx+9,top+2],fill=GREEN_D)
    d.ellipse([cx-7,top-18,cx+5,top-4],fill=GREEN)
    d.ellipse([cx-2,top-20,cx+8,top-8],fill=GREEN_HI)
    if big:
        d.ellipse([cx-11,top-8,cx-1,top+4],fill=GREEN)
        d.ellipse([cx+1,top-6,cx+11,top+6],fill=GREEN_D)
    im.save(f"{OUT}/{'plant_big' if big else 'plant'}.png");
    return im,(W//2,H-2)

def counter():
    # kitchenette 220 x 96, anchor (0,0) top-left placement
    W,H=220,96; im=new(W,H); d=D(im)
    # counter top
    d.rectangle([0,0,W,H],fill=WOOD)
    d.rectangle([0,0,W,3],fill=WOOD_HI)
    d.rectangle([0,H-4,W,H],fill=WOOD_SH)
    for xx in range(0,W,40): d.line([xx,0,xx,H],fill=shade(WOOD,0.92))
    # white countertop strip
    d.rectangle([0,0,W,10],fill=(236,232,220))
    # coffee machine
    d.rectangle([20,16,52,52],fill=METAL_SH); d.rectangle([20,16,52,20],fill=METAL)
    d.rectangle([24,22,48,32],fill=BLACK)
    d.rectangle([30,38,42,48],fill=METAL_SH); d.rectangle([32,42,40,46],fill=(93,58,24))
    # snack bowl
    d.ellipse([90,30,128,46],fill=WOOD_HI); d.ellipse([96,28,122,40],fill=(232,192,96))
    # plant on counter
    d.rectangle([170,28,186,44],fill=POT); d.ellipse([164,16,192,34],fill=GREEN_D); d.ellipse([170,12,188,28],fill=GREEN)
    im.save(f"{OUT}/counter.png"); return im,(0,0)

def pingpong():
    # 96 x 56, anchor (48,28)
    W,H=96,56; im=new(W,H); d=D(im)
    d.rectangle([4,6,W-4,H-6],fill=(46,120,80))         # table green
    d.rectangle([4,6,W-4,8],fill=(70,150,100))
    d.rectangle([6,8,W-6,H-8],outline=(236,236,236))    # white border
    d.line([W//2,8,W//2,H-8],fill=(236,236,236))        # center line
    d.rectangle([W//2-1,2,W//2+1,H-2],fill=(220,220,230))  # net
    # paddles
    d.ellipse([10,H-18,20,H-8],fill=(200,80,70))
    d.ellipse([W-20,8,W-10,18],fill=(40,40,52))
    im.save(f"{OUT}/pingpong.png"); return im,(48,28)

def door():
    # 16 x 56 door on left wall, anchor (0,28)
    W,H=16,56; im=new(W,H); d=D(im)
    d.rectangle([0,0,W,H],fill=(14,12,20))
    d.rectangle([2,2,W-2,H-2],fill=METAL_SH)
    d.rectangle([4,4,W-4,H-4],fill=(58,54,70))
    d.line([0,0,0,H],fill=METAL)
    im.save(f"{OUT}/door.png"); return im,(0,28)

def watercooler():
    W,H=20,28; im=new(W,H); d=D(im)
    d.rectangle([4,10,16,H-1],fill=(220,228,236))      # body
    d.rectangle([4,10,16,12],fill=(190,200,210))
    d.ellipse([3,0,17,14],fill=(150,200,230))          # bottle
    d.rectangle([7,H-6,13,H-1],fill=(120,140,160))
    im.save(f"{OUT}/watercooler.png"); return im,(10,H-1)

# ---------- build ----------
def build():
    floor_tile(); rug_tile(); wall_tile()
    anchors={}
    _,a=cubicle();   anchors["cubicle"]=a
    _,a=desk();      anchors["desk"]=a
    _,a=desk_front();anchors["desk_front"]=a
    _,a=sofa();      anchors["sofa"]=a
    _,a=table();     anchors["table"]=a
    _,a=plant();     anchors["plant"]=a
    _,a=plant(True); anchors["plant_big"]=a
    _,a=counter();   anchors["counter"]=a
    _,a=pingpong();  anchors["pingpong"]=a
    _,a=door();      anchors["door"]=a
    _,a=watercooler();anchors["watercooler"]=a
    atlas={"anchors":anchors,
           "tiles":{"floor":"floor.png","rug":"rug.png","wall":"wall.png"},
           "rugEdge":list(RUGE)}
    with open(f"{OUT}/office.json","w") as f: json.dump(atlas,f,indent=2)
    return atlas

def contact():
    files=["cubicle","desk","sofa","table","plant","plant_big","counter","pingpong","door","watercooler"]
    scale=4; pad=12
    imgs=[(n,Image.open(f"{OUT}/{n}.png")) for n in files]
    maxw=max(i.size[0] for _,i in imgs)*scale
    totw=sum(i.size[0]*scale+pad for _,i in imgs)+pad
    maxh=max(i.size[1] for _,i in imgs)*scale
    # floor + rug background swatch
    canvas=Image.new("RGBA",(totw, maxh+40),(236,230,212,255))
    floor=Image.open(f"{OUT}/floor.png")
    for ty in range(0,canvas.size[1],16):
        for tx in range(0,canvas.size[0],16):
            canvas.paste(floor,(tx,ty))
    x=pad
    for n,i in imgs:
        big=i.resize((i.size[0]*scale,i.size[1]*scale),Image.NEAREST)
        canvas.paste(big,(x, 20),big)
        x+=i.size[0]*scale+pad
    canvas.save(f"{PREV}/office_contact.png")
    print("office contact ->",canvas.size)

if __name__=="__main__":
    a=build(); contact()
    print("OK office. pieces:",list(a["anchors"].keys()))
