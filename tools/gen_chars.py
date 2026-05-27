#!/usr/bin/env python3
"""
Claude HQ — LAYERED character generator (v2).

Outputs separable layers so each agent is a distinct, polished person composed
at runtime:
  body_skin{0..3}.png   skin head+face+hands, pants, shoes  (fixed colors)
  hair_{short,long,bun}.png   grayscale hair shape          (tinted to hair color)
  agent_shirt.png       grayscale shirt+sleeves             (tinted to STATE color)
  acc_{glasses,headphones}.png  accessory                   (fixed colors)
  outline_{style}_{acc}.png   dark 1px shape outline         (per silhouette)
  agent.json            atlas: cell/anchor/anims + layer templates + variety dims

Grid: 4 cols x 6 rows of 32x32.
  row0 walk_down 0-3 | row1 walk_up 0-3 | row2 walk_left 0-3 | row3 walk_right 0-3
  row4 sit_down(0,1) sit_up(2,3) | row5 sit_left(0,1) sit_right(2,3)
Idle = walk frame 0 (atlas alias).
"""
import os, json
from PIL import Image, ImageDraw

CELL=32; COLS=4; ROWS=6
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT=os.path.join(ROOT,"src","assets","characters")
PREV=os.path.join(ROOT,"tools","_preview")
os.makedirs(OUT,exist_ok=True); os.makedirs(PREV,exist_ok=True)

def sh(c,f): return tuple(max(0,min(255,int(v*f))) for v in c[:3])

# fixed colors
PANTS=(58,50,104); PANTS_S=(40,34,78); PANTS_H=(78,68,128); SHOE=(28,26,36)
WHITE=(250,250,252,255); PUP=(40,32,52,255); BROW=(78,62,70,255)
OUTLINE=(34,28,46,255)
CUP=(58,62,84,255); CUP_HI=(96,100,128,255); CUP_LO=(40,43,60,255)
GLASS_FR=(40,40,54,255); LENS=(150,200,228,255)

SKIN_TONES=[
 ((247,206,160),(214,165,118),(255,226,190)),
 ((233,178,128),(196,140,96),(246,200,156)),
 ((198,140,96),(160,104,66),(216,164,120)),
 ((150,100,66),(112,72,44),(178,126,88)),
]
HAIR_COLORS=[(45,36,56),(120,68,46),(212,160,96),(86,160,192),(192,90,144),(74,74,86),(208,208,214)]
STYLES=["short","long","bun"]
ACCS=["none","glasses","headphones"]

# grayscale ink for tintable layers (bright so multiply keeps vivid color)
S_HI=(255,255,255,255); S_MID=(224,224,224,255); S_LO=(176,176,176,255)
H_HI=(255,255,255,255); H_MID=(212,212,212,255); H_LO=(150,150,150,255)

class Cell:
    def __init__(s):
        s.body =Image.new("RGBA",(CELL,CELL),(0,0,0,0))
        s.hair =Image.new("RGBA",(CELL,CELL),(0,0,0,0))
        s.shirt=Image.new("RGBA",(CELL,CELL),(0,0,0,0))
        s.acc  =Image.new("RGBA",(CELL,CELL),(0,0,0,0))
        s.db=ImageDraw.Draw(s.body); s.dh=ImageDraw.Draw(s.hair)
        s.ds=ImageDraw.Draw(s.shirt); s.da=ImageDraw.Draw(s.acc)

# ---------- shared parts (operate on a Cell) ----------
def legs_front(c, frame, sit=False):
    if sit:
        c.db.rectangle([12,25,19,28],fill=PANTS); c.db.rectangle([12,25,19,25],fill=PANTS_H)
        c.db.rectangle([12,29,14,29],fill=SHOE); c.db.rectangle([17,29,19,29],fill=SHOE); return
    ll=[0,1,0,0][frame]; rl=[0,0,0,1][frame]
    c.db.rectangle([12,24,14,28-ll],fill=PANTS); c.db.rectangle([12,24,12,28-ll],fill=PANTS_S); c.db.rectangle([13,24,13,28-ll],fill=PANTS_H)
    c.db.rectangle([17,24,19,28-rl],fill=PANTS); c.db.rectangle([19,24,19,28-rl],fill=PANTS_S); c.db.rectangle([18,24,18,28-rl],fill=PANTS_H)
    c.db.rectangle([12,29-ll,14,29-ll],fill=SHOE); c.db.rectangle([17,29-rl,19,29-rl],fill=SHOE)

