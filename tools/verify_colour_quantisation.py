import math
# Wyman/Sloan/Shirley multi-lobe Gaussian fits to CIE 1931 2-deg CMFs (lambda in nm)
def g(x,m,s1,s2):
    s = s1 if x<m else s2
    t=(x-m)/s
    return math.exp(-0.5*t*t)
def xbar(l): return 1.056*g(l,599.8,37.9,31.0)+0.362*g(l,442.0,16.0,26.7)-0.065*g(l,501.1,20.4,26.2)
def ybar(l): return 0.821*g(l,568.8,46.9,40.5)+0.286*g(l,530.9,16.3,31.1)
def zbar(l): return 1.217*g(l,437.0,11.8,36.0)+0.681*g(l,459.0,26.0,13.8)

h=6.62607015e-34; c=2.99792458e8; kB=1.380649e-23
def planck(l_nm,T):
    l=l_nm*1e-9
    return (2*h*c*c)/(l**5)/(math.expm1(h*c/(l*kB*T)))

def xyz(T):
    X=Y=Z=0.0
    for l in range(360,831,1):
        p=planck(l,T)
        X+=p*xbar(l); Y+=p*ybar(l); Z+=p*zbar(l)
    return X,Y,Z

M=[[3.2406,-1.5372,-0.4986],[-0.9689,1.8758,0.0415],[0.0557,-0.2040,1.0570]]
def to_srgb_linear(T):
    X,Y,Z=xyz(T)
    if Y<=0: return (0,0,0)
    X,Y,Z=X/Y,1.0,Z/Y  # normalise to unit luminance
    r=[sum(M[i][j]*v for j,v in enumerate((X,Y,Z))) for i in range(3)]
    return r

def lab(T, wp):
    # relative to D65 white so we can measure perceptual step size
    X,Y,Z=xyz(T); 
    X,Y,Z=X/Y,1.0,Z/Y
    Xn,Yn,Zn=wp
    def f(t):
        return t**(1/3) if t>(6/29)**3 else t/(3*(6/29)**2)+4/29
    fx,fy,fz=f(X/Xn),f(Y/Yn),f(Z/Zn)
    return (116*fy-16, 500*(fx-fy), 200*(fy-fz))

D65=(0.95047,1.0,1.08883)

def de(T1,T2):
    L1,a1,b1=lab(T1,D65); L2,a2,b2=lab(T2,D65)
    return math.sqrt((L1-L2)**2+(a1-a2)**2+(b1-b2)**2)

TMIN,TMAX=2000.0,50000.0
for bits in (5,6,7,8):
    N=2**bits
    ratio=(TMAX/TMIN)**(1.0/(N-1))
    worst=0.0; wT=0
    for i in range(N-1):
        T1=TMIN*ratio**i; T2=TMIN*ratio**(i+1)
        d=de(T1,T2)
        if d>worst: worst,wT=d,T1
    print(f"{bits} bits ({N:4d} steps, {(ratio-1)*100:5.2f}% Teff/step): worst adjacent dE76 = {worst:.3f}  (near {wT:.0f} K)")

print()
print("Blackbody sRGB (linear, unit-luminance, then gamma+normalised to max=1):")
def srgb_hex(T):
    r=to_srgb_linear(T)
    r=[max(0.0,v) for v in r]
    m=max(r) or 1.0
    r=[v/m for v in r]
    def gam(u): return 12.92*u if u<=0.0031308 else 1.055*u**(1/2.4)-0.055
    return "#%02X%02X%02X"%tuple(min(255,max(0,round(gam(v)*255))) for v in r)
for T in (2500,3000,3500,4000,4500,5000,5772,6500,7500,9000,12000,20000,35000,50000):
    r=to_srgb_linear(T)
    print(f"  {T:6d} K  {srgb_hex(T)}   linear RGB ratio {r[0]:.3f},{r[1]:.3f},{r[2]:.3f}")

# chroma / saturation of the stellar locus
print()
print("Perceptual chroma (CIELAB C*) of blackbody colours vs D65 white:")
for T in (2500,3000,4000,5000,5772,6500,8000,10000,20000,40000):
    L,a,b=lab(T,D65)
    print(f"  {T:6d} K  C* = {math.hypot(a,b):5.1f}")

print()
print("=== Perceptually-uniform palette allocation along Planckian locus ===")
# arc length in dE76 from 2000K to 50000K
Ts=[2000.0*(50000/2000)**(i/20000) for i in range(20001)]
arc=0.0
for i in range(len(Ts)-1):
    arc+=de(Ts[i],Ts[i+1])
print(f"total locus arc length 2000->50000 K = {arc:.1f} dE76")
for bits in (5,6,7,8):
    N=2**bits
    print(f"  {bits} bits ({N:4d} steps) perceptually uniform -> worst step {arc/(N-1):.2f} dE76")
print("  (JND ~ 2.3 dE76)")
