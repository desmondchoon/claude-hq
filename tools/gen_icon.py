#!/usr/bin/env python3
"""
Claude HQ — app icon + menu-bar tray glyph generator.

Writes to src-tauri/icons/:
  icon.png (1024)  32x32.png  128x128.png  128x128@2x.png  icon.icns  icon.ico
  tray.rgba        raw 44x44 RGBA template glyph (loaded via Image::new in Rust)
  tray.png         preview of the template glyph
Also writes outputs/preview/icon_preview.png.
"""
import os
from PIL import Image, ImageDraw

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONS=os.path.join(ROOT,"src-tauri","icons")
PREV=os.path.join(ROOT,"tools","_preview")
os.makedirs(ICONS,exist_ok=True); os.makedirs(PREV,exist_ok=True)

def sh(c,f): return tuple(max(0,min(255,int(v*f))) for v in c[:3])

SKIN=(244,200,150); SKIN_S=(206,158,112); SKIN_H=(255,224,186)
HAIR=(60,48,74); HAIR_HI=(96,80,118)
SHIRT=(74,170,150); SHIRT_S=(48,120,108); SHIRT_HI=(120,206,186)
PANTS=(60,52,104); PANTS_S=(42,36,80)
SHOE=(30,28,38); OUTLINE=(34,28,46,255)
CUP=(54,58,80); CUP_HI=(110,116,150)

def outline_layer(im, color=OUTLINE):
    """Add a 1px dark ring around opaque pixels of a TRANSPARENT-bg layer."""
    px=im.load(); W,H=im.size; ring=[]
    for y in range(H):
        for x in range(W):
            if px[x,y][3]<40:
                for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)):
                    nx,ny=x+dx,y+dy
                    if 0<=nx<W and 0<=ny<H and px[nx,ny][3]>140:
                        ring.append((x,y)); break
    for x,y in ring: px[x,y]=color

def app_icon(S=128):
    rad=int(S*0.22); u=S/128.0
    # 1) opaque gradient background
    bg=Image.new("RGBA",(S,S),(0,0,0,0)); bd=ImageDraw.Draw(bg)
    top=(246,240,226); bot=(150,192,214)
    for y in range(S):
        t=y/(S-1); col=tuple(int(top[i]*(1-t)+bot[i]*t) for i in range(3)); bd.line([(0,y),(S,y)],fill=col+(255,))
    # subtle floor band (office hint) via alpha composite (keeps gradient above)
    floor=Image.new("RGBA",(S,S),(0,0,0,0)); fd=ImageDraw.Draw(floor)
    fy=int(S*0.64); fd.rectangle([0,fy,S,S],fill=(92,148,180,95)); fd.line([0,fy,S,fy],fill=(255,255,255,70))
    bg.alpha_composite(floor)
    # soft shadow under the character
    sdw=Image.new("RGBA",(S,S),(0,0,0,0)); ImageDraw.Draw(sdw).ellipse([(64-22)*u,103*u,(64+22)*u,114*u],fill=(0,0,0,70))
    bg.alpha_composite(sdw)

    # 2) character on a transparent layer (so the outline forms), then composite
    ch=Image.new("RGBA",(S,S),(0,0,0,0)); d=ImageDraw.Draw(ch)
    def R(x0,y0,x1,y1,c): d.rectangle([x0*u,y0*u,x1*u-1,y1*u-1],fill=c)
    # legs
    R(54,92,61,108,PANTS); R(54,92,56,108,PANTS_S)
    R(67,92,74,108,PANTS); R(72,92,74,108,PANTS_S)
    R(53,108,62,112,SHOE); R(66,108,75,112,SHOE)
    # torso
    R(48,60,80,94,SHIRT); R(48,60,80,64,SHIRT_HI); R(48,90,80,94,SHIRT_S)
    R(48,60,52,94,SHIRT_S); R(76,60,80,94,SHIRT_S); R(62,62,66,90,SHIRT_HI)
    # arms + hands
    R(42,62,48,88,SHIRT); R(42,62,45,88,SHIRT_S)
    R(80,62,86,88,SHIRT); R(83,62,86,88,SHIRT_S)
    R(42,88,48,93,SKIN); R(80,88,86,93,SKIN)
    # neck + head
    R(58,55,70,60,SKIN_S)
    R(46,26,82,58,SKIN); R(46,26,82,30,SKIN_H); R(46,54,82,58,SKIN_S)
    R(46,40,49,54,SKIN_S); R(79,40,82,54,SKIN_S)
    # face
    R(54,40,60,46,(252,252,255)); R(56,42,60,46,(46,38,60))
    R(68,40,74,46,(252,252,255)); R(68,42,72,46,(46,38,60))
    R(53,36,60,38,HAIR); R(68,36,75,38,HAIR)
    R(58,50,70,52,SKIN_S); R(60,51,68,53,(196,120,110))
    # hair (short swept) + sideburns
    R(44,18,84,30,HAIR); R(48,14,80,20,HAIR); R(48,15,72,18,HAIR_HI)
    R(44,30,48,40,HAIR); R(80,30,84,40,HAIR); R(44,28,84,30,sh(HAIR,0.8))
    # headphones
    R(46,12,82,16,CUP); R(50,12,78,14,CUP_HI)
    R(40,30,48,46,CUP); R(80,30,88,46,CUP)
    R(41,32,46,34,CUP_HI); R(82,32,87,34,CUP_HI)
    outline_layer(ch)
    bg.alpha_composite(ch)

    # status bubble (signals "agent at work")
    d2=ImageDraw.Draw(bg)
    bx0,by0=int(84*u),int(18*u); bw,bh=int(30*u),int(17*u)
    d2.rounded_rectangle([bx0,by0,bx0+bw,by0+bh],radius=int(5*u),fill=(255,255,255,255),outline=(48,120,108,255),width=max(1,int(1.4*u)))
    d2.polygon([(bx0+int(6*u),by0+bh-1),(bx0+int(13*u),by0+bh-1),(bx0+int(7*u),by0+bh+int(6*u))],fill=(255,255,255,255))
    for i in range(3):
        dx=bx0+int((8+i*7)*u); cyy=by0+bh//2
        d2.ellipse([dx,cyy-int(1.8*u),dx+int(3.4*u),cyy+int(1.8*u)],fill=(48,120,108))

    # 3) round-corner mask + rim
    mask=Image.new("L",(S,S),0); ImageDraw.Draw(mask).rounded_rectangle([0,0,S-1,S-1],radius=rad,fill=255)
    out=Image.new("RGBA",(S,S),(0,0,0,0)); out.paste(bg,(0,0),mask)
    od=ImageDraw.Draw(out)
    od.rounded_rectangle([0,0,S-1,S-1],radius=rad,outline=(255,255,255,90),width=max(1,int(1*u)))
    od.rounded_rectangle([1,1,S-2,S-2],radius=rad-1,outline=(40,34,60,60),width=1)
    return out

