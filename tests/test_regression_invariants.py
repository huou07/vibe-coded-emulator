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
        self.assertIn('["native","root","root-touch","overlay"]', PLAYER)
        self.assertIn('elementFromPoint(event.clientX,event.clientY)', PLAYER)
        self.assertIn('gameRoot.setPointerCapture(event.pointerId)', PLAYER)
        self.assertIn('!["touch","touch-passive","pointer-touch","hybrid"].includes(touchVariant)', PLAYER)
        self.assertIn('event.touches||[]', PLAYER)
        self.assertIn('document.addEventListener("touchmove",move', PLAYER)
        self.assertIn('touchVariant === "touch-passive"', PLAYER)
        self.assertIn('touchVariant === "pointer-no-capture"', PLAYER)
        self.assertIn('touchVariant === "delta"', PLAYER)
        self.assertIn('touchVariant === "pointer-touch"', PLAYER)
        self.assertIn('touchVariant === "hybrid"', PLAYER)
        self.assertIn('touchVariant === "root-touch"', PLAYER)
        self.assertNotIn("desmume", PLAYER.lower())
        self.assertNotIn("startButtonClicked", PLAYER)

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
