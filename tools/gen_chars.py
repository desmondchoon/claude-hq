#!/usr/bin/env python3
"""
Claude HQ — LAYERED character generator (v3, 48px high-detail).

Outputs separable layers so each agent is a distinct, polished person composed
at runtime:
  body_skin{0..N}.png   skin head+face+hands, pants, shoes  (fixed colors)
  hair_{style}.png      grayscale hair shape                (tinted to hair color)
  agent_shirt.png       grayscale shirt+sleeves             (tinted to STATE color)
  acc_{glasses,headphones,cap}.png  accessory               (fixed colors)
  outline_{style}_{acc}.png   dark 1px shape outline         (per silhouette)
  agent.json            atlas: cell/anchor/anims + layer templates + variety dims

Grid: 4 cols x 6 rows of 48x48 (v2 was 32x32 — this is the resolution bump).
  row0 walk_down 0-3 | row1 walk_up 0-3 | row2 walk_left 0-3 | row3 walk_right 0-3
  row4 sit_down(0,1) sit_up(2,3) | row5 sit_left(0,1) sit_right(2,3)
Idle = walk frame 0 (atlas alias).

Coordinates are authored directly at 48px. Compared with v2 the extra pixels
buy: a real face (eyes/brow/nose/mouth/ears + cheek + jaw shading), volumetric
hair with highlights, shaded shirt (collar, shoulder seams, sleeve shadow),
shaded pants, and 2 new hairstyles + 1 new accessory.
"""
import os, json
from PIL import Image, ImageDraw

CELL=48; COLS=4; ROWS=6
CX=24                      # body centre column
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT=os.path.join(ROOT,"src","assets","characters")
PREV=os.path.join(ROOT,"tools","_preview")
os.makedirs(OUT,exist_ok=True); os.makedirs(PREV,exist_ok=True)

def sh(c,f): return tuple(max(0,min(255,int(v*f))) for v in c[:3])

# ---- fixed colours (body layer) ----
PANTS=(58,50,104); PANTS_S=(40,34,78); PANTS_H=(82,72,134); SHOE=(30,28,40); SHOE_H=(54,50,66)
WHITE=(250,250,252,255); PUP=(40,32,52,255); BROW=(96,70,58,255)
MOUTH=(176,108,96,255)
OUTLINE=(34,28,46,255)
# accessory colours
CUP=(52,56,78,255); CUP_HI=(96,100,132,255); CUP_LO=(36,39,56,255); BAND=(70,74,100,255)
GLASS_FR=(40,40,54,255); LENS=(150,200,228,120); GLASS_HI=(196,226,242,200)
CAP=(74,92,150,255); CAP_HI=(108,128,190,255); CAP_SH=(50,64,110,255); CAP_BRIM=(44,56,96,255)

SKIN_TONES=[
 ((247,206,160),(214,165,118),(255,226,190)),
 ((233,178,128),(196,140,96),(246,200,156)),
 ((205,150,108),(168,116,78),(224,176,134)),
 ((168,116,80),(128,84,54),(196,146,104)),
 ((120,82,56),(88,56,36),(150,108,76)),
]
HAIR_COLORS=[(45,36,56),(120,68,46),(212,160,96),(86,160,192),(192,90,144),
             (74,74,86),(208,208,214),(150,52,52),(110,84,168)]
STYLES=["short","long","bun","curly","spiky"]
ACCS=["none","glasses","headphones","cap"]

# grayscale ink for tintable layers (bright so multiply keeps colour vivid)
S_HI=(255,255,255,255); S_MID=(222,222,222,255); S_LO=(176,176,176,255); S_LO2=(138,138,138,255)
H_HI=(255,255,255,255); H_MID=(206,206,206,255); H_LO=(150,150,150,255); H_LO2=(116,116,116,255)

