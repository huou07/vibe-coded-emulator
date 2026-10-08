const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');
const code = fs.readFileSync('static/renderer-worker.js','utf8');
const runtime = fs.readFileSync('static/player-runtime.js','utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
test('renderer choice persists, URL overrides storage, and denied storage remains usable',()=>{
  let stored='webgl2';const context={URLSearchParams,location:{search:''},localStorage:{getItem:()=>stored,setItem:(_,v)=>{stored=v}}};
  vm.runInNewContext(runtime,context);const api=context.AN3PlayerRuntime;
  assert.equal(api.queryRendererPreference(),'webgl2');
  assert.equal(api.saveRendererPreference('webgpu'),true);assert.equal(api.queryRendererPreference(),'webgpu');
  context.location.search='?renderer=auto';assert.equal(api.queryRendererPreference(),'auto');
  assert.equal(api.saveRendererPreference('invalid'),false);assert.equal(stored,'webgpu');
  context.localStorage.setItem=()=>{throw Error('denied')};assert.equal(api.saveRendererPreference('auto'),false);
  context.location.search='?renderer=webgl2';assert.equal(api.queryRendererPreference(),'webgl2');
});
test('copy diagnostics only includes safe scalars and never arbitrary errors or private data',()=>{
  const context={};vm.runInNewContext(runtime,context);
  const result=context.AN3PlayerRuntime.playerDiagnostics({system:'nds',core:'/private/core',renderer:{requested:'webgpu',effective:'webgl2',reason:'requestAdapter: https://secret.example/?token=PRIVATE',cookie:'PRIVATE',renderedFrames:42,presentationFps:60,offscreen:true},pacing:{coreSourceFps:0}});
  assert.equal(result.core,null);assert.equal(result.coreSourceFps,0);assert.equal(result.presentationFps,60);
  assert.equal(result.renderedFrames,42);assert.match(result.fallbackReason,/requestAdapter/);
  assert.doesNotMatch(JSON.stringify(result),/PRIVATE|secret|private|cookie/);
  assert.equal(result.renderP95Ms,null);
});
function glContext() {
  return new Proxy({}, {get: (_,key) => key === 'getShaderParameter' || key === 'getProgramParameter' ? () => true : () => ({})});
}
function gpuScope(failAt) {
  let usage = 0;
  const bad = stage => { if(failAt===stage) throw new Error('injected '+stage); };
  const texture = {createView:()=>({}),destroy(){}};
  const pass = {setPipeline(){},setBindGroup(){},draw(){},end(){}};
  const device = {
    pushErrorScope(){}, async popErrorScope(){return null}, addEventListener(){},lost:new Promise(()=>{}),destroy(){},
    createSampler:()=>({}),createShaderModule(){bad('shader');return {}},async createRenderPipelineAsync(){bad('pipeline');return {getBindGroupLayout:()=>({})}},
    createTexture(desc){usage=desc.usage;return texture},createBindGroup:()=>({}),
    createCommandEncoder:()=>({beginRenderPass:()=>pass,finish:()=>({})}),
    queue:{copyExternalImageToTexture(){assert.ok(usage & 16,'RenderAttachment required');bad('copy')},submit(){bad('submit')}},
  };
  return {navigator:{gpu:{async requestAdapter(){bad('adapter');return {async requestDevice(){bad('device');return device}}},getPreferredCanvasFormat:()=> 'bgra8unorm'}},device};
}
async function worker(failAt) {
  const messages=[];const scope=gpuScope(failAt);
  const canvas={width:8,height:8,getContext(type){if(type==='webgl2')return glContext();return {configure(){},unconfigure(){},getCurrentTexture:()=>({createView:()=>({})})}}};
  const self={navigator:scope.navigator,postMessage:m=>messages.push(m),close(){}};
  vm.runInNewContext(code,{self,performance,console});
  await self.onmessage({data:{type:'init',canvas,requested:'webgpu'}});
  return {self,messages};
}
test('WebGPU validates required copy texture usage and reports first frame stages',async()=>{
  const {self,messages}=await worker();let closed=0;
  await self.onmessage({data:{type:'frame',bitmap:{close(){closed++}},width:8,height:8,frameId:1}});await flush();
  const frame=messages.find(m=>m.type==='frame-result');assert.equal(frame.rendered,true);assert.equal(closed,1);
  assert.equal(typeof frame.renderP50Ms,'number');
  for(const stage of ['worker','OffscreenCanvas','requestAdapter','requestDevice','context','configure','shader','pipeline','texture','first bitmap','copyExternalImageToTexture','encoder','render pass','submit','first frame']) assert.ok(frame.stages.includes(stage),stage);
});
test('adapter rejection retains WebGL2 fallback and reason',async()=>{
  const {messages}=await worker('adapter');const ready=messages.find(m=>m.state==='ready');assert.equal(ready.effective,'webgl2');assert.match(ready.reason,/requestAdapter: injected adapter/);
});
test('pipeline error retains exact stage after context binding',async()=>{
  const {messages}=await worker('pipeline');const failed=messages.find(m=>m.state==='failed');assert.equal(failed.stage,'pipeline');assert.match(failed.reason,/injected pipeline/);
});
test('frame error is reported, never counted as rendered, and closes bitmap',async()=>{
  const {self,messages}=await worker('copy');let closed=0;
  await self.onmessage({data:{type:'frame',bitmap:{close(){closed++}},width:8,height:8,frameId:1}});await flush();
  assert.equal(messages.find(m=>m.type==='frame-result').rendered,false);assert.equal(closed,1);
  assert.equal(messages.find(m=>m.state==='failed').stage,'copyExternalImageToTexture');
});
function bridgeFixture(glFails=false) {
  const canvases=[];const scope=gpuScope();
  const source={width:8,height:8,style:{opacity:'1',position:'',zIndex:''}};
  const parent={appendChild(){}};
  const context={window:{navigator:scope.navigator},performance,console,setTimeout,clearTimeout,requestAnimationFrame:()=>1,cancelAnimationFrame(){},
    createImageBitmap:async()=>({close(){}}),
    document:{createElement(){const canvas={style:{},setAttribute(){},remove(){this.removed=true},getContext:()=>glFails?null:glContext(),transferControlToOffscreen(){this.transferred=true;return {}}};canvases.push(canvas);return canvas}},
    Worker:class {postMessage(msg){if(msg.type==='init')queueMicrotask(()=>this.onmessage({data:{type:'status',state:'failed',reason:'pipeline: test failure',stage:'pipeline'}}))}terminate(){}},
  };
  vm.runInNewContext(code,context);
  const bridge=new context.AN3WebRenderer.RendererBridge({requested:'webgpu',source,parent,workerUrl:'test.js'});
  return {bridge,canvases,source};
}
test('transferred worker failure retries reusable WebGL2 on fresh canvas',async()=>{
  const {bridge,canvases,source}=bridgeFixture();const status=await bridge.start();assert.equal(status.effective,'webgl2');assert.equal(canvases.length,2);assert.equal(canvases[0].removed,true);assert.equal(source.style.opacity,'1');assert.match(status.reason,/pipeline/);bridge.stop();
});
test('external fallback occurs only after fresh WebGL2 fails and restores source',async()=>{
  const {bridge,canvases,source}=bridgeFixture(true);const status=await bridge.start();assert.equal(status.effective,'external-core-canvas');assert.equal(canvases.length,2);assert.equal(source.style.opacity,'1');bridge.stop();
});
test('presentation metrics separate bitmap acquisition, rendering, rate, and backing size',async()=>{
  const {bridge}=bridgeFixture();
  bridge.target={width:300,height:150};
  bridge.active=true;
  bridge.backend={render:async()=>0.25};
  await bridge.captureLatestFrame();
  await bridge.captureLatestFrame();
  const status=bridge.snapshot();
  assert.equal(status.sourceWidth,8);assert.equal(status.sourceHeight,8);
  assert.equal(status.presentationWidth,8);assert.equal(status.presentationHeight,8);assert.equal(status.presentationPixels,64);
  assert.equal(status.renderP50Ms,0.25);assert.equal(typeof status.imageBitmapP50Ms,'number');assert.equal(typeof status.presentationFps,'number');
});
test('boot return and repeated frozen-canvas submissions never imply gameplay acceptance',()=>{
  const context={};vm.runInNewContext(runtime,context);const readiness=context.AN3PlayerRuntime.playbackReadiness;
  assert.equal(readiness().milestone,'starting');assert.equal(readiness({booted:true}).milestone,'core-started');
  const result=readiness({booted:true,renderer:{effective:'webgl2',renderedFrames:5000}});assert.equal(result.milestone,'video-submitted');assert.equal(result.gameplayVerified,false);
  assert.equal(readiness({booted:true,failed:true}).milestone,'failed');
});
test('core source rate comes from the independent core counter, not rAF count',()=>{
  let callback;const frames=[100,101,103];
  const context={requestAnimationFrame:next=>(callback=next,1),cancelAnimationFrame(){},PerformanceObserver:undefined};
  vm.runInNewContext(runtime,context);
  const monitor=new context.AN3PlayerRuntime.FramePacingMonitor({frameNumber:()=>frames.shift()});
  monitor.start();callback(1000);callback(1010);callback(1030);
  const snapshot=monitor.snapshot();
  assert.equal(snapshot.coreFrameNumber,103);assert.equal(snapshot.coreFrames,3);assert.equal(snapshot.coreSourceFps,100);
  assert.match(snapshot.coreFrameSource,/get_current_frame_count/);assert.equal(snapshot.coreCounterRegressions,0);
});
