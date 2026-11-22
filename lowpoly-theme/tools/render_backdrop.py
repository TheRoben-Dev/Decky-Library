"""Tiny PS1-style software renderer for the Lowpoly backdrop.
Low resolution, vertex positions snapped to whole pixels, flat/gouraud shading, depth fog,
15-bit colour with ordered dither. Output is upscaled by the browser with image-rendering: pixelated."""
import math, sys
import numpy as np
from PIL import Image

W, H = 384, 216
BG_TOP, BG_HOR, FLOOR = np.array([14, 15, 31]), np.array([9, 9, 20]), np.array([8, 8, 17])
FOG = np.array([9, 9, 19])
CAM = np.array([0.0, 1.6, 0.0]); PITCH = math.radians(-9); FOV = math.radians(58)
F = (H / 2) / math.tan(FOV / 2)
LIGHT = np.array([-0.45, 0.8, 0.55]); LIGHT /= np.linalg.norm(LIGHT)

def hexc(h): return np.array([int(h[i:i+2], 16) for i in (1, 3, 5)], float)

def rot(rx, ry, rz):
    rx, ry, rz = map(math.radians, (rx, ry, rz))
    X = np.array([[1,0,0],[0,math.cos(rx),-math.sin(rx)],[0,math.sin(rx),math.cos(rx)]])
    Y = np.array([[math.cos(ry),0,math.sin(ry)],[0,1,0],[-math.sin(ry),0,math.cos(ry)]])
    Z = np.array([[math.cos(rz),-math.sin(rz),0],[math.sin(rz),math.cos(rz),0],[0,0,1]])
    return Y @ X @ Z

def to_view(p):
    q = p - CAM
    c, s = math.cos(-PITCH), math.sin(-PITCH)
    return np.array([q[0], c*q[1] - s*q[2], s*q[1] + c*q[2]])

def project(v):  # view space -> pixel, snapped (PS1: no subpixel precision)
    z = -v[2]
    return np.array([round(W/2 + v[0]*F/z), round(H/2 - v[1]*F/z)]), z

def box(sx, sy, sz, col, off=(0, 0, 0), top=None):
    """Triangles of an axis-aligned box; col = colour or (colour_top_vertices, colour_bottom_vertices) for gouraud."""
    x, y, z = sx/2, sy/2, sz/2; o = np.array(off, float)
    P = [np.array(p, float) + o for p in [(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),(-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)]]
    quads = [(4,5,6,7),(1,0,3,2),(0,4,7,3),(5,1,2,6),(3,7,6,2),(0,1,5,4)]
    tris = []
    for a, b, c, d in quads:
        for t in ((a, b, c), (a, c, d)):
            if isinstance(col, tuple):
                cols = [col[0] if P[i][1] > o[1] else col[1] for i in t]
            else:
                cols = [col] * 3
            tris.append(([P[i] for i in t], cols))
    return tris

def torus(R, r, col, nu=12, nv=6):
    tris = []
    def pt(u, v):
        return np.array([(R + r*math.cos(v))*math.cos(u), r*math.sin(v), (R + r*math.cos(v))*math.sin(u)])
    for i in range(nu):
        for j in range(nv):
            u0, u1 = 2*math.pi*i/nu, 2*math.pi*(i+1)/nu
            v0, v1 = 2*math.pi*j/nv, 2*math.pi*(j+1)/nv
            a, b, c, d = pt(u0, v0), pt(u1, v0), pt(u1, v1), pt(u0, v1)
            tris += [([a, b, c], [col]*3), ([a, c, d], [col]*3)]
    return tris

def octa(s, col):
    v = [np.array(p, float)*s for p in [(1,0,0),(-1,0,0),(0,1.4,0),(0,-1.4,0),(0,0,1),(0,0,-1)]]
    f = [(2,4,0),(2,0,5),(2,5,1),(2,1,4),(3,0,4),(3,5,0),(3,1,5),(3,4,1)]
    return [([v[a], v[b], v[c]], [col]*3) for a, b, c in f]

def place(tris, pos, r):
    M = rot(*r); p = np.array(pos, float)
    return [([M @ q + p for q in t], c) for t, c in tris]

# ── Scene (original generic era toys) ───────────────────────────
scene = []
# floppy disk
fl = box(.9, .9, .07, hexc("#2C4BD1")) + box(.42, .3, .08, hexc("#B9BDCB"), (.08, .3, 0)) \
   + box(.62, .36, .075, hexc("#E6E1D2"), (0, -.2, .002)) + box(.12, .12, .08, hexc("#1A2A80"), (-.36, .36, 0))
scene += place(fl, (-2.95, .42, -4.2), (-18, 38, 12))
# cartridge with a sunset-gradient label
ca = box(.8, 1.0, .18, hexc("#6D6D86")) + box(.64, .52, .19, (hexc("#F59A35"), hexc("#7E3BD0")), (0, .12, 0)) \
   + box(.5, .06, .19, hexc("#55556B"), (0, -.3, 0)) + box(.5, .06, .19, hexc("#55556B"), (0, -.4, 0))