class Cell:
    def __init__(s):
        s.body =Image.new("RGBA",(CELL,CELL),(0,0,0,0))
        s.hair =Image.new("RGBA",(CELL,CELL),(0,0,0,0))
        s.shirt=Image.new("RGBA",(CELL,CELL),(0,0,0,0))
        s.acc  =Image.new("RGBA",(CELL,CELL),(0,0,0,0))
        s.db=ImageDraw.Draw(s.body); s.dh=ImageDraw.Draw(s.hair)
        s.ds=ImageDraw.Draw(s.shirt); s.da=ImageDraw.Draw(s.acc)

def R(d,x0,y0,x1,y1,c): d.rectangle([x0,y0,x1,y1],fill=c)

# ============================ BODY PARTS ============================
# Vertical map (front/idle):  hair y4..   head y10..25   neck 25..27
#                             torso 27..39  hands 36..39  legs 39..45  shoes 45..46
def legs_front(c, frame, sit=False):
    d=c.db
    if sit:
        # knees together, feet forward
        R(d,18,38,22,44,PANTS); R(d,25,38,29,44,PANTS)
        R(d,18,38,18,44,PANTS_S); R(d,25,38,25,44,PANTS_H)
        R(d,17,44,23,45,SHOE); R(d,24,44,30,45,SHOE)
        R(d,17,44,23,44,SHOE_H); R(d,24,44,30,44,SHOE_H)
        return
    # walk lift pattern: left leg up on f1, right leg up on f3
    ll=[0,2,0,0][frame]; rl=[0,0,0,2][frame]
    R(d,18,39,22,45-ll,PANTS); R(d,18,39,18,45-ll,PANTS_S); R(d,21,39,22,45-ll,PANTS_H)
    R(d,25,39,29,45-rl,PANTS); R(d,29,39,29,45-rl,PANTS_S); R(d,25,39,26,45-rl,PANTS_H)
    R(d,17,46-ll,23,46-ll,SHOE); R(d,24,46-rl,30,46-rl,SHOE)

def torso_front(c, sit=False):
    d=c.ds; top=27; bot=39
    # shoulders a touch wider than torso
    R(d,15,27,32,28,S_MID)                 # shoulder line
    R(d,16,28,31,bot,S_MID)                # body
    R(d,16,28,31,28,S_HI)                  # top light
    R(d,16,bot,31,bot,S_LO)                # hem shadow
    R(d,16,28,16,bot,S_LO); R(d,31,28,31,bot,S_LO)   # side shadows
    R(d,17,29,17,bot-1,S_HI)               # left chest highlight
    # collar
    R(d,21,27,26,29,S_LO); R(d,22,27,25,28,S_LO2)

def arms_front(c, tone, frame, sit=False):
    d=c.ds; db=c.db; skin=tone[0]; skin_s=tone[1]
    sw=[0,-1,0,1][frame] if not sit else 0
    # sleeves
    R(d,13,28,15,34+sw,S_MID); R(d,13,28,13,34+sw,S_LO); R(d,15,28,15,34+sw,S_LO2)
    R(d,32,28,34,34-sw,S_MID); R(d,34,28,34,34-sw,S_LO); R(d,32,28,32,34-sw,S_LO2)
    # hands
    R(db,13,35+sw,15,37+sw,skin); R(db,13,35+sw,13,37+sw,skin_s)
    R(db,32,35-sw,34,37-sw,skin); R(db,34,35-sw,34,37-sw,skin_s)

def head_front(c, tone, eyes=True):
    d=c.db; skin,skin_s,skin_h=tone
    R(d,22,24,25,26,skin_s)                          # neck
    R(d,17,10,30,25,skin)                            # face block
    # rounded corners
    for (x,y) in [(17,10),(30,10),(17,25),(30,25)]: d.point((x,y),fill=(0,0,0,0))
    R(d,18,10,29,11,skin_h)                          # forehead light
    R(d,17,10,17,24,skin_s); R(d,30,10,30,24,skin_s) # cheek shadow sides
    R(d,18,24,29,25,skin_s)                          # jaw shadow
    R(d,16,16,16,20,skin); R(d,31,16,31,20,skin)     # ears
    R(d,16,16,16,16,skin_s); R(d,31,16,31,16,skin_s)
    if eyes:
        R(d,19,15,21,16,WHITE); d.point((20,16),fill=PUP); d.point((20,15),fill=(180,196,214,255))
        R(d,26,15,28,16,WHITE); d.point((27,16),fill=PUP); d.point((27,15),fill=(180,196,214,255))
        R(d,19,13,21,13,BROW); R(d,26,13,28,13,BROW)  # brows
        R(d,23,17,24,19,skin_s)                        # nose
        R(d,22,21,25,21,MOUTH)                         # mouth
        d.point((19,19),fill=sh(skin_s,1.05)); d.point((28,19),fill=sh(skin_s,1.05))  # cheeks

