// No Node packages or game assets: tests the browser-only geometry adapter.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const script=fs.readFileSync('web/entity-models.js','utf8');
const scope={window:{}};
vm.runInNewContext(script,scope);

function model(){
  return {id:'minecraft:cat',layers:{main:{
    texture:[64,32],root:{
      pose:{offset:[0,0,0],rotation:[0,0,0]},
      cubes:[{origin:[-4,0,-4],size:[8,8,8],uv:[0,0]}],
      children:{head:{pose:{offset:[2,4,0],rotation:[0,0,0]},
                      cubes:[{origin:[-2,0,-2],size:[4,4,4],uv:[32,0]}],
                      children:{}}}
    }
  }},transform:[{rotate:[0,Math.PI,0]},{scale:[-1,-1,1]},{translate:[0,-24,0]}]};
}
test('real vanilla model parts become texture-mapped triangles, not fake boxes',()=>{
  const entity={type:'cat',pos:[25,84,20],yaw:45,baby:false,
    texture:'minecraft:textures/entity/cat/cat_black.png'};
  const pack={version:1,models:{cat:model()},textures:{[entity.texture]:'PNG'}};
  const meshes=scope.window.MWW_ENTITY_MODELS.create([entity],pack,[20,80,18]);
  assert.equal(meshes.length,1);
  assert.equal(meshes[0].vertices.length,2*6*6*12);
  for(let i=0;i<meshes[0].vertices.length;i+=12){
    const v=meshes[0].vertices;
    for(let j=0;j<12;j++)assert.ok(Number.isFinite(v[i+j]));
    assert.ok(v[i+6]>=0&&v[i+6]<=1);
    assert.ok(v[i+7]>=0&&v[i+7]<=1);
  }
});
test('unknown skins do not create misleading fake animal geometry',()=>{
  const entity={type:'cat',pos:[0,0,0],texture:'missing.png'};
  assert.equal(scope.window.MWW_ENTITY_MODELS.create([entity],
    {version:1,models:{cat:model()},textures:{}},[0,0,0]).length,0);
});
