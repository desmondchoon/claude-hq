#!/usr/bin/env python3
"""
Claude HQ — static office preview (v2, layered characters).

Renders a still of the office exactly how renderer.js composes it: tiled
floor/walls, rugs, glass + solid room walls, furniture with cast shadows,
layered varied characters, and status-icon chips + nameplates. Handy for a
quick visual check without launching the app. (For a LIVE animated preview,
open src/preview.html in a browser.)

Outputs tools/_preview/scene.png (+ scene_2x.png).
"""
import os, json
from PIL import Image, ImageDraw, ImageChops, ImageFont

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CH=os.path.join(ROOT,"src","assets","characters")
OF=os.path.join(ROOT,"src","assets","office")
PREV=os.path.join(ROOT,"tools","_preview"); os.makedirs(PREV,exist_ok=True)
A=json.load(open(f"{CH}/agent.json")); O=json.load(open(f"{OF}/office.json"))
FW,FH=800,500

bodies=[Image.open(f"{CH}/{A['layers']['body'].replace('{skin}',str(s))}").convert("RGBA") for s in range(A['skinCount'])]
hairs={st:Image.open(f"{CH}/{A['layers']['hair'].replace('{style}',st)}").convert("RGBA") for st in A['hairStyles']}
shirt=Image.open(f"{CH}/{A['layers']['shirt']}").convert("RGBA")
accs={a:Image.open(f"{CH}/{A['layers']['acc'].replace('{acc}',a)}").convert("RGBA") for a in A['accessories'] if a!='none'}
outs={f"{st}|{a}":Image.open(f"{CH}/{A['layers']['outline'].replace('{style}',st).replace('{acc}',a)}").convert("RGBA")
      for st in A['hairStyles'] for a in A['accessories']}
tiles={n:Image.open(f"{OF}/{f}").convert("RGBA") for n,f in O['tiles'].items()}
pieces={n:Image.open(f"{OF}/{n}.png").convert("RGBA") for n in O['anchors']}

def hx(h): h=h.lstrip('#'); return tuple(int(h[i:i+2],16) for i in (0,2,4))
STATE={'idle':('#6770b0','#454a82','idle'),'thinking':('#d4a13a','#9b7423','thinking'),
 'typing':('#4ab574','#2e7a4e','output'),'tool':('#5a8fd4','#3b6da8','tool'),
 'done':('#7fc864','#558a3f','done'),'error':('#d05858','#8a3838','error'),
 'permission':('#f0a040','#a06820','awaiting you'),'asking':('#5fbac0','#3c7c80','asking')}

def tint(gray,color):
    solid=Image.new("RGB",gray.size,color)
    rgb=ImageChops.multiply(gray.convert("RGB"),solid)
    out=rgb.convert("RGBA"); out.putalpha(gray.split()[3]); return out