def head_back(c, tone):
    d=c.db; skin,skin_s,_=tone
    R(d,22,24,25,26,skin_s)
    R(d,17,11,30,25,skin)                            # back of head (mostly hair)
    for (x,y) in [(17,11),(30,11)]: d.point((x,y),fill=(0,0,0,0))
    R(d,16,16,16,20,skin); R(d,31,16,31,20,skin)     # ears

def head_side(c, tone):
    d=c.db; skin,skin_s,skin_h=tone
    R(d,22,24,25,26,skin_s)
    R(d,17,10,30,25,skin)
    for (x,y) in [(17,10),(30,10),(17,25),(30,25)]: d.point((x,y),fill=(0,0,0,0))
    R(d,18,10,29,11,skin_h)
    R(d,16,18,16,20,skin)                            # nose hint (facing left)
    d.point((19,16),fill=PUP); R(d,18,16,19,16,WHITE); d.point((19,16),fill=PUP)
    R(d,18,13,20,13,BROW)
    R(d,18,21,21,21,MOUTH)
    R(d,29,16,30,21,skin_s)                          # back jaw shadow
    R(d,30,16,30,20,skin)                            # ear (far side toward back)

# ----------------------------- HAIR -----------------------------
def _crown(d):  # the common skull cap used by several styles
    R(d,17,7,30,12,H_MID); R(d,16,9,31,13,H_MID)
    R(d,18,6,29,8,H_HI); R(d,19,6,28,6,H_HI)
    R(d,16,12,31,13,H_LO)

def hair_front(c, style):
    d=c.dh
    if style=="spiky":
        for x in range(16,31,3):
            d.polygon([(x,11),(x+1,3),(x+3,11)],fill=H_MID)
            d.line([(x+1,4),(x+1,9)],fill=H_HI)
        R(d,16,10,31,12,H_MID); R(d,16,12,31,13,H_LO)
        return
    if style=="curly":
        for cx0,cy0 in [(15,5),(20,3),(26,3),(31,5),(16,9),(30,9)]:
            d.ellipse([cx0-3,cy0-3,cx0+3,cy0+3],fill=H_MID)
        R(d,16,8,31,13,H_MID)
        for cx0,cy0 in [(18,5),(24,3),(29,5)]: d.ellipse([cx0-2,cy0-2,cx0+2,cy0+2],fill=H_HI)
        R(d,16,12,31,13,H_LO)
        return
    _crown(d)
    R(d,16,11,17,15,H_MID); R(d,30,11,31,15,H_MID)   # sideburns
    R(d,16,14,17,15,H_LO);  R(d,30,14,31,15,H_LO)
    if style=="long":
        R(d,15,11,17,30,H_MID); R(d,30,11,32,30,H_MID)
        R(d,15,11,15,30,H_LO);  R(d,32,11,32,30,H_LO)
        R(d,15,29,17,30,H_LO);  R(d,30,29,32,30,H_LO)
    if style=="bun":
        d.ellipse([20,1,27,8,],fill=H_MID); d.ellipse([21,2,25,5],fill=H_HI)

