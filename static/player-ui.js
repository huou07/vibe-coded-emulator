// Generated from native-offline/shared/player-ui.json; edit the shared model.
(function(root) {
  const model = {"version":1,"reference":"VibeCodedEmulator macOS 1.0.0 native player","tabs":["General","Graphics","Audio","Keyboard","Controller","Emulation","Save States","Diagnostics","About"],"panel":{"maxWidth":820,"maxHeight":620,"edge":12},"joystick":{"diameter":108,"thumbRadiusRatio":0.3,"travelRatio":0.6111111111111112,"deadzone":0.15},"colors":{"control":"#b8141414","border":"#80ffffff","thumb":"#d9ffffff","text":"#ffffffff"},"toolbar":{"menu":"Menu","pad":"Pad","layout":"Layout","save":"Save","quickSave":"Quick Save","quickLoad":"Quick Load","cursorLock":"Lock cursor","speed":["0.5x","1x","x2"]},"autoSave":{"label":"Auto Save","titles":["Off","On game exit","Every 30 seconds","Every 10 seconds","Every 5 seconds"],"tokens":["off","exit","30","10","5"]}};
  function normalize(x, y) {
    if (!Number.isFinite(x) || !Number.isFinite(y)) return {x:0,y:0};
    const length = Math.hypot(x,y);
    if (length < model.joystick.deadzone) return {x:0,y:0};
    const scale = Math.max(1,length);
    return {x:x/scale,y:y/scale};
  }
  const api = Object.freeze({model, normalize});
  if (typeof module === "object" && module.exports) module.exports = api;
  root.AN3PlayerUI = api;
})(typeof globalThis === "object" ? globalThis : this);