def torso_front(c, sit=False):
    bot=24
    c.ds.rectangle([11,16,20,bot],fill=S_MID)
    c.ds.rectangle([11,16,20,16],fill=S_HI); c.ds.rectangle([11,bot,20,bot],fill=S_LO)
    c.ds.rectangle([11,16,11,bot],fill=S_LO); c.ds.rectangle([20,16,20,bot],fill=S_LO)
    c.ds.rectangle([15,17,16,bot-1],fill=S_HI)

def arms_front(c, tone, frame, sit=False):
    skin=tone[0]; sw=[0,-1,0,1][frame] if not sit else 0
    c.ds.rectangle([9,17,10,22+sw],fill=S_MID); c.ds.rectangle([9,17,9,22+sw],fill=S_LO)
    c.ds.rectangle([21,17,22,22-sw],fill=S_MID); c.ds.rectangle([22,17,22,22-sw],fill=S_LO)
    c.db.rectangle([9,23+sw,10,24+sw],fill=skin); c.db.rectangle([21,23-sw,22,24-sw],fill=skin)

def head_front(c, tone, eyes=True):
    skin,skin_s,skin_h=tone
    c.db.rectangle([14,15,17,16],fill=skin_s)            # neck
    c.db.rectangle([12,9,19,16],fill=skin)
    c.db.rectangle([12,9,19,9],fill=skin_h)
    c.db.rectangle([12,16,19,16],fill=skin_s)
    c.db.rectangle([12,13,12,15],fill=skin_s); c.db.rectangle([19,13,19,15],fill=skin_s)
    if eyes:
        c.db.rectangle([13,12,14,13],fill=WHITE); c.body.putpixel((14,13),PUP)
        c.db.rectangle([17,12,18,13],fill=WHITE); c.body.putpixel((17,13),PUP)
        c.db.line([13,11,14,11],fill=BROW); c.db.line([17,11,18,11],fill=BROW)
        c.db.line([15,15,16,15],fill=skin_s)

def head_back(c, tone):
    skin,skin_s,_=tone
    c.db.rectangle([14,15,17,16],fill=skin_s)
    c.db.rectangle([12,10,19,16],fill=skin)   # mostly covered by hair

def head_side(c, tone, faceleft=True):
    skin,skin_s,skin_h=tone
    c.db.rectangle([14,15,17,16],fill=skin_s)
    c.db.rectangle([12,9,19,16],fill=skin)
    c.db.rectangle([12,9,19,9],fill=skin_h)
    # face on left side (x12..16)
    c.body.putpixel((13,13),PUP)
    c.db.rectangle([11,12,11,14],fill=skin)   # nose hint
    c.db.line([13,11,14,11],fill=BROW)
    c.db.rectangle([12,16,19,16],fill=skin_s)

def hair_front(c, style):
    c.dh.rectangle([11,5,20,8],fill=H_MID); c.dh.rectangle([10,6,21,9],fill=H_MID)
    c.dh.rectangle([12,5,18,6],fill=H_HI)
    c.dh.rectangle([10,9,11,11],fill=H_MID); c.dh.rectangle([20,9,21,11],fill=H_MID)
    c.dh.rectangle([10,8,21,9],fill=H_LO)
    if style=="long":
        c.dh.rectangle([10,9,11,18],fill=H_MID); c.dh.rectangle([20,9,21,18],fill=H_MID)
        c.dh.rectangle([10,17,11,18],fill=H_LO); c.dh.rectangle([20,17,21,18],fill=H_LO)
    if style=="bun":
        c.dh.ellipse([13,1,18,6],fill=H_MID); c.dh.ellipse([14,1,17,4],fill=H_HI)