def hair_back(c, style):
    d=c.dh
    if style=="spiky":
        for x in range(16,31,3):
            d.polygon([(x,12),(x+1,3),(x+3,12)],fill=H_MID); d.line([(x+1,4),(x+1,10)],fill=H_HI)
        R(d,16,10,31,24,H_MID); R(d,16,23,31,24,H_LO)
        return
    if style=="curly":
        for cx0,cy0 in [(15,5),(20,3),(26,3),(31,5),(16,9),(30,9)]: d.ellipse([cx0-3,cy0-3,cx0+3,cy0+3],fill=H_MID)
        R(d,16,8,31,24,H_MID)
        for cx0,cy0 in [(18,18),(24,20),(29,18)]: d.ellipse([cx0-3,cy0-3,cx0+3,cy0+3],fill=H_MID)
        R(d,16,23,31,24,H_LO)
        return
    R(d,17,7,30,24,H_MID); R(d,16,9,31,24,H_MID)
    R(d,18,6,29,8,H_HI); R(d,19,6,28,6,H_HI)
    R(d,16,23,31,24,H_LO); R(d,16,9,16,23,H_LO); R(d,31,9,31,23,H_LO)
    R(d,23,9,23,23,H_LO2)                              # centre part shadow
    if style=="long":
        R(d,15,9,17,32,H_MID); R(d,30,9,32,32,H_MID)
        R(d,15,9,15,32,H_LO);  R(d,32,9,32,32,H_LO); R(d,15,31,32,32,H_LO)
    if style=="bun":
        d.ellipse([20,2,27,9],fill=H_MID); d.ellipse([21,3,25,6],fill=H_HI)

def hair_side(c, style):
    d=c.dh
    if style=="spiky":
        for x in range(17,31,3): d.polygon([(x,11),(x+1,4),(x+3,11)],fill=H_MID)
        R(d,17,10,30,13,H_MID); R(d,26,12,30,18,H_MID); R(d,17,12,30,13,H_LO)
        return
    if style=="curly":
        for cx0,cy0 in [(18,5),(23,3),(28,4),(30,8)]: d.ellipse([cx0-3,cy0-3,cx0+3,cy0+3],fill=H_MID)
        R(d,17,7,30,14,H_MID); R(d,26,12,30,18,H_MID); R(d,17,13,30,14,H_LO)
        return
    R(d,17,7,30,12,H_MID); R(d,18,6,29,7,H_HI)
    R(d,26,8,30,16,H_MID)                              # back of head
    R(d,17,12,30,13,H_LO)
    if style=="long":
        R(d,27,12,30,30,H_MID); R(d,27,29,30,30,H_LO); R(d,30,12,30,30,H_LO)
    if style=="bun":
        d.ellipse([27,2,33,8],fill=H_MID); d.ellipse([28,3,31,6],fill=H_HI)

# --------------------------- ACCESSORIES ---------------------------
def acc_front(c, t):
    d=c.da
    if t=="glasses":
        d.rectangle([18,14,22,18],outline=GLASS_FR); d.rectangle([25,14,29,18],outline=GLASS_FR)
        d.line([22,15,25,15],fill=GLASS_FR)            # bridge
        R(d,19,15,21,17,LENS); R(d,26,15,28,17,LENS)
        d.point((20,15),fill=GLASS_HI); d.point((27,15),fill=GLASS_HI)
    elif t=="headphones":
        d.arc([15,3,32,16],180,360,fill=CUP,width=2)   # band
        R(d,16,5,18,6,CUP_HI)
        R(d,13,14,16,21,CUP); R(d,31,14,34,21,CUP)     # cups
        R(d,13,14,16,15,CUP_HI); R(d,31,14,34,15,CUP_HI)
        R(d,13,20,16,21,CUP_LO); R(d,31,20,34,21,CUP_LO)
    elif t=="cap":
        R(d,16,7,31,12,CAP); R(d,16,7,31,8,CAP_HI)     # crown
        R(d,16,11,31,12,CAP_SH)
        R(d,12,11,21,13,CAP_BRIM); R(d,12,12,21,13,sh(CAP_BRIM,0.85))  # brim (front-left tilt)
        d.point((23,8),fill=CAP_HI)                     # button

