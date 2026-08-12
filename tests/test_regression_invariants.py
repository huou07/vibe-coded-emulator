import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PLAYER = (ROOT / "static/player.js").read_text(encoding="utf-8")
OFFLINE = (ROOT / "static/offline.js").read_text(encoding="utf-8")
SERVICE_WORKER = (ROOT / "static/service-worker.js").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")


class RegressionInvariantTests(unittest.TestCase):
    def test_nds_uses_melonds_auto_start_and_touch_bridge(self):
        self.assertIn('nds:"melonds"', PLAYER)
        self.assertIn("window.EJS_startOnLoaded = true", PLAYER)
        self.assertIn('retroarch_core:"melonds"', PLAYER)
        self.assertIn('window.EJS_disableLocalStorage = ndsPad', PLAYER)
        self.assertIn('canvas.classList.remove("ejs-canvas-no-pointer")', PLAYER)
        self.assertIn('setProperty("pointer-events","auto","important")', PLAYER)
        self.assertIn('setProperty("touch-action","none","important")', PLAYER)
        self.assertIn("new MutationObserver(protectNdsCanvas)", PLAYER)
        self.assertIn("dispatchNdsMouse", PLAYER)
        self.assertIn("getBoundingClientRect", PLAYER)
        self.assertIn('Object.defineProperty(event,name', PLAYER)
        self.assertIn('"offsetX"', PLAYER)
        self.assertIn('"offsetY"', PLAYER)
        self.assertIn('new URLSearchParams(location.search).get("touch")', PLAYER)
        self.assertIn('get("touch") || "geometry-mapped"', PLAYER)
        self.assertIn('["native","root","root-touch","overlay","hybrid-root","geometry-only","geometry-mapped"]', PLAYER)
        self.assertIn('elementFromPoint(event.clientX,event.clientY)', PLAYER)
        self.assertIn('gameRoot.setPointerCapture(event.pointerId)', PLAYER)
        self.assertIn('!["touch","touch-passive","pointer-touch","hybrid"].includes(touchVariant)', PLAYER)
        self.assertIn('event.touches||[]', PLAYER)
        self.assertIn('document.addEventListener("touchmove",move', PLAYER)
        self.assertIn('touchVariant === "touch-passive"', PLAYER)
        self.assertIn('touchVariant === "pointer-no-capture"', PLAYER)
        self.assertIn('["delta","geometry-only","geometry-mapped"].includes(touchVariant)', PLAYER)
        self.assertIn('touchVariant === "pointer-touch"', PLAYER)
        self.assertIn('["hybrid","hybrid-root","geometry-only","geometry-mapped"].includes(touchVariant)', PLAYER)
        self.assertIn('["root-touch","hybrid-root","geometry-only","geometry-mapped"].includes(touchVariant)', PLAYER)
        self.assertIn('const isolatedNdsMovement = ["geometry-only","geometry-mapped"].includes(touchVariant)', PLAYER)
        self.assertIn('"__an3NdsLastMousePoint"', PLAYER)
        self.assertIn('"__an3NdsLastPointerPoint"', PLAYER)
        self.assertIn('const pointKey=isolatedNdsMovement', PLAYER)
        self.assertIn('const mapNdsCursor =', PLAYER)
        self.assertIn('gl?.getParameter(gl.VIEWPORT)', PLAYER)
        self.assertIn('raw[0]+raw[2]<=backingWidth', PLAYER)
        self.assertIn('raw[1]+raw[3]<=backingHeight', PLAYER)
        self.assertIn('movementX=mapped.x-ndsMappedCursor.x', PLAYER)
        self.assertIn('movementY=mapped.y-ndsMappedCursor.y', PLAYER)
        self.assertIn('if (type === "mousedown") ndsViewportCache.delete(canvas)', PLAYER)
        hybrid_block = PLAYER[PLAYER.index('if (["hybrid","hybrid-root","geometry-only","geometry-mapped"]'):PLAYER.index('dispatchNdsMouse(canvas, type, source, buttons);', PLAYER.index('if (["hybrid","hybrid-root","geometry-only","geometry-mapped"]')) + len('dispatchNdsMouse(canvas, type, source, buttons);')]
        self.assertLess(hybrid_block.index("dispatchNdsPointer"), hybrid_block.index("dispatchNdsMouse"))
        self.assertIn('...(touchVariant === "core-touch" ? {melonds_touch_mode:"Touch"} : {})', PLAYER)
        self.assertNotIn('touchVariant === "geometry-mapped" ? {melonds_touch_mode', PLAYER)
        self.assertNotIn("desmume", PLAYER.lower())
        self.assertNotIn("startButtonClicked", PLAYER)
        self.assertIn('new URL(event.request.url).pathname', SERVICE_WORKER)
        self.assertIn('an3-arcade-pwa-v17', SERVICE_WORKER)

    def test_nds_debug_is_bounded_exportable_and_fail_closed(self):
        self.assertIn('NDS_DEBUG_ALLOWED = ENVIRONMENT in {"staging", "development"}', APP)
        self.assertIn('"ndsDebugAllowed": NDS_DEBUG_ALLOWED', APP)
        self.assertIn('config.ndsDebugAllowed === true && new URLSearchParams(location.search).get("ndsdebug") === "1"', PLAYER)
        self.assertIn('const NDS_DEBUG_LIMIT = 160', PLAYER)
        self.assertIn('ndsDebugEvents.splice(0,ndsDebugEvents.length-NDS_DEBUG_LIMIT)', PLAYER)
        self.assertIn('window.AN3NdsDebug=Object.freeze', PLAYER)
        self.assertIn('exportJSON', PLAYER)
        self.assertIn('{capture:true,passive:true}', PLAYER)
        debug_block = PLAYER[PLAYER.index("const NDS_DEBUG_LIMIT"):PLAYER.index("const dispatchNdsMouse")]
        self.assertNotIn("preventDefault", debug_block)
        self.assertNotIn("setPointerCapture", debug_block)
        self.assertNotIn("dispatchEvent", debug_block)
        self.assertNotIn("getComputedStyle", debug_block)
        self.assertIn("activeTouchIds", debug_block)
        self.assertIn("activePointerIds", debug_block)
        self.assertIn("!inside && !trackedTouch && !trackedPointer", debug_block)
        for field in (
            "eventType", "isTrusted", "pointerType", "clientX", "clientY", "pageX", "pageY",
            "target", "pointerCaptureOwner", "canvasRect", "canvasBackingWidth", "canvasBackingHeight",
            "canvasCssWidth", "canvasCssHeight", "devicePixelRatio", "mappedX", "mappedY",
            "normalizedX", "normalizedY", "movementX", "movementY", "orientation", "viewportOrientation",
            "screenOrientation", "fullscreen", "touchVariant", "activeCore", "configuredCore", "runtimeCore",
        ):
            self.assertIn(field, debug_block)

    def test_core_storage_is_emulatorjs_indexeddb_and_report_first(self):
        for source in (PLAYER, OFFLINE):
            self.assertIn('indexedDB.open("EmulatorJS-core",1)', source)
            self.assertIn('transaction("core"', source)
            self.assertIn('"?EJS_KEYS!"', source)
        self.assertIn("report?.options?.defaultWebGL2", PLAYER)
        self.assertIn("putCoreRecord(coreFile,coreData,report.buildStart)", PLAYER)
        self.assertIn("an3-arcade-cores-v1", PLAYER)
        self.assertIn('const CORE_CACHE = "an3-arcade-cores-v1"', SERVICE_WORKER)

    def test_nds_delivery_keeps_original_archive_and_range_support(self):
        self.assertIn('path.startswith("/game-file/") and game["system"] != "nds"', APP)
        self.assertIn('self.send_header("Accept-Ranges", "bytes")', APP)
        self.assertIn('self.send_header("Content-Range", f"bytes {start}-{end}/{size}")', APP)


if __name__ == "__main__":
    unittest.main(verbosity=2)
