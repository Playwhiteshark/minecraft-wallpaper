/* Minecraft Living World Wallpaper: vanilla mob model adapter.
   Descriptions are generated from the public versioned Minecraft entity-model
   extractor and cached locally on user-triggered refresh. This module contains
   NO Mojang models or textures and uses NO external runtime dependencies.
   Output: world-space triangles with UVs/material layers for the shared shader.
*/
(() => {
  'use strict';
  const scale=1/16;
  const rad=v=>v*Math.PI/180;
  const dye=[
    [1.,1.,1.],[.85,.50,.20],[.75,.35,.84],[.40,.60,.86],
    [.90,.88,.32],[.45,.70,.18],[.89,.47,.66],[.28,.32,.35],
    [.61,.62,.62],[.20,.55,.62],[.55,.31,.75],[.25,.33,.70],
    [.45,.30,.20],[.37,.50,.22],[.70,.25,.22],[.14,.16,.18]
  ];
  function rot(v, angles) {
    let [x,y,z]=v;
    let [rx,ry,rz]=angles||[0,0,0];
    let a=Math.cos(rx),b=Math.sin(rx);[y,z]=[y*a-z*b,y*b+z*a];
    a=Math.cos(ry);b=Math.sin(ry);[x,z]=[x*a+z*b,-x*b+z*a];
    a=Math.cos(rz);b=Math.sin(rz);[x,y]=[x*a-y*b,x*b+y*a];
    return [x,y,z];
  }
  function transform(v, pose) {
    const s=pose?.scale||[1,1,1],o=pose?.offset||[0,0,0];
    const p=rot([v[0]*s[0],v[1]*s[1],v[2]*s[2]],pose?.rotation);
    return [p[0]+o[0],p[1]+o[1],p[2]+o[2]];
  }
  function applyModelTransform(point, ops) {
    let p=point;
    // The saved extractor lists vanilla pose-stack operations in call order.
    // Vanilla vertices receive the LAST listed operation first.
    for(let i=(ops||[]).length-1;i>=0;i--){
      const op=ops[i];
      if(op.translate)p=p.map((v,j)=>v+op.translate[j]);
      if(op.scale)p=p.map((v,j)=>v*op.scale[j]);
      if(op.rotate)p=rot(p,op.rotate);
    }
    return p.map(v=>v*scale);
  }
  const sub=(a,b)=>[a[0]-b[0],a[1]-b[1],a[2]-b[2]];
  const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  function unit(v){const l=Math.hypot(...v)||1;return v.map(n=>n/l);}
  // Vanilla ModelPart.Cube texture net. Texture rectangles are specified in
  // pixel coordinates of the actual 64x32/64x64/etc mob PNG, not an atlas.
  function cubeFaces(box){
    const [x,y,z]=box.origin,[w,h,d]=box.size;
    const grow=box.grow||[0,0,0];
    const a=x-grow[0],b=y-grow[1],c=z-grow[2],e=x+w+grow[0],f=y+h+grow[1],g=z+d+grow[2];
    const P=[
      [a,b,c],[e,b,c],[e,f,c],[a,f,c],
      [a,b,g],[e,b,g],[e,f,g],[a,f,g]
    ];
    const [u,v]=box.uv||[0,0];
    const faces=[
      {ids:[0,1,2,3],uv:[u+d,v+d,w,h]},  // front
      {ids:[5,4,7,6],uv:[u+2*d+w,v+d,w,h]}, // back
      {ids:[4,0,3,7],uv:[u,v+d,d,h]},    // west
      {ids:[1,5,6,2],uv:[u+d+w,v+d,d,h]}, // east
      {ids:[4,5,1,0],uv:[u+d,v,w,d]},    // top
      {ids:[3,2,6,7],uv:[u+d+w,v,w,d]}   // bottom
    ];
    return faces.map(face=>({points:face.ids.map(i=>P[i]),uv:face.uv,mirror:!!box.mirror}));
  }
  function bakeLayer(entity,model,layerName,origin,tint){
    const layer=model.layers[layerName];
    if(!layer)return new Float32Array();
    const out=[];
    const texSize=layer.texture||[64,64];
    let color=[1,1,1];
    if(tint==='collar_color'){
      const n=Number(entity.collar);
      color=dye[Number.isInteger(n)&&n>=0&&n<dye.length?n:14];
    }
    const yaw=rad(Number(entity.yaw)||0);
    function world(raw){
      const normalized=applyModelTransform(raw,model.transform);
      const baby=entity.baby ? .55 : 1; // proportion fallback until baby-model mapping is available
      const x=normalized[0]*baby,z=normalized[2]*baby,y=normalized[1]*baby;
      const ca=Math.cos(yaw),sa=Math.sin(yaw);
      return [
        entity.pos[0]-origin[0]+x*ca-z*sa,
        entity.pos[1]-origin[1]+y,
        entity.pos[2]-origin[2]+x*sa+z*ca
      ];
    }
    function walk(part,parentTransforms,dimensions){
      const pose=part.pose||{};
      const transforms=parentTransforms.concat([pose]);
      const imageSize=part.texture||dimensions;
      for(const cube of part.cubes||[]){
        if(!cube.origin||!cube.size||!cube.uv)continue;
        const centreRaw=cube.origin.map((v,i)=>v+cube.size[i]/2);
        function toWorld(raw){
          let p=raw;
          for(let i=transforms.length-1;i>=0;i--)p=transform(p,transforms[i]);
          return world(p);
        }
        const cubeCentre=toWorld(centreRaw);
        for(const face of cubeFaces(cube)){
          const pts=face.points.map(toWorld);
          const faceCentre=[0,1,2].map(i=>
            (pts[0][i]+pts[1][i]+pts[2][i]+pts[3][i])/4);
          // UV face winding isn't guaranteed to be outward after the
          // vanilla model's mirror/negative scale. Centre-to-face normals
          // are outward even for nested rotations and mirrored model parts.
          const n=unit(sub(faceCentre,cubeCentre));
          const [u,v,uw,vh]=face.uv;
          // Pixel-edge inset avoids bleeding into adjacent skin regions.
          const eps=Math.min(.08,uw*.03,vh*.03);
          let tx1=(u+eps)/imageSize[0],tx2=(u+uw-eps)/imageSize[0];
          const ty1=(v+eps)/imageSize[1],ty2=(v+vh-eps)/imageSize[1];
          if(face.mirror)[tx1,tx2]=[tx2,tx1];
          const uvs=[[tx1,ty1],[tx2,ty1],[tx2,ty2],[tx1,ty2]];
          for(const idx of [0,1,2,0,2,3]){
            const p=pts[idx],uv=uvs[idx];
            out.push(...p,...n,...uv,...color,entity.type==='happy_ghast'?1:0);
          }
        }
      }
      for(const child of Object.values(part.children||{}))
        walk(child,transforms,imageSize);
    }
    walk(layer.root,[],texSize);
    return new Float32Array(out);
  }
  function create(entities,pack,origin){
    const result=[];
    if(!pack||pack.version!==1)return result;
    for(const entity of entities||[]){
      const model=pack.models?.[entity.type];
      if(!model||!entity.texture||!pack.textures?.[entity.texture])continue;
      result.push({texture:entity.texture,
        vertices:bakeLayer(entity,model,'main',origin)});
      for(const pass of entity.passes||[]){
        if(!pack.textures[pass.texture])continue;
        const passModel=pack.models?.[pass.model||entity.type];
        if(!passModel?.layers?.[pass.layer])continue;
        result.push({texture:pass.texture,
          vertices:bakeLayer(entity,passModel,pass.layer,origin,pass.tint)});
      }
    }
    return result.filter(entry=>entry.vertices.length>0);
  }
  window.MWW_ENTITY_MODELS={create};
})();