def acc_back(c, t):
    d=c.da
    if t=="headphones":
        d.arc([15,3,32,16],180,360,fill=CUP,width=2); R(d,16,5,18,6,CUP_HI)
        R(d,13,14,16,21,CUP); R(d,31,14,34,21,CUP)
        R(d,13,14,16,15,CUP_HI); R(d,31,14,34,15,CUP_HI)
    elif t=="cap":
        R(d,16,7,31,13,CAP); R(d,16,7,31,8,CAP_HI); R(d,16,12,31,13,CAP_SH)
        R(d,18,11,29,13,CAP_SH)                          # back strap band

def acc_side(c, t):
    d=c.da
    if t=="glasses":
        d.rectangle([16,14,21,18],outline=GLASS_FR); R(d,17,15,20,17,LENS)
        d.line([21,15,24,15],fill=GLASS_FR)
    elif t=="headphones":
        d.arc([17,3,31,15],200,340,fill=CUP,width=2)
        R(d,16,14,19,21,CUP); R(d,16,14,19,15,CUP_HI); R(d,16,20,19,21,CUP_LO)
    elif t=="cap":
        R(d,17,7,30,12,CAP); R(d,17,7,30,8,CAP_HI); R(d,17,11,30,12,CAP_SH)
        R(d,12,11,20,13,CAP_BRIM)

# ----------------------------- helpers -----------------------------
def bob(c, dy):
    if dy==0: return
    for nm in ("body","hair","shirt","acc"):
        img=getattr(c,nm); out=Image.new("RGBA",img.size,(0,0,0,0)); out.paste(img,(0,dy),img); setattr(c,nm,out)

def flip(c):
    for nm in ("body","hair","shirt","acc"):
        setattr(c,nm,getattr(c,nm).transpose(Image.FLIP_LEFT_RIGHT))

# --------------------------- cell dispatcher ---------------------------
def build_cell(kind, dirn, frame, style, tone, acc):
    c=Cell(); skin=tone[0]
    if kind=="walk":
        if dirn=="down":
            legs_front(c,frame); torso_front(c); arms_front(c,tone,frame); head_front(c,tone)
            hair_front(c,style); acc_front(c,acc)
        elif dirn=="up":
            legs_front(c,frame); torso_front(c); arms_front(c,tone,frame); head_back(c,tone)
            hair_back(c,style); acc_back(c,acc)
        else:  # left (mirror -> right)
            legs_front(c,frame); torso_front(c); arms_front(c,tone,frame); head_side(c,tone)
            hair_side(c,style); acc_side(c,acc)
        if frame in (1,3): bob(c,-2)
        if dirn=="right": flip(c)
    else:  # sit — frame 0/1 typing animation
        legs_front(c,0,sit=True); torso_front(c,sit=True)
        f=frame
        if dirn=="up":
            # back view: forearms reach forward to a keyboard; hands clack out of phase
            la=36+(0 if f==0 else 3); ra=36+(3 if f==0 else 0)
            R(c.ds,13,28,15,la-1,S_MID); R(c.ds,13,28,13,la-1,S_LO)
            R(c.ds,32,28,34,ra-1,S_MID); R(c.ds,34,28,34,ra-1,S_LO)
            R(c.db,13,la,15,la+1,skin); R(c.db,32,ra,34,ra+1,skin)
            head_back(c,tone); hair_back(c,style); acc_back(c,acc)
        elif dirn=="down":
            # front view: forearms angle inward to a keyboard in the lap; small bob
            lh=37+(0 if f==0 else 2); rh=37+(2 if f==0 else 0)
            R(c.ds,14,28,16,33,S_MID); R(c.ds,31,28,33,33,S_MID)
            R(c.ds,16,32,20,34,S_MID); R(c.ds,27,32,31,34,S_MID)   # forearms inward
            R(c.db,18,lh,20,lh+1,skin); R(c.db,27,rh,29,rh+1,skin) # hands on keys
            head_front(c,tone); hair_front(c,style); acc_front(c,acc)
        else:  # profile (left; mirror -> right): near arm reaches forward, bobs
            ah=31+(0 if f==0 else 3)
            R(c.ds,15,28,20,30,S_MID); R(c.ds,18,30,20,ah,S_MID)
            R(c.db,18,ah,20,ah+1,skin)
            head_side(c,tone); hair_side(c,style); acc_side(c,acc)
            if dirn=="right": flip(c)
    return c

