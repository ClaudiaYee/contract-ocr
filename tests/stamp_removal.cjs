// 浏览器版 OCR 的去章逻辑与 native/stamp_removal.py 一致（合成像素）
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const ctx=vm.createContext({window:{},console});vm.runInContext(fs.readFileSync(path.resolve(__dirname,'../js/paddle-ocr.js'),'utf8')+';this.P=PaddleOCR;',ctx);
const remove=ctx.P._removeStampsRGBA,W=1654,H=2339;
const blank=()=>{const d=new Uint8ClampedArray(W*H*4);d.fill(255);return d;};
const px=(d,x,y,[r,g,b])=>{const p=(y*W+x)*4;d[p]=r;d[p+1]=g;d[p+2]=b;};
const rect=(d,x0,y0,x1,y1,c)=>{for(let y=y0;y<y1;y++)for(let x=x0;x<x1;x++)px(d,x,y,c);};
const ring=(d,cx,cy,r,t,c)=>{for(let y=cy-r;y<=cy+r;y++)for(let x=cx-r;x<=cx+r;x++){const q=Math.hypot(x-cx,y-cy);if(q<=r&&q>=r-t)px(d,x,y,c);}};
const redCount=d=>{let n=0;for(let p=0;p<d.length;p+=4)if(d[p]-Math.max(d[p+1],d[p+2])>40&&d[p]>=110)n++;return n;};
const RED=[215,40,40];
let d=blank();rect(d,150,400,1200,430,[20,20,20]);ring(d,680,430,180,7,RED);for(let i=0;i<10;i++)rect(d,560+i*25,300,575+i*25,330,RED);rect(d,1000,900,1260,908,RED);rect(d,1000,1152,1260,1160,RED);rect(d,1000,900,1008,1160,RED);rect(d,1252,900,1260,1160,RED);
let r=remove(d,W,H);assert.equal(r.removed,2);assert.equal(redCount(r.data),0);assert(redCount(d)>0,'input untouched');
for(let x=150;x<1200;x+=97){const p=(415*W+x)*4;assert.deepEqual([r.data[p],r.data[p+1],r.data[p+2]],[20,20,20],'black text kept');}
d=blank();rect(d,150,150,1450,185,RED);for(let i=0;i<4;i++)rect(d,150,260+i*52,1400,290+i*52,[200,30,30]);rect(d,150,560,175,585,RED);
r=remove(d,W,H);assert.equal(r.removed,0);assert.strictEqual(r.data,d,'red text page unchanged');
d=blank();rect(d,300,300,600,600,RED);assert.equal(remove(d,W,H).removed,0,'solid red block is not a seal');
console.log('PASS stamp removal (browser): seals removed, red text / blocks / dark text kept');
