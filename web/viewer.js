/* Minecraft Living World Wallpaper: dependency-free offline WebGL2 runtime.
   This is deliberately not a complete Minecraft renderer or shaderpack. */
(() => {
  'use strict';
  const scene = window.MWW_SCENE;
  const canvas = document.getElementById('world');
  const err = document.getElementById('error');
  function fail(message) {
    err.hidden = false;
    err.textContent = String(message);
    console.error(message);
  }
  if (!scene || scene.schema !== 1) return fail('No compatible scene data. Generate a scene with the desktop control panel.');
  if (!canvas) return;
  const gl = canvas.getContext('webgl2', { alpha:true, antialias:true, powerPreference:'low-power' });
  if (!gl) return fail('WebGL2 is not available in this wallpaper browser.');
  document.body.classList.add(scene.light === 'night' ? 'night' : scene.light === 'day' ? 'day' : 'golden');
  if (new URLSearchParams(location.search).has('preview')) document.body.classList.add('preview');
  document.getElementById('world-title').textContent = scene.name || 'Minecraft Living World';
  document.getElementById('location-title').textContent = `${scene.dimension || 'overworld'} · ${(scene.stats || {}).blocks || 0} blocks · ${(scene.stats || {}).faces || 0} faces · ${scene.stats?.mobTextured ?? (scene.entities||[]).length}/${(scene.entities || []).length} textured mobs`;

  // Camera math: column-major matrices, no 3D runtime dependencies.
  const rad = d => d * Math.PI / 180;
  const vec = (x,y,z) => [x,y,z];
  const sub = (a,b) => [a[0]-b[0],a[1]-b[1],a[2]-b[2]];
  const dot = (a,b) => a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
  const cross = (a,b) => [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  const norm = a => {const n=Math.hypot(...a)||1;return a.map(x=>x/n);};
  function lookAt(eye, center) {
    const z=norm(sub(eye,center)),x=norm(cross([0,1,0],z)),y=cross(z,x);
    return new Float32Array([x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1]);
  }
  function perspective(fovy, aspect, near, far) {
    const f=1/Math.tan(fovy/2),nf=1/(near-far);
    return new Float32Array([f/aspect,0,0,0,0,f,0,0,0,0,(far+near)*nf,-1,0,0,2*far*near*nf,0]);
  }
  function mul(a,b) {
    const o=new Float32Array(16);
    for(let c=0;c<4;c++) for(let r=0;r<4;r++){
      let v=0;for(let k=0;k<4;k++)v+=a[k*4+r]*b[c*4+k];o[c*4+r]=v;
    }
    return o;
  }
  function compile(type,src) {
    const sh=gl.createShader(type);gl.shaderSource(sh,src);gl.compileShader(sh);
    if(!gl.getShaderParameter(sh,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(sh));
    return sh;
  }
  function program(vertex,fragment) {
    const p=gl.createProgram();
    gl.attachShader(p,compile(gl.VERTEX_SHADER,vertex));
    gl.attachShader(p,compile(gl.FRAGMENT_SHADER,fragment));
    gl.linkProgram(p);
    if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(p));
    return p;
  }

  const terrainVS = `#version 300 es
    precision highp float;
    layout(location=0) in vec3 aBlock;
    layout(location=1) in float aSide;
    layout(location=2) in float aTile;
    layout(location=3) in vec3 aTint;
    layout(location=4) in float aShape;
    uniform mat4 uMVP;
    uniform float uCols;
    out vec2 vUv;
    out vec3 vPos;
    out vec3 vNormal;
    out vec3 vTint;
    const vec2 corners[6]=vec2[6](vec2(0.,0.),vec2(1.,0.),vec2(1.,1.),vec2(0.,0.),vec2(1.,1.),vec2(0.,1.));
    void main(){
      vec2 uv=corners[gl_VertexID];int side=int(aSide+.5);
      vec3 p=vec3(uv,0.);vec3 n=vec3(0.,0.,-1.);
      if(side==1){p=vec3(1.-uv.x,uv.y,1.);n=vec3(0.,0.,1.);}
      if(side==2){p=vec3(0.,uv.y,1.-uv.x);n=vec3(-1.,0.,0.);}
      if(side==3){p=vec3(1.,uv.y,uv.x);n=vec3(1.,0.,0.);}
      if(side==4){p=vec3(uv.x,0.,1.-uv.y);n=vec3(0.,-1.,0.);}
      if(side==5){p=vec3(uv.x,1.,uv.y);n=vec3(0.,1.,0.);}
      if(side==6){p=vec3(uv.x,uv.y,uv.x);n=normalize(vec3(1.,0.,-1.));}
      if(side==7){p=vec3(1.-uv.x,uv.y,uv.x);n=normalize(vec3(1.,0.,1.));}
      if(aShape>0.5 && aShape<1.5) p.y=.5 + p.y*.5;
      if(aShape>1.5 && aShape<2.5) p.y=p.y*.5;
      if(aShape>2.5) p.y=p.y*.063;
      vPos=aBlock+p;vNormal=n;vTint=aTint;
      vec2 tile=vec2(mod(aTile,uCols),floor(aTile/uCols));
      // Canvas uploads are NOT flipped: atlas row 0 must remain texture row 0.
      // Flip only the UV within each tile so block faces stay upright, and
      // sample texel centres to avoid sampling the transparent 2px gutter.
      vUv=(tile*36.+vec2(2.5+uv.x*31.,2.5+(1.-uv.y)*31.))/(36.*uCols);
      gl_Position=uMVP*vec4(vPos,1.);
    }`;
  const lighting = `
    uniform vec3 uSunDir;
    uniform vec3 uAmbient;
    uniform vec3 uSun;
    uniform vec3 uFogColor;
    uniform vec3 uEye;
    uniform float uFogNear;
    uniform float uFogFar;
    uniform vec3 uLampPos[8];
    uniform int uLampCount;
    vec3 shade(vec3 base,vec3 p,vec3 n){
      float diffuse=max(0.,dot(normalize(n),normalize(uSunDir)));
      vec3 color=base*(uAmbient + uSun*diffuse);
      for(int i=0;i<8;i++){
        if(i>=uLampCount)break;
        vec3 delta=uLampPos[i]-p;
        float d2=dot(delta,delta);
        float strength=1.65/(1.+d2*.12);
        color+=base*vec3(1.0,.72,.36)*strength;
      }
      return color;
    }
    vec3 grade(vec3 value){
      value=max(value,vec3(0.));
      return pow(value/(vec3(1.)+.35*value),vec3(.91));
    }
    vec3 doFog(vec3 color,vec3 p){
      float f=clamp((length(p-uEye)-uFogNear)/max(1.,uFogFar-uFogNear),0.,1.);
      return mix(color,uFogColor,f*f*.85);
    }
  `;
  const terrainFS = `#version 300 es
    precision highp float;
    in vec2 vUv;in vec3 vPos;in vec3 vNormal;in vec3 vTint;
    uniform sampler2D uAtlas;
    uniform bool uTransparent;
    uniform float uCutRadius;
    ${lighting}
    out vec4 frag;
    void main(){
      // On a continuous, fully connected landscape, these are artificial
      // crop-box walls, not actual cliffs. Keep natural interior cliff faces.
      if(uCutRadius>0. &&
         ((abs(vPos.x)>=uCutRadius-.01 && vPos.x*vNormal.x>.5) ||
          (abs(vPos.z)>=uCutRadius-.01 && vPos.z*vNormal.z>.5))) discard;
      vec4 tex=texture(uAtlas,vUv);
      if(tex.a<.12)discard;
      vec3 base=tex.rgb*vTint;
      vec3 color=doFog(grade(shade(base,vPos,vNormal)),vPos);
      frag=vec4(color,uTransparent?min(tex.a,.83):tex.a);
    }`;
  // Real vanilla entity UVs use the same lighting/fog material functions.
  const modelVS = `#version 300 es
    precision highp float;
    layout(location=0) in vec3 aPos;
    layout(location=1) in vec3 aNormal;
    layout(location=2) in vec2 aUV;
    layout(location=3) in vec3 aTint;
    layout(location=4) in float aFloat;
    uniform mat4 uMVP;uniform float uTime;
    out vec3 vPos;out vec3 vNormal;out vec2 vUV;out vec3 vTint;
    void main(){
      vec3 p=aPos;
      if(aFloat>.5)p.y+=sin(uTime*.55+p.x*.17+p.z*.24)*.13;
      vPos=p;vNormal=aNormal;vUV=aUV;vTint=aTint;
      gl_Position=uMVP*vec4(p,1.);
    }`;
  const modelFS = `#version 300 es
    precision highp float;
    in vec3 vPos;in vec3 vNormal;in vec2 vUV;in vec3 vTint;
    uniform sampler2D uModelTexture;
    ${lighting}
    out vec4 frag;
    void main(){
      vec4 tex=texture(uModelTexture,vUV);
      if(tex.a<.12)discard;
      vec3 result=doFog(grade(shade(tex.rgb*vTint,vPos,vNormal)),vPos);
      frag=vec4(result,tex.a);
    }`;
  const petVS = `#version 300 es
    precision highp float;
    layout(location=0) in vec3 aPos;
    layout(location=1) in vec3 aNormal;
    layout(location=2) in vec3 aColor;
    layout(location=3) in float aKind;
    uniform mat4 uMVP;uniform float uTime;
    out vec3 vPos;out vec3 vNormal;out vec3 vColor;
    void main(){
      vec3 p=aPos;
      if(aKind>0.5) p.y += sin(uTime*.55+p.x*.17+p.z*.24)*.18;
      vPos=p;vNormal=aNormal;vColor=aColor;
      gl_Position=uMVP*vec4(p,1.);
    }`;
  const petFS = `#version 300 es
    precision highp float;
    in vec3 vPos;in vec3 vNormal;in vec3 vColor;
    uniform float uHorizonRadius;
    ${lighting}
    out vec4 frag;
    void main(){
      vec3 color=doFog(grade(shade(vColor,vPos,vNormal)),vPos);
      float alpha=1.;
      if(uHorizonRadius>0.){
        float edge=max(abs(vPos.x),abs(vPos.z));
        alpha=1.-smoothstep(uHorizonRadius*.78,uHorizonRadius,edge);
        if(alpha<.015)discard;
      }
      frag=vec4(color,alpha);
    }`;

  function fromB64(input){
    const bytes=atob(input || ''),out=new Uint8Array(bytes.length);
    for(let i=0;i<bytes.length;i++)out[i]=bytes.charCodeAt(i);
    return out;
  }
  function faceVAO(encoded){
    const bytes=fromB64(encoded),vao=gl.createVertexArray();
    gl.bindVertexArray(vao);
    gl.bindBuffer(gl.ARRAY_BUFFER,gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER,bytes,gl.STATIC_DRAW);
    const stride=16;
    gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,3,gl.SHORT,false,stride,0);gl.vertexAttribDivisor(0,1);
    gl.enableVertexAttribArray(1);gl.vertexAttribPointer(1,1,gl.UNSIGNED_BYTE,false,stride,6);gl.vertexAttribDivisor(1,1);
    gl.enableVertexAttribArray(2);gl.vertexAttribPointer(2,1,gl.UNSIGNED_SHORT,false,stride,8);gl.vertexAttribDivisor(2,1);
    gl.enableVertexAttribArray(3);gl.vertexAttribPointer(3,3,gl.UNSIGNED_BYTE,true,stride,10);gl.vertexAttribDivisor(3,1);
    gl.enableVertexAttribArray(4);gl.vertexAttribPointer(4,1,gl.UNSIGNED_BYTE,false,stride,13);gl.vertexAttribDivisor(4,1);
    gl.bindVertexArray(null);
    return { vao, count:bytes.length/stride, bytes };
  }

  // Deliberately low-polygon, recognisable resident models, not game meshes.
  function petGeometry(animals,origin){
    const verts=[];
    const facenorms=[[0,0,-1],[0,0,1],[-1,0,0],[1,0,0],[0,-1,0],[0,1,0]];
    const faceCorners=[
      [[0,0,0],[1,0,0],[1,1,0],[0,1,0]],
      [[1,0,1],[0,0,1],[0,1,1],[1,1,1]],
      [[0,0,1],[0,0,0],[0,1,0],[0,1,1]],
      [[1,0,0],[1,0,1],[1,1,1],[1,1,0]],
      [[0,0,1],[1,0,1],[1,0,0],[0,0,0]],
      [[0,1,0],[0,1,1],[1,1,1],[1,1,0]],
    ];
    const order=[0,1,2,0,2,3];
    function box(base,x,y,z,w,h,d,color,kind,yaw){
      const ca=Math.cos(yaw),sa=Math.sin(yaw);
      for(let side=0;side<6;side++){
        const n=facenorms[side],nn=[n[0]*ca-n[2]*sa,n[1],n[0]*sa+n[2]*ca];
        for(const ix of order){
          const v=faceCorners[side][ix],lx=x+v[0]*w,lz=z+v[2]*d;
          const px=base[0]+lx*ca-lz*sa,py=base[1]+y+v[1]*h,pz=base[2]+lx*sa+lz*ca;
          verts.push(px,py,pz,...nn,...color,kind);
        }
      }
    }
    for(const e of animals){
      const raw=e.pos || [0,0,0];
      const p=[raw[0]-origin[0],raw[1]-origin[1],raw[2]-origin[2]];
      const yaw=(e.yaw || 0)*Math.PI/180;
      const kind=e.type === 'happy_ghast' ? 1:0;
      const scale=e.baby ? .55:1;
      const b=(x,y,z,w,h,d,color)=>box(p,x*scale,y*scale,z*scale,w*scale,h*scale,d*scale,color,kind,yaw);
      if(e.type === 'happy_ghast'){
        const ivory=[.94,.94,.88],gray=[.74,.78,.78],dark=[.14,.18,.22],pink=[.9,.55,.58];
        b(-1.35,1.55,-1.35,2.7,2.25,2.7,ivory);
        for(const x of [-.95,-.25,.45,.95])for(const z of [-.92,.45])b(x,.76,z,.29,.85,.28,gray);
        b(-.78,2.55,1.36,.43,.35,.045,dark);b(.37,2.55,1.36,.43,.35,.045,dark);
        b(-.29,2.13,1.36,.58,.13,.049,pink);
      } else if(e.type === 'horse'){
        const coat=[.52,.32,.20],mane=[.28,.19,.15],muzzle=[.66,.53,.39];
        b(-.75,1.02,-.30,1.5,.78,.62,coat);
        for(const x of [-.55,.48])for(const z of [-.22,.17])b(x,.14,z,.24,.96,.20,coat);
        b(.49,1.51,-.22,.35,.80,.43,coat);b(.63,2.08,-.23,.55,.44,.48,muzzle);
        b(.76,2.4,-.18,.12,.28,.14,mane);b(.05,1.67,-.12,.55,.23,.26,mane);
      } else if(e.type === 'wolf'){
        const fur=[.70,.72,.70],face=[.85,.84,.78],dark=[.21,.23,.24],red=[.73,.17,.14];
        b(-.4,.45,-.24,.83,.51,.48,fur);
        for(const x of [-.29,.24])for(const z of [-.16,.14])b(x,.06,z,.16,.43,.17,fur);
        b(.36,.66,-.20,.39,.39,.40,face);b(.65,.60,-.11,.20,.20,.22,face);
        b(.4,.99,-.15,.12,.20,.13,fur);b(.60,.99,-.15,.12,.20,.13,fur);
        b(.70,.76,-.12,.04,.08,.06,dark);b(-.65,.73,-.10,.31,.15,.16,fur);
        b(.36,.69,-.25,.14,.13,.04,red);
      } else if(e.type === 'cat'){
        const orange=[.79,.51,.25],cream=[.93,.75,.51],dark=[.21,.20,.19];
        b(-.36,.26,-.16,.72,.28,.32,orange);
        for(const x of [-.27,.20])for(const z of [-.13,.10])b(x,.03,z,.11,.25,.10,orange);
        b(.3,.36,-.17,.28,.28,.33,cream);
        b(.34,.61,-.15,.09,.18,.12,orange);b(.51,.61,-.15,.09,.18,.12,orange);
        b(.56,.51,-.15,.04,.07,.05,dark);b(-.55,.36,.06,.12,.12,.12,orange);
      } else if(e.type === 'allay'){
        const blue=[.34,.81,.98],wing=[.55,.86,.97];
        b(-.25,.6,-.2,.5,.65,.4,blue);b(-.52,.9,-.10,.29,.40,.16,wing);b(.30,.9,-.10,.29,.40,.16,wing);
      } else if(e.type === 'fox'){
        const fur=[.85,.36,.16],cream=[.96,.9,.78];
        b(-.47,.29,-.23,.85,.38,.45,fur);b(.31,.35,-.20,.33,.36,.4,fur);
        b(.32,.70,-.17,.12,.2,.11,fur);b(.50,.70,-.17,.12,.2,.11,fur);b(-.72,.37,.05,.35,.18,.20,cream);
      } else if(e.type === 'parrot'){
        b(-.15,.30,-.14,.30,.52,.28,[.3,.82,.44]);b(-.12,.79,-.10,.25,.22,.22,[.91,.75,.22]);
      }
    }
    return new Float32Array(verts);
  }
  function petVAO(array){
    const vao=gl.createVertexArray();gl.bindVertexArray(vao);gl.bindBuffer(gl.ARRAY_BUFFER,gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER,array,gl.STATIC_DRAW);
    for(const [loc,n,off] of [[0,3,0],[1,3,3],[2,3,6],[3,1,9]]){
      gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,n,gl.FLOAT,false,40,off*4);
    }
    gl.bindVertexArray(null);
    return {vao,count:array.length/10};
  }


  // An independent, versioned low-detail surroundings adapter. The detailed
  // block renderer remains unchanged; missing saved chunks never get invented.
  function landscapeGeometry(data, nearRadius){
    if(!data || data.version!==1 || !(data.present>0))return [];
    const n=Number(data.size),step=Number(data.step);
    if(!Number.isInteger(n)||n<2||n>97||![4,8,16].includes(step))throw Error('Invalid landscape grid');
    const raw=fromB64(data.samples);
    if(raw.byteLength!==n*n*5)throw Error('Invalid landscape data length');
    const view=new DataView(raw.buffer,raw.byteOffset,raw.byteLength);
    const points=[];
    for(let z=0;z<n;z++)for(let x=0;x<n;x++){
      const index=(z*n+x)*5,y=view.getInt16(index,true);
      points.push(y===-32768?null:{
        pos:[data.x0+x*step,y+.06,data.z0+z*step],
        rgb:[raw[index+2]/255,raw[index+3]/255,raw[index+4]/255]
      });
    }
    const mesh=[];
    function triangle(a,b,c){
      if(!a||!b||!c)return;
      const u=sub(b.pos,a.pos),v=sub(c.pos,a.pos),normal=norm(cross(u,v));
      if(normal[1]<0)normal.forEach((v,i)=>normal[i]=-v);
      for(const point of [a,b,c])mesh.push(...point.pos,...normal,...point.rgb,0);
    }
    for(let z=0;z<n-1;z++)for(let x=0;x<n-1;x++){
      const cx=data.x0+(x+.5)*step,cz=data.z0+(z+.5)*step;
      // Do not put a coarse skin over the detailed base or its interiors.
      if(Math.abs(cx)<nearRadius&&Math.abs(cz)<nearRadius)continue;
      const a=points[z*n+x],b=points[z*n+x+1];
      const c=points[(z+1)*n+x],d=points[(z+1)*n+x+1];
      triangle(a,c,b);triangle(b,c,d);
    }
    return mesh;
  }

  function modelVAO(verts){
    const vao=gl.createVertexArray();gl.bindVertexArray(vao);
    gl.bindBuffer(gl.ARRAY_BUFFER,gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER,verts,gl.STATIC_DRAW);
    const stride=48;
    for(const [i,n,offset] of [[0,3,0],[1,3,12],[2,2,24],[3,3,32],[4,1,44]]){
      gl.enableVertexAttribArray(i);
      gl.vertexAttribPointer(i,n,gl.FLOAT,false,stride,offset);
    }
    gl.bindVertexArray(null);
    return {vao,count:verts.length/12};
  }
  function loadModelTextures(textures){
    const results={};
    return Promise.all(Object.entries(textures||{}).map(([key,encoded])=>
      new Promise((resolve,reject)=>{
        const im=new Image();
        im.onload=()=>{
          try{
            const texture=gl.createTexture();
            gl.bindTexture(gl.TEXTURE_2D,texture);
            gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,false);
            gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,im);
            gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);
            gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);
            gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);
            gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
            results[key]=texture;resolve();
          }catch(e){reject(e);}
        };
        im.onerror=()=>reject(new Error('Invalid Minecraft mob texture: '+key));
        im.src='data:image/png;base64,'+encoded;
      })
    )).then(()=>results);
  }

  let terrain, pets, models, opaque, alpha, petMesh, landscapeMesh, modelMeshes=[];
  try{
    terrain=program(terrainVS,terrainFS);pets=program(petVS,petFS);
    models=program(modelVS,modelFS);
    opaque=faceVAO(scene.opaque);alpha=faceVAO(scene.alpha);
    // Old generated scenes keep their simple models; new scenes do not
    // describe coloured cubes as real Minecraft entity geometry.
    petMesh=petVAO(scene.entityAssets?new Float32Array():
      petGeometry(scene.entities||[],scene.origin||[0,0,0]));
    if(scene.entityAssets&&window.MWW_ENTITY_MODELS){
      for(const item of window.MWW_ENTITY_MODELS.create(
          scene.entities||[],scene.entityAssets,scene.origin||[0,0,0]))
        modelMeshes.push({texture:item.texture,mesh:modelVAO(item.vertices)});
    }
    landscapeMesh=petVAO(landscapeGeometry(scene.landscape,Number(scene.radius||24)));
  }catch(e){return fail('WebGL scene creation failed: '+e.message);}
  gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);
  gl.disable(gl.CULL_FACE);

  const preset={
    golden:{ambient:[.70,.72,.80],sun:[.98,.79,.54],dir:[.45,.73,.34],fog:[.69,.68,.63]},
    day:{ambient:[.83,.89,.96],sun:[.83,.89,.93],dir:[.35,.94,.25],fog:[.65,.81,.89]},
    night:{ambient:[.20,.28,.45],sun:[.22,.29,.48],dir:[-.22,.68,.52],fog:[.12,.18,.29]}
  }[scene.light] || {ambient:[.7,.75,.8],sun:[1.,.9,.75],dir:[.45,.7,.4],fog:[.65,.7,.75]};

  function commonUniforms(prog,mvp,eye,time){
    gl.useProgram(prog);
    const m=(name)=>gl.getUniformLocation(prog,name);
    gl.uniformMatrix4fv(m('uMVP'),false,mvp);
    gl.uniform3fv(m('uEye'),eye);
    gl.uniform3fv(m('uAmbient'),preset.ambient);
    gl.uniform3fv(m('uSun'),preset.sun);
    gl.uniform3fv(m('uSunDir'),norm(preset.dir));
    gl.uniform3fv(m('uFogColor'),preset.fog);
    const radius=scene.radius||24;
    const farRadius=Number(scene.landscape?.present>0?scene.landscape.radius:radius);
    gl.uniform1f(m('uFogNear'),Math.max(radius*.9,distance*.65));
    gl.uniform1f(m('uFogFar'),Math.max(radius*3.1,farRadius*.90,distance+radius*2.6));
    if(prog===terrain)gl.uniform1f(m('uCutRadius'),scene.landscape?.joinable?radius:0.);
    const lights=(scene.lights||[]).slice(0,8);
    gl.uniform1i(m('uLampCount'),lights.length);
    const flat=new Float32Array(24);
    for(let i=0;i<lights.length;i++){
      const v=lights[i];flat[i*3]=v[0]-scene.origin[0];flat[i*3+1]=v[1]-scene.origin[1];flat[i*3+2]=v[2]-scene.origin[2];
    }
    gl.uniform3fv(m('uLampPos[0]'),flat);
    if(prog===pets){gl.uniform1f(m('uTime'),time);gl.uniform1f(m('uHorizonRadius'),0.);}
  }

  function loadAtlas(tiles){
    const count=Math.max(1,tiles.length),cols=1<<Math.ceil(Math.log2(Math.ceil(Math.sqrt(count))));
    const rows=Math.ceil(count/cols),size=36;
    const off=document.createElement('canvas');off.width=cols*size;off.height=cols*size;
    const ctx=off.getContext('2d',{willReadFrequently:false});
    if(!ctx)throw Error('2D canvas unavailable');
    ctx.imageSmoothingEnabled=false;
    const loads=tiles.map((tile,index)=>new Promise(resolve=>{
      const x=index%cols*size+2,y=Math.floor(index/cols)*size+2;
      const rgb=tile.rgb||[130,140,145];
      ctx.fillStyle=`rgb(${rgb.join(',')})`;ctx.fillRect(x,y,32,32);
      if(!tile.png)return resolve();
      const im=new Image();
      im.onload=()=>{try{ctx.drawImage(im,0,0,im.width,Math.min(im.width,im.height),x,y,32,32);}catch(_){/* palette fallback */}resolve();};
      im.onerror=resolve;
      im.src='data:image/png;base64,'+tile.png;
    }));
    return Promise.all(loads).then(()=>{
      const tx=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,tx);
      // Do not flip the entire atlas: only its first rows contain tiles when
      // the texture count is not a full square. Flipping turns every block
      // transparent for e.g. 31 textures in an 8x8 atlas.
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,false);
      gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,off);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
      gl.bindTexture(gl.TEXTURE_2D,null);
      return {tx,cols};
    });
  }

  // Derive a scenic camera target from visible block surfaces, not the
  // player's last saved Y. The player may have been flying above the base.
  // This uses only already generated face data; no additional world scan.
  function terrainFocus(meshes) {
    const close=[],wide=[];
    const inner=Math.max(8,Math.min(16,Number(scene.radius||24)*.55));
    for(const mesh of meshes){
      const view=new DataView(mesh.bytes.buffer,mesh.bytes.byteOffset,mesh.bytes.byteLength);
      for(let i=0;i<mesh.count;i++){
        const offset=i*16,face=view.getUint8(offset+6);
        if(face!==5)continue;
        const x=view.getInt16(offset,true),y=view.getInt16(offset+2,true),z=view.getInt16(offset+4,true);
        wide.push(y);
        if(Math.abs(x)<=inner && Math.abs(z)<=inner)close.push(y);
      }
    }
    const heights=close.length>=8?close:wide;
    if(!heights.length)return [0,1.5,0];
    heights.sort((a,b)=>a-b);
    const h=heights[Math.floor(heights.length*.55)];
    return [0,Math.max(-256,Math.min(256,h+1.5)),0];
  }
  const surfaceFocus=terrainFocus([opaque,alpha]);
  const pY=(scene.entities||[]).map(e=>Number(e.pos?.[1])-Number(scene.origin?.[1]))
    .filter(Number.isFinite).sort((a,b)=>a-b);
  const explicitTarget=scene.camera?.target;
  const hasTarget=Array.isArray(explicitTarget)&&explicitTarget.length===3&&explicitTarget.every(Number.isFinite);
  const baseFocus=hasTarget?explicitTarget.slice():surfaceFocus.slice();
  const initialYaw=rad(Number(scene.camera?.yaw||42));
  const initialPitch=rad(Number(scene.camera?.pitch||22));
  const requestedDistance=Math.max(4,Number(scene.camera?.distance||Math.max(14,scene.radius*2.2)));
  // Old saved shots remain unchanged. With a surrounding world, choose a
  // camera that actually sees it rather than filling the screen with the
  // original 24-block cutout. Explicit camera targets always take priority.
  const visibleLandscape=Number(scene.landscape?.present||0)>0;
  const baseDistance=(!hasTarget && visibleLandscape)
    ? Math.max(requestedDistance,Math.min(160,Number(scene.landscape.radius)*.72))
    : requestedDistance;
  if(!hasTarget && visibleLandscape){
    const data=scene.landscape,raw=fromB64(data.samples),view=new DataView(raw.buffer,raw.byteOffset,raw.byteLength);
    const near=Number(scene.radius||24),values=[];
    for(let z=0;z<data.size;z++)for(let x=0;x<data.size;x++){
      const px=data.x0+x*data.step,pz=data.z0+z*data.step;
      const edge=Math.max(Math.abs(px),Math.abs(pz));
      if(edge<=near+data.step || edge>Math.min(data.radius*.7,near*3))continue;
      const y=view.getInt16((z*data.size+x)*5,true);
      if(y!==-32768)values.push(y);
    }
    if(values.length){
      values.sort((a,b)=>a-b);
      const median=values[Math.floor(values.length/2)];
      const shift=Math.max(-20,Math.min(20,median-baseFocus[1]));
      baseFocus[1]+=shift*.35;
    }
  }
  const allFocus=baseFocus.slice();
  let allDistance=baseDistance;
  if(!hasTarget && pY.length){
    const bottom=Math.min(surfaceFocus[1]-2,pY[0]-1);
    const top=Math.max(surfaceFocus[1]+3,pY[pY.length-1]+4);
    allFocus[1]=(bottom+top)/2;
    const r=Math.max(4,Number(scene.radius||24));
    const halfSpan=(top-bottom)/2;
    const cp=Math.abs(Math.cos(initialPitch)),sp=Math.abs(Math.sin(initialPitch));
    const vHalf=halfSpan*cp+r*.85*sp;
    const depthHalf=halfSpan*sp+r*.85*cp;
    const aspect=Math.max(1,canvas.clientWidth/Math.max(1,canvas.clientHeight));
    const required=Math.max(vHalf/Math.tan(rad(30)),r/(Math.tan(rad(30))*aspect))+depthHalf;
    allDistance=Math.max(baseDistance,required*1.12);
  }
  delete opaque.bytes;delete alpha.bytes;
  let framingAll=false;
  let firstFocus=baseFocus;
  let yaw=initialYaw,pitch=initialPitch,mouseX=0,mouseY=0,motion=true,paused=false;
  let distance=baseDistance;
  let lastDraw=0,frameQueued=false,atlas=null,modelTextures={};
  let dragging=false,dragX=0,dragY=0;
  const start=performance.now();
  function draw(now=performance.now()){
    frameQueued=false;
    if(paused || !atlas || document.hidden)return;
    const dpr=Math.min(1.5,window.devicePixelRatio||1);
    const w=Math.min(2560,Math.round(canvas.clientWidth*dpr)),h=Math.min(1440,Math.round(canvas.clientHeight*dpr));
    if(!w||!h)return;
    if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
    gl.viewport(0,0,w,h);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
    const elapsed=(now-start)/1000;
    const pan=motion ? Math.sin(elapsed*.045)*rad(.65):0;
    const yy=yaw+pan+mouseX*.055,pp=Math.max(-.26,Math.min(1.35,pitch-mouseY*.033));
    const focus=firstFocus;
    const eye=[focus[0]+Math.sin(yy)*Math.cos(pp)*distance,focus[1]+Math.sin(pp)*distance,focus[2]+Math.cos(yy)*Math.cos(pp)*distance];
    const mvp=mul(perspective(rad(60),w/h,.1,Math.max(250,distance*8)),lookAt(eye,focus));
    if(landscapeMesh.count){
      commonUniforms(pets,mvp,eye,elapsed);
      gl.uniform1f(gl.getUniformLocation(pets,'uHorizonRadius'),Number(scene.landscape.radius));
      gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.depthMask(false);
      gl.bindVertexArray(landscapeMesh.vao);
      gl.drawArrays(gl.TRIANGLES,0,landscapeMesh.count);
      gl.depthMask(true);gl.disable(gl.BLEND);
    }
    commonUniforms(terrain,mvp,eye,elapsed);
    gl.uniform1f(gl.getUniformLocation(terrain,'uCols'),atlas.cols);
    gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,atlas.tx);
    gl.uniform1i(gl.getUniformLocation(terrain,'uAtlas'),0);
    gl.uniform1i(gl.getUniformLocation(terrain,'uTransparent'),0);
    gl.bindVertexArray(opaque.vao);gl.drawArraysInstanced(gl.TRIANGLES,0,6,opaque.count);
    if(gl.getError()!==gl.NO_ERROR){paused=true;return fail('Terrain drawing failed in WebGL. Try a smaller radius or report the browser/GPU and displayed face count.');}
    if(modelMeshes.length){
      commonUniforms(models,mvp,eye,elapsed);
      gl.uniform1f(gl.getUniformLocation(models,'uTime'),elapsed);
      gl.uniform1i(gl.getUniformLocation(models,'uModelTexture'),1);
      gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
      gl.activeTexture(gl.TEXTURE1);
      for(const entry of modelMeshes){
        const texture=modelTextures[entry.texture];
        if(!texture)continue;
        gl.bindTexture(gl.TEXTURE_2D,texture);
        gl.bindVertexArray(entry.mesh.vao);
        gl.drawArrays(gl.TRIANGLES,0,entry.mesh.count);
      }
      gl.disable(gl.BLEND);
      gl.activeTexture(gl.TEXTURE0);
    }
    commonUniforms(pets,mvp,eye,elapsed);
    gl.bindVertexArray(petMesh.vao);gl.drawArrays(gl.TRIANGLES,0,petMesh.count);
    if(alpha.count){
      commonUniforms(terrain,mvp,eye,elapsed);gl.uniform1f(gl.getUniformLocation(terrain,'uCols'),atlas.cols);
      gl.uniform1i(gl.getUniformLocation(terrain,'uTransparent'),1);
      gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.depthMask(false);
      gl.bindVertexArray(alpha.vao);gl.drawArraysInstanced(gl.TRIANGLES,0,6,alpha.count);
      gl.depthMask(true);gl.disable(gl.BLEND);
    }
    gl.bindVertexArray(null);
    lastDraw=now;
  }
  function request(){if(!frameQueued&&!paused&&!document.hidden){frameQueued=true;requestAnimationFrame(draw);}}
  canvas.addEventListener('pointermove',e=>{
    const rect=canvas.getBoundingClientRect();
    mouseX=Math.max(-1,Math.min(1,((e.clientX-rect.left)/rect.width-.5)*2));
    mouseY=Math.max(-1,Math.min(1,((e.clientY-rect.top)/rect.height-.5)*2));
    if(dragging){yaw+=(e.clientX-dragX)*.004;pitch=Math.max(-.25,Math.min(1.4,pitch+(e.clientY-dragY)*.003));dragX=e.clientX;dragY=e.clientY;}
    request();
  });
  if(document.body.classList.contains('preview')){
    canvas.addEventListener('pointerdown',e=>{dragging=true;dragX=e.clientX;dragY=e.clientY;});
    window.addEventListener('pointerup',()=>dragging=false);
    canvas.addEventListener('wheel',e=>{e.preventDefault();distance=Math.max(3,Math.min(150,distance*(e.deltaY>0?1.07:.93)));request();},{passive:false});
  }
  const turn=d=>{yaw+=d;request();};
  document.getElementById('left').onclick=()=>turn(-rad(15));
  document.getElementById('right').onclick=()=>turn(rad(15));
  const frameButton=document.getElementById('frame');
  frameButton.onclick=()=>{
    framingAll=!framingAll;
    firstFocus=framingAll?allFocus:baseFocus;
    distance=framingAll?allDistance:baseDistance;
    frameButton.textContent=framingAll?'Base':'All';request();
  };
  document.getElementById('reset').onclick=()=>{
    yaw=initialYaw;pitch=initialPitch;distance=baseDistance;mouseX=mouseY=0;
    framingAll=false;firstFocus=baseFocus;frameButton.textContent='All';request();
  };
  const motionButton=document.getElementById('motion');
  motionButton.onclick=()=>{motion=!motion;motionButton.textContent=motion?'❚❚':'▶';request();};
  document.addEventListener('visibilitychange',()=>{paused=document.hidden;if(!paused)request();});
  window.livelyPropertyListener=(name,value)=>{if(name==='motion'){motion=Boolean(value);request();}if(name==='pause'){paused=Boolean(value);request();}};
  window.addEventListener('message',e=>{if(e.data?.type==='mww-pause')paused=true;if(e.data?.type==='mww-resume'){paused=false;request();}});
  window.addEventListener('resize',request);
  // Wallpaper is capped at 10fps while gently animated; otherwise it renders on interaction only.
  setInterval(()=>{if(!paused&&!document.hidden&&motion&&(scene.entities?.length || true))request();},100);
  if(!opaque.count&&!alpha.count)fail('The generated scene has zero visible block faces. Check the selected height range and regenerate.');
  else Promise.all([
    loadAtlas(scene.tiles||[]),
    loadModelTextures(scene.entityAssets?.textures||{})
  ]).then(([a,t])=>{atlas=a;modelTextures=t;request();})
    .catch(e=>fail('Texture loading failed: '+e.message));
})();