# row/col -> (kind,dir,frame)
def spec(row,col):
    if row==0: return ("walk","down",col)
    if row==1: return ("walk","up",col)
    if row==2: return ("walk","left",col)
    if row==3: return ("walk","right",col)
    if row==4: return ("sit","down" if col<2 else "up", col%2)
    if row==5: return ("sit","left" if col<2 else "right", col%2)

def blank(): return Image.new("RGBA",(COLS*CELL,ROWS*CELL),(0,0,0,0))
def paste(sheet,img,row,col): sheet.paste(img,(col*CELL,row*CELL),img)

def outline_from(union):
    px=union.load(); w,h=union.size; ring=Image.new("RGBA",(w,h),(0,0,0,0)); rp=ring.load()
    for y in range(h):
        for x in range(w):
            if px[x,y][3]==0:
                for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)):
                    nx,ny=x+dx,y+dy
                    if 0<=nx<w and 0<=ny<h and px[nx,ny][3]>30:
                        rp[x,y]=OUTLINE; break
    return ring

def build():
    # 1) shirt sheet (style/acc/tone independent)
    shirt=blank()
    for r in range(ROWS):
        for col in range(COLS):
            k,d,f=spec(r,col); c=build_cell(k,d,f,"short",SKIN_TONES[0],"none")
            paste(shirt,c.shirt,r,col)
    shirt.save(f"{OUT}/agent_shirt.png")

    # 2) body sheets per skin tone
    for si,tone in enumerate(SKIN_TONES):
        sheet=blank()
        for r in range(ROWS):
            for col in range(COLS):
                k,d,f=spec(r,col); c=build_cell(k,d,f,"short",tone,"none")
                paste(sheet,c.body,r,col)
        sheet.save(f"{OUT}/body_skin{si}.png")

    # 3) hair sheets per style (gray)
    for style in STYLES:
        sheet=blank()
        for r in range(ROWS):
            for col in range(COLS):
                k,d,f=spec(r,col); c=build_cell(k,d,f,style,SKIN_TONES[0],"none")
                paste(sheet,c.hair,r,col)
        sheet.save(f"{OUT}/hair_{style}.png")

    # 4) accessory sheets
    for acc in [a for a in ACCS if a!="none"]:
        sheet=blank()
        for r in range(ROWS):
            for col in range(COLS):
                k,d,f=spec(r,col); c=build_cell(k,d,f,"short",SKIN_TONES[0],acc)
                paste(sheet,c.acc,r,col)
        sheet.save(f"{OUT}/acc_{acc}.png")

    # 5) outline sheets per (style,acc): union of all layers
    for style in STYLES:
        for acc in ACCS:
            sheet=blank()
            for r in range(ROWS):
                for col in range(COLS):
                    k,d,f=spec(r,col); c=build_cell(k,d,f,style,SKIN_TONES[0],acc)
                    union=Image.new("RGBA",(CELL,CELL),(0,0,0,0))
                    for lyr in (c.shirt,c.body,c.hair,c.acc):
                        union=Image.alpha_composite(union,lyr)
                    paste(sheet,outline_from(union),r,col)
            sheet.save(f"{OUT}/outline_{style}_{acc}.png")

    anims={
        "walk_down":{"row":0,"frames":[0,1,2,3],"fps":8},
        "walk_up":{"row":1,"frames":[0,1,2,3],"fps":8},
        "walk_left":{"row":2,"frames":[0,1,2,3],"fps":8},
        "walk_right":{"row":3,"frames":[0,1,2,3],"fps":8},
        "idle_down":{"row":0,"frames":[0],"fps":1},
        "idle_up":{"row":1,"frames":[0],"fps":1},
        "idle_left":{"row":2,"frames":[0],"fps":1},
        "idle_right":{"row":3,"frames":[0],"fps":1},
        "sit_down":{"row":4,"frames":[0,1],"fps":3,"cols":[0,1]},
        "sit_up":{"row":4,"frames":[0,1],"fps":3,"cols":[2,3]},
        "sit_left":{"row":5,"frames":[0,1],"fps":3,"cols":[0,1]},
        "sit_right":{"row":5,"frames":[0,1],"fps":3,"cols":[2,3]},
    }
    atlas={
        "cell":CELL,"cols":COLS,"rows":ROWS,"anchor":[24,32],
        "skinCount":len(SKIN_TONES),
        "hairStyles":STYLES,
        "hairColors":["#%02x%02x%02x"%c for c in HAIR_COLORS],
        "accessories":ACCS,
        "layers":{
            "body":"body_skin{skin}.png",
            "hair":"hair_{style}.png",
            "shirt":"agent_shirt.png",
            "acc":"acc_{acc}.png",
            "outline":"outline_{style}_{acc}.png",
        },
        "anims":anims,
    }
    json.dump(atlas,open(f"{OUT}/agent.json","w"),indent=2)
    return atlas