def hair_back(c, style):
    c.dh.rectangle([11,5,20,16],fill=H_MID); c.dh.rectangle([11,5,20,6],fill=H_HI)
    c.dh.rectangle([10,7,21,15],fill=H_MID)
    c.dh.rectangle([11,15,20,16],fill=H_LO)
    c.dh.rectangle([10,7,10,15],fill=H_LO); c.dh.rectangle([21,7,21,15],fill=H_LO)
    if style=="long":
        c.dh.rectangle([10,7,11,20],fill=H_MID); c.dh.rectangle([20,7,21,20],fill=H_MID)
        c.dh.rectangle([10,19,11,20],fill=H_LO); c.dh.rectangle([20,19,21,20],fill=H_LO)
    if style=="bun":
        c.dh.ellipse([13,2,18,7],fill=H_MID); c.dh.ellipse([14,2,17,5],fill=H_HI)

def hair_side(c, style):
    c.dh.rectangle([12,5,19,8],fill=H_MID); c.dh.rectangle([12,5,19,6],fill=H_HI)
    c.dh.rectangle([16,7,19,11],fill=H_MID)   # back of head hair
    c.dh.rectangle([12,8,19,8],fill=H_LO)
    if style=="long":
        c.dh.rectangle([17,8,19,18],fill=H_MID); c.dh.rectangle([17,17,19,18],fill=H_LO)
    if style=="bun":
        c.dh.ellipse([17,2,22,7],fill=H_MID)

def acc_front(c, t):
    if t=="glasses":
        c.da.rectangle([12,11,15,14],outline=GLASS_FR); c.da.rectangle([16,11,19,14],outline=GLASS_FR)
        c.da.line([15,12,16,12],fill=GLASS_FR)
        c.acc.putpixel((13,12),LENS); c.acc.putpixel((18,12),LENS)
    elif t=="headphones":
        c.da.line([12,4,19,4],fill=CUP); c.acc.putpixel((11,5),CUP); c.acc.putpixel((20,5),CUP)
        c.da.line([13,4,18,4],fill=CUP_HI)
        c.da.line([10,6,10,9],fill=CUP); c.da.line([21,6,21,9],fill=CUP)
        c.da.rectangle([8,9,10,13],fill=CUP); c.da.rectangle([21,9,23,13],fill=CUP)
        c.acc.putpixel((9,10),CUP_HI); c.acc.putpixel((22,10),CUP_HI)
        c.acc.putpixel((9,12),CUP_LO); c.acc.putpixel((22,12),CUP_LO)

def acc_back(c, t):
    if t=="headphones":
        c.da.line([12,5,19,5],fill=CUP); c.da.line([13,5,18,5],fill=CUP_HI)
        c.da.rectangle([8,9,10,13],fill=CUP); c.da.rectangle([21,9,23,13],fill=CUP)
        c.acc.putpixel((9,10),CUP_HI); c.acc.putpixel((22,10),CUP_HI)

def acc_side(c, t):
    if t=="glasses":
        c.da.rectangle([11,11,14,14],outline=GLASS_FR); c.acc.putpixel((12,12),LENS)
    elif t=="headphones":
        c.da.line([12,4,19,4],fill=CUP); c.da.line([10,5,10,9],fill=CUP)
        c.da.rectangle([8,9,10,13],fill=CUP); c.acc.putpixel((9,10),CUP_HI)

def bob(c, dy):
    if dy==0: return
    for nm in ("body","hair","shirt","acc"):
        img=getattr(c,nm); out=Image.new("RGBA",img.size,(0,0,0,0)); out.paste(img,(0,dy),img); setattr(c,nm,out)

def flip(c):
    for nm in ("body","hair","shirt","acc"):
        setattr(c,nm,getattr(c,nm).transpose(Image.FLIP_LEFT_RIGHT))