def pick_ap(h):
    h=abs(int(h)); skin=h%A['skinCount']; style=A['hairStyles'][(h//A['skinCount'])%len(A['hairStyles'])]
    col=hx(A['hairColors'][(h//(A['skinCount']*len(A['hairStyles'])))%len(A['hairColors'])])
    roll=(h//97)%5; acc='glasses' if roll==3 else 'headphones' if roll==4 else 'none'
    return skin,style,col,acc

def cell(name,f):
    an=A['anims'].get(name,A['anims']['idle_down']); cols=an.get('cols')
    c=cols[f%len(cols)] if cols else an['frames'][f%len(an['frames'])]
    return c*A['cell'],an['row']*A['cell']

def draw_agent(canvas,x,y,anim,f,h,state):
    skin,style,col,acc=pick_ap(h); sx,sy=cell(anim,f); ax,ay=A['anchor']
    dx,dy=int(round(x-ax)),int(round(y-ay)); cl=A['cell']
    def blit(img): canvas.alpha_composite(img.crop((sx,sy,sx+cl,sy+cl)),(dx,dy))
    sh=Image.new("RGBA",(14,4),(0,0,0,70)); canvas.alpha_composite(sh,(int(x)-7,int(y)+7))
    blit(outs[f"{style}|{acc}"]); blit(tint(shirt,hx(STATE[state][0]))); blit(bodies[skin])
    blit(tint(hairs[style],col))
    if acc!='none': blit(accs[acc])

def tile_region(c,img,x,y,w,h):
    for ty in range(y,y+h,img.height):
        for tx in range(x,x+w,img.width): c.alpha_composite(img,(tx,ty))

def rug(c,x,y,w,h):
    e=O['rugEdge']; ImageDraw.Draw(c).rectangle([x,y,x+w,y+h],fill=(e[0],e[1],e[2],255))
    fill=Image.new("RGBA",(w-4,h-4),(0,0,0,0)); tile_region(fill,tiles['rug'],0,0,w-4,h-4); c.alpha_composite(fill,(x+2,y+2))

def pshadow(c,name,px,py):
    img=pieces[name]; a=O['anchors'][name]; cx=px-a[0]+img.width//2; by=py-a[1]+img.height-9
    s=Image.new("RGBA",(int(img.width*0.84),10),(0,0,0,0)); ImageDraw.Draw(s).ellipse([0,0,s.width-1,9],fill=(0,0,0,40))
    c.alpha_composite(s,(cx-s.width//2,by))

def piece(c,name,px,py):
    a=O['anchors'][name]; c.alpha_composite(pieces[name],(px-a[0],py-a[1]))

WALLS=[(612,150,180,8,'g','back'),(612,150,8,80,'g','back'),(612,278,8,62,'g','back'),
 (784,150,8,190,'g','back'),(612,332,180,8,'g','front'),
 (50,54,FW-270,6,'s','back'),(70,352,380,6,'s','back'),(444,352,6,128,'s','back')]
def wall(c,w):
    x,y,ww,hh,k,_=w; d=ImageDraw.Draw(c)
    if k=='g':
        pane=Image.new("RGBA",(ww,hh),(150,202,230,66)); c.alpha_composite(pane,(x,y))
        d.rectangle([x,y,x+ww-1,y+hh-1],outline=(138,166,188))
        if ww>hh:
            for xx in range(x+18,x+ww-2,18): d.line([xx,y,xx,y+hh-1],fill=(138,166,188))
        else:
            for yy in range(y+18,y+hh-2,18): d.line([x,yy,x+ww-1,yy],fill=(138,166,188))
    else:
        d.rectangle([x,y,x+ww,y+hh],fill=(74,70,88)); d.rectangle([x,y,x+ww,y+1],fill=(108,104,120))
def walls(c,layer):
    for w in WALLS:
        if w[5]==layer: wall(c,w)

def font(sz):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf","/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if os.path.exists(p): return ImageFont.truetype(p,sz)
    return ImageFont.load_default()

def chip(d,x,y,state,tool=None):
    p,s,lbl=STATE[state]; text='' if state=='idle' else (tool or lbl) if state=='tool' else lbl
    f=font(8); tw=int(d.textlength(text,font=f)) if text else 0
    iw,pad,gap=9,3,(3 if text else 0); w=pad+iw+gap+tw+pad; h=14; bx=x-w//2; by=y-22-h
    d.rounded_rectangle([bx,by,bx+w,by+h],radius=3,fill=(255,255,255),outline=hx(p),width=1)
    d.polygon([(x-2,by+h-1),(x+2,by+h-1),(x,by+h+3)],fill=(255,255,255))
    ix,iy=bx+pad+4,by+h//2; col=hx(s)
    if state=='thinking':
        for dx in (-3,-1,1,3): d.point((ix+dx,iy),fill=col)
    elif state=='tool':
        d.rectangle([ix,iy-3,ix,iy+3],fill=col); d.rectangle([ix-3,iy,ix+3,iy],fill=col)
    elif state=='typing': d.rectangle([ix-3,iy-1,ix+3,iy-1],fill=col); d.rectangle([ix-3,iy+1,ix+1,iy+1],fill=col)
    elif state=='done':
        for dx,dy in ((-3,0),(-2,1),(-1,2),(0,1),(1,0),(2,-1),(3,-2)): d.point((ix+dx,iy+dy),fill=col)
    elif state=='error': d.rectangle([ix,iy-3,ix,iy],fill=col); d.point((ix,iy+2),fill=col)
    elif state=='permission': d.rectangle([ix-2,iy-3,ix-1,iy+3],fill=col); d.rectangle([ix+1,iy-3,ix+2,iy+3],fill=col)
    else: d.text((ix-3,iy-5),'?' if state=='asking' else 'z',font=font(9),fill=col)
    if text: d.text((bx+pad+iw+gap,by+3),text,font=f,fill=col)

def nameplate(d,x,y,text):
    f=font(8); tw=int(d.textlength(text,font=f)); w=tw+6; bx=x-w//2
    d.rectangle([bx,y,bx+w,y+10],fill=(26,22,32)); d.text((bx+3,y+1),text,font=f,fill=(228,224,246))

def build():
    c=Image.new("RGBA",(FW,FH),(13,13,18,255))
    tile_region(c,tiles['wall'],0,0,FW,FH)
    fl=Image.new("RGBA",(FW-16,FH-16),(0,0,0,0)); tile_region(fl,tiles['floor'],0,0,FW-16,FH-16); c.alpha_composite(fl,(8,8))
    for r in [(50,60,FW-220,70),(100,180,460,60),(80,360,360,110)]: rug(c,*r)
    walls(c,'back')
    piece(c,'door',0,275)
    for n,x,y in [('counter',540,380),('table',700,245),('sofa',160,400),('sofa',350,400),
                  ('plant_big',60,160),('plant_big',590,150),('plant',470,360),('plant',60,470),
                  ('pingpong',470,415),('watercooler',36,150)]: pshadow(c,n,x,y); piece(c,n,x,y)
    # cubicles render behind agents; open desks render IN FRONT (desk_front)
    for n,x,y in [('cubicle',130,95),('cubicle',260,95),('cubicle',390,95),('cubicle',520,95)]:
        pshadow(c,n,x,y); piece(c,n,x,y)
    DESKS_FRONT=[(170,210),(320,210),(470,210)]
    AG=[(130,95,'sit_up',1,11,'thinking',None),(260,95,'sit_up',1,42,'tool',None),
        (390,95,'sit_up',0,7,'typing',None),(520,95,'sit_up',1,99,'done','opus-4.6'),
        (170,210,'sit_down',1,23,'idle',None),(320,210,'sit_down',0,64,'tool','sonnet-4.6'),(470,210,'sit_down',1,5,'thinking',None),
        (660,200,'sit_right',1,33,'tool',None),(740,200,'sit_left',1,71,'typing',None),
        (660,290,'sit_right',0,88,'asking',None),(740,290,'sit_left',1,14,'permission',None),
        (130,400,'sit_down',1,52,'idle',None),(320,400,'sit_down',1,9,'error',None),
        (80,275,'walk_right',1,40,'tool',None)]
    for a in sorted(AG,key=lambda r:r[1]): draw_agent(c,a[0],a[1],a[2],a[3],a[4],a[5])
    for x,y in DESKS_FRONT: pshadow(c,'desk_front',x,y); piece(c,'desk_front',x,y)
    walls(c,'front')
    d=ImageDraw.Draw(c)
    for a in AG:
        x,y=a[0],a[1]
        if a[2].startswith('sit'): chip(d,x,y,a[5],'Bash' if a[5]=='tool' else None)
        if a[6]: nameplate(d,x,y+13,a[6])
    for t,x,y in [('CUBICLES',55,18),('OPEN DESKS',105,166),('MEETING',660,138),('LOUNGE',85,342),('KITCHEN',542,366)]:
        d.text((x,y),t,font=font(9),fill=(90,79,60))
    c.convert("RGB").save(f"{PREV}/scene.png")
    c.resize((FW*2,FH*2),Image.NEAREST).convert("RGB").save(f"{PREV}/scene_2x.png")
    print("scene ->",f"{PREV}/scene_2x.png")

if __name__=="__main__": build()