def contact():
    def tint(gray_img, color):
        out=Image.new("RGBA",gray_img.size,(0,0,0,0)); gp=gray_img.load(); op=out.load()
        for y in range(gray_img.size[1]):
            for x in range(gray_img.size[0]):
                r,g,b,a=gp[x,y]
                if a: op[x,y]=(r*color[0]//255,g*color[1]//255,b*color[2]//255,a)
        return out
    shirt=Image.open(f"{OUT}/agent_shirt.png").convert("RGBA")
    bodies=[Image.open(f"{OUT}/body_skin{i}.png").convert("RGBA") for i in range(len(SKIN_TONES))]
    hairs={s:Image.open(f"{OUT}/hair_{s}.png").convert("RGBA") for s in STYLES}
    accs={a:Image.open(f"{OUT}/acc_{a}.png").convert("RGBA") for a in ACCS if a!="none"}
    outs={}
    for s in STYLES:
        for a in ACCS: outs[(s,a)]=Image.open(f"{OUT}/outline_{s}_{a}.png").convert("RGBA")
    STATE={'idle':(103,112,176),'thinking':(212,161,58),'output':(74,181,116),'tool':(90,143,212),'error':(208,88,88),'permission':(240,160,64)}
    def compose(skin,hairc,style,acc,state):
        base=Image.new("RGBA",shirt.size,(0,0,0,0))
        base=Image.alpha_composite(base, outs[(style,acc)])
        base=Image.alpha_composite(base, tint(shirt,STATE[state]))
        base=Image.alpha_composite(base, bodies[skin])
        base=Image.alpha_composite(base, tint(hairs[style],HAIR_COLORS[hairc]))
        if acc!="none": base=Image.alpha_composite(base, accs[acc])
        return base
    people=[
        (0,0,"short","none","idle"),(1,3,"short","headphones","tool"),
        (2,2,"bun","glasses","thinking"),(3,4,"long","none","output"),
        (1,5,"spiky","glasses","error"),(0,6,"bun","cap","permission"),
        (2,1,"curly","headphones","tool"),(4,7,"short","cap","idle"),
        (3,8,"curly","none","output"),(2,5,"long","glasses","thinking"),
    ]
    scale=6; pad=6
    W=(COLS*CELL*scale)+ (len(people)*(CELL*scale+pad)) + 40
    H=ROWS*CELL*scale+40
    cv=Image.new("RGBA",(W,H),(28,24,54,255))
    full=compose(*people[1])
    cv.alpha_composite(full.resize((COLS*CELL*scale,ROWS*CELL*scale),Image.NEAREST),(10,20))
    x=COLS*CELL*scale+30
    for p in people:
        comp=compose(*p).crop((0,0,CELL,CELL))  # walk_down f0
        cv.alpha_composite(comp.resize((CELL*scale,CELL*scale),Image.NEAREST),(x,H//2-CELL*scale//2))
        x+=CELL*scale+pad
    cv.convert("RGB").save(f"{PREV}/chars2_contact.png")
    print("chars2_contact ->",cv.size)

if __name__=="__main__":
    build(); contact()
    print("OK v3 layered chars (48px)")