# ---------- cell dispatcher ----------
def build_cell(kind, dirn, frame, style, tone, acc):
    c=Cell()
    if kind=="walk":
        if dirn=="down":
            legs_front(c,frame); torso_front(c); arms_front(c,tone,frame); head_front(c,tone)
            hair_front(c,style); acc_front(c,acc)
        elif dirn=="up":
            legs_front(c,frame); torso_front(c); arms_front(c,tone,frame); head_back(c,tone)
            hair_back(c,style); acc_back(c,acc)
        else:  # left (mirror for right)
            legs_front(c,frame); torso_front(c); arms_front(c,tone,frame); head_side(c,tone)
            hair_side(c,style); acc_side(c,acc)
        if frame in (1,3): bob(c,-1)
        if dirn=="right": flip(c)
    else:  # sit — frame 0/1 is the typing animation; hands alternate clearly
        legs_front(c,0,sit=True); torso_front(c,sit=True)
        skin=tone[0]; f=frame
        if dirn=="up":
            # back view (faces monitor): both forearms reach FORWARD onto the keyboard,
            # hands clack up/down out of phase -> reads as typing.
            la=23+(0 if f==0 else 2); ra=23+(2 if f==0 else 0)
            c.ds.rectangle([9,17,10,la-1],fill=S_MID); c.ds.rectangle([9,17,9,la-1],fill=S_LO)
            c.ds.rectangle([21,17,22,ra-1],fill=S_MID); c.ds.rectangle([22,17,22,ra-1],fill=S_LO)
            c.db.rectangle([9,la,10,la],fill=skin); c.db.rectangle([21,ra,22,ra],fill=skin)
            head_back(c,tone); hair_back(c,style); acc_back(c,acc)
        elif dirn=="down":
            # front view: forearms angle inward to a keyboard in front of the lap; bob
            lh=24+(0 if f==0 else 1); rh=24+(1 if f==0 else 0)
            c.ds.rectangle([10,17,11,21],fill=S_MID); c.ds.rectangle([20,17,21,21],fill=S_MID)
            c.ds.rectangle([11,21,13,22],fill=S_MID); c.ds.rectangle([18,21,20,22],fill=S_MID)
            c.db.rectangle([12,lh,13,lh],fill=skin); c.db.rectangle([18,rh,19,rh],fill=skin)
            head_front(c,tone); hair_front(c,style); acc_front(c,acc)
        else:  # profile (left; mirror for right): near arm reaches forward and bobs
            ah=19+(0 if f==0 else 2)
            c.ds.rectangle([10,17,13,18],fill=S_MID); c.ds.rectangle([12,18,13,ah-1],fill=S_MID)
            c.db.rectangle([12,ah,13,ah],fill=skin)
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

    # 2) body sheets per skin tone (style/acc independent)
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
    for acc in ("glasses","headphones"):
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
        "cell":CELL,"cols":COLS,"rows":ROWS,"anchor":[16,21],
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
    # compose a few distinct agents across states for QA
    def tint(gray_img, color):
        out=Image.new("RGBA",gray_img.size,(0,0,0,0)); gp=gray_img.load(); op=out.load()
        for y in range(gray_img.size[1]):
            for x in range(gray_img.size[0]):
                r,g,b,a=gp[x,y]
                if a: op[x,y]=(r*color[0]//255,g*color[1]//255,b*color[2]//255,a)
        return out
    shirt=Image.open(f"{OUT}/agent_shirt.png").convert("RGBA")
    bodies=[Image.open(f"{OUT}/body_skin{i}.png").convert("RGBA") for i in range(4)]
    hairs={s:Image.open(f"{OUT}/hair_{s}.png").convert("RGBA") for s in STYLES}
    accs={a:Image.open(f"{OUT}/acc_{a}.png").convert("RGBA") for a in ("glasses","headphones")}
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
        (1,5,"short","glasses","error"),(0,6,"bun","none","permission"),
        (2,1,"long","headphones","tool"),(3,0,"short","none","idle"),
    ]
    scale=7; pad=6
    cols_show=[0,1,4,5]  # walk_down0, walk_down1, sit_down0, sit_up... show a few cells
    # show full sheet for first person + lineup of others' walk_down0
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
    print("OK v2 layered chars")
