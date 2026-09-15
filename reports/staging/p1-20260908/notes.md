# P1 work notes
Baseline: intentional dirty tree preserved; no production actions permitted.
Blast radius: azahar_host.mm touches RG-001–014, RG-021–031, RG-039–042 and RG-046. Renderer/player touches RG-015–020, RG-026, RG-030, RG-032–038, RG-043–048. Baseline full Python, focused Node touch and native checks before edits; matching suites after. Runtime acceptance must remain separate from static tests.

## Proven findings
- Mounted baseline Show FPS saved=on; unsaved off, Escape, reopen=off (FAIL). Fixed mounted P1 DMG: Escape reopens on with Unsaved settings discarded and live FPS restored. Menu same PASS. Save off, Escape twice, NDS relaunch, Graphics off PASS; restored on and saved. Visible Golden Sun Dark Dawn title/intro observed. No save-state overwrite performed by test actions.
- Secure localhost synthetic baseline original renderer: black output despite 398 renderedFrames. Added diagnostic listener to work-only original copy: GPUValidationError message Destination texture needs to have CopyDst and RenderAttachment usage. Fixed source displays advancing test text via effective=webgpu/offscreen=true. This is a fixture, not gameplay acceptance.
- Isolated-page fixture with missing worker COEP reproduces worker-stage Render worker failed before GPU stages. Same fixture and worker bytes with matching require-corp header starts WebGPU and visibly renders test text. app.py serve_static now adds COEP only to the renderer worker (raw and versioned paths), preserving security restrictions. Secure staging baseline reproduces effective external-core-canvas, 0 frames, white source/FPS overlay with Playing.
- Device discovery: DEVICE_CONNECTED=no during P1. Prior owner Redmi tap/drag PASS preserved separately.
- All 93 Python tests pass after changes, including Node renderer behavior wrapper; direct Node touch plus renderer: 8 tests PASS. Syntax and git diff --check PASS.