def tray_glyph(S=44):
    """Monochrome template: a clean person bust (head over shoulders).
    Solid template silhouettes can't show internal detail, so we keep it to a
    universally-readable head + shoulders with a transparent neck gap."""
    im=Image.new("RGBA",(S,S),(0,0,0,0)); d=ImageDraw.Draw(im); K=(0,0,0,255); cx=S//2
    # shoulders / upper body (rounded top reads as a bust)
    d.rounded_rectangle([cx-15,32,cx+15,S-3],radius=10,fill=K)
    # head (circle), with a ~2px transparent gap above the shoulders = neck
    d.ellipse([cx-10,7,cx+10,29],fill=K)
    return im

def export():
    app=app_icon(128)
    big=app.resize((1024,1024),Image.NEAREST); big.save(f"{ICONS}/icon.png")
    for name,sz in [("32x32.png",32),("128x128.png",128),("128x128@2x.png",256)]:
        app.resize((sz,sz),Image.NEAREST).save(f"{ICONS}/{name}")
    msg=[]
    try: big.save(f"{ICONS}/icon.ico",sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]); msg.append("ico ok")
    except Exception as e: msg.append(f"ico FAIL {e}")
    try: big.save(f"{ICONS}/icon.icns"); msg.append("icns ok")
    except Exception as e: msg.append(f"icns FAIL {e}")
    tg=tray_glyph(44)
    open(f"{ICONS}/tray.rgba","wb").write(tg.tobytes()); tg.save(f"{ICONS}/tray.png")

    prev=Image.new("RGBA",(1040,520),(40,36,64,255)); pd=ImageDraw.Draw(prev)
    pd.text((40,16),"Claude HQ — app icon (1024/128/64/32/16)  +  menu-bar template",fill=(222,218,242))
    prev.alpha_composite(big.resize((256,256),Image.NEAREST),(40,52))
    for sz,x in [(128,320),(64,470),(32,556),(16,600)]:
        prev.alpha_composite(app.resize((sz,sz),Image.NEAREST),(x,52))
    pd.rectangle([320,330,520,450],fill=(236,236,239,255)); pd.text((328,334),"menu bar (light)",fill=(60,60,70))
    pd.rectangle([540,330,740,450],fill=(38,38,44,255));   pd.text((548,334),"menu bar (dark)",fill=(210,210,216))
    tgL=Image.new("RGBA",tg.size,(0,0,0,0)); tgL.paste((28,28,34,255),(0,0),tg)
    tgD=Image.new("RGBA",tg.size,(0,0,0,0)); tgD.paste((236,236,240,255),(0,0),tg)
    prev.alpha_composite(tgL.resize((44,44),Image.NEAREST),(398,366))
    prev.alpha_composite(tgD.resize((44,44),Image.NEAREST),(618,366))
    prev.alpha_composite(tgL.resize((22,22),Image.NEAREST),(470,377))
    prev.alpha_composite(tgD.resize((22,22),Image.NEAREST),(690,377))
    prev.convert("RGB").save(f"{PREV}/icon_preview.png")
    print("exported:", ", ".join(msg), "| tray.rgba", os.path.getsize(f'{ICONS}/tray.rgba'),"bytes")

if __name__=="__main__":
    export()