scene += place(ca, (-3.7, 1.35, -8.2), (-10, 28, 7))
# pocket console
hh = box(1.7, .85, .22, hexc("#2C6B66")) + box(.08, .5, .22, hexc("#245A56"), (-.82, 0, 0)) + box(.08, .5, .22, hexc("#245A56"), (.82, 0, 0)) \
   + box(.74, .56, .23, hexc("#18241E"), (0, .04, 0)) + box(.6, .44, .235, (hexc("#9FDC5A"), hexc("#5E9E33")), (0, .04, 0)) \
   + box(.26, .08, .24, hexc("#16201C"), (-.6, -.05, 0)) + box(.08, .26, .24, hexc("#16201C"), (-.6, -.05, 0)) \
   + box(.11, .11, .24, hexc("#D2386F"), (.62, .04, 0)) + box(.11, .11, .24, hexc("#E8B23A"), (.52, -.12, 0))
scene += place(hh, (3.75, .7, -5.0), (-14, -34, -9))
# gold ring
scene += place(torus(.52, .15, hexc("#E3A72A")), (3.5, 2.6, -7.6), (68, 22, 0))
# magenta gem
scene += place(octa(.42, hexc("#D33B8D")), (-5.0, 3.0, -9.6), (12, 30, 8))
# cream cube
scene += place(box(.55, .55, .55, hexc("#D9CFB6")), (5.2, .28, -11.5), (0, 35, 0))

def render(with_toys=True):
    img = np.zeros((H, W, 3))
    ys = np.arange(H)[:, None]
    # sky gradient down to the horizon, floor below
    hor = H/2 - math.tan(-PITCH) * F * -1  # horizon row for a level ray
    hor = H/2 + math.tan(PITCH) * F * -1
    t = np.clip(ys / max(hor, 1), 0, 1)
    sky = BG_TOP*(1-t) + BG_HOR*t
    img[:] = np.where(ys < hor, sky, FLOOR)[:, None, :] if False else 0
    for y in range(H):
        img[y, :] = (BG_TOP*(1-min(y/hor, 1)) + BG_HOR*min(y/hor, 1)) if y < hor else FLOOR
    zbuf = np.full((H, W), np.inf)
    # floor grid lines (fogged)
    line = hexc("#2B2E4E")
    def seg(a, b, n=6000):
        for k in range(n + 1):
            p = a + (b - a) * k / n
            v = to_view(p)
            if -v[2] < .3: continue
            (x, y), z = project(v)
            if 0 <= x < W and 0 <= y < H and z < zbuf[y, x]:
                f = min(max((z - 2) / 20, 0), 1) ** .8
                img[y, x] = line * (1 - f) + FOG * f
                zbuf[y, x] = z + 1000  # floor never hides objects
    for gx in range(-40, 41, 2):
        seg(np.array([gx, 0, -.5]), np.array([gx, 0, -40.0]))
    for gz in range(2, 41, 2):
        seg(np.array([-40, 0, -gz]), np.array([40, 0, -gz]))
    if with_toys:
        for tri, cols in scene:
            vv = [to_view(p) for p in tri]
            if any(-v[2] < .3 for v in vv): continue
            n = np.cross(tri[1] - tri[0], tri[2] - tri[0]); nl = np.linalg.norm(n)
            if nl == 0: continue
            n /= nl
            pr = [project(v) for v in vv]
            (x0, y0), z0 = pr[0]; (x1, y1), z1 = pr[1]; (x2, y2), z2 = pr[2]
            area = (x1-x0)*(y2-y0) - (x2-x0)*(y1-y0)
            if area == 0: continue
            # world-space facing: light both sides (meshes are closed, back faces lose the z-test)
            lam = abs(float(n @ LIGHT))
            shade = .32 + .78 * lam
            minx, maxx = max(min(x0,x1,x2), 0), min(max(x0,x1,x2), W-1)
            miny, maxy = max(min(y0,y1,y2), 0), min(max(y0,y1,y2), H-1)
            if minx > maxx or miny > maxy: continue
            X, Y = np.meshgrid(np.arange(minx, maxx+1), np.arange(miny, maxy+1))
            w0 = ((x1-X)*(y2-Y) - (x2-X)*(y1-Y)) / area
            w1 = ((x2-X)*(y0-Y) - (x0-X)*(y2-Y)) / area
            w2 = 1 - w0 - w1
            inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not inside.any(): continue
            z = w0*z0 + w1*z1 + w2*z2
            sub = zbuf[miny:maxy+1, minx:maxx+1]
            m = inside & (z < sub)
            col = (w0[..., None]*cols[0] + w1[..., None]*cols[1] + w2[..., None]*cols[2]) * shade
            f = np.clip((z - 4) / 16, 0, 1)[..., None] * .85
            col = col*(1-f) + FOG*f
            region = img[miny:maxy+1, minx:maxx+1]
            region[m] = col[m]
            sub[m] = z[m]
    # 15-bit colour with 4x4 ordered dither
    B = np.array([[0,8,2,10],[12,4,14,6],[3,11,1,9],[15,7,13,5]]) / 16 - .5
    d = np.tile(B, (H//4 + 1, W//4 + 1))[:H, :W, None] * 6
    out = np.clip(np.floor((img + d) / 8) * 8 + 4, 0, 255).astype(np.uint8)
    return Image.fromarray(out)

render(True).save(sys.argv[1] + "/scene.png", optimize=True)
render(False).save(sys.argv[1] + "/grid.png", optimize=True)
