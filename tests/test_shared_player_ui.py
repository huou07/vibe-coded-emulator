"""Behavior at the shared circular input / pinned EmulatorJS ABI boundary."""
import json
import math
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SharedPlayerUiTests(unittest.TestCase):
    def test_generated_native_and_web_models_do_not_drift(self):
        subprocess.run(["node", "native-offline/scripts/generate-player-ui.mjs", "--check"], cwd=ROOT, check=True, capture_output=True)

    def test_toolbar_contract_is_generated_for_native_and_web_adapters(self):
        model = json.loads((ROOT / "native-offline/shared/player-ui.json").read_text())
        toolbar = model["toolbar"]
        self.assertEqual(toolbar["speed"], ["0.5x", "1x", "x2"])
        native = (ROOT / "native-offline/shared/generated/player_ui.h").read_text()
        android = (ROOT / "native-offline/src-tauri/gen/android/app/src/main/java/space/an3tocom/offline/NativePlayerUi.kt").read_text()
        web = (ROOT / "static/player-ui.js").read_text()
        for label in (toolbar["menu"], toolbar["pad"], toolbar["nextLayout"], toolbar["cursorLock"], *toolbar["speed"]):
            self.assertIn(label, native)
            self.assertIn(label, android)
            self.assertIn(label, web)

    def test_circle_normalization_matches_cpp_and_keeps_thumb_inside_base(self):
        vectors = [[0, 0], [.1, .1], [1, 0], [0, -1], [1, 1], [-4, 3], [.3, -.4]]
        js = "const ui=require('./static/player-ui.js');console.log(JSON.stringify(" + json.dumps(vectors) + ".map(([x,y])=>ui.normalize(x,y))));"
        actual = json.loads(subprocess.check_output(["node", "-e", js], cwd=ROOT, text=True))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/"stick.cpp"
            source.write_text('#include "native-offline/shared/generated/player_ui.h"\n#include <iostream>\n#include <iomanip>\nint main(){double x,y;while(std::cin>>x>>y){auto a=an3::player_ui::normalize(x,y);std::cout<<std::setprecision(17)<<a.x<<" "<<a.y<<"\\n";}}')
            binary = Path(directory)/"stick"
            subprocess.run(["c++", "-std=c++20", "-I", str(ROOT), str(source), "-o", str(binary)], check=True, capture_output=True)
            cpp = subprocess.check_output([str(binary)], input="\n".join(f"{x} {y}" for x,y in vectors), text=True)
        native = [list(map(float,line.split())) for line in cpp.splitlines()]
        model = json.loads((ROOT/"native-offline/shared/player-ui.json").read_text())["joystick"]
        for value, (x,y) in zip(actual,native):
            self.assertAlmostEqual(value["x"],x)
            self.assertAlmostEqual(value["y"],y)
            self.assertLessEqual(math.hypot(x,y)*model["travelRatio"] + model["thumbRadiusRatio"], 1)
        self.assertEqual(actual[0], {"x":0,"y":0})
        self.assertEqual(actual[1], {"x":0,"y":0})
        self.assertEqual(actual[2], {"x":1,"y":0})
        self.assertAlmostEqual(actual[4]["x"], math.sqrt(.5))

    def test_emulator_half_axes_use_analog_range_and_release_opposite_direction(self):
        script = r'''
require('./static/player-runtime.js');
const state={};
const input=new globalThis.AN3PlayerRuntime.InputRouter({manager:()=>({simulateInput:(port,key,value)=>{state[key]=value;}})});
const samples=[];
for(const [x,y] of [[1,-.5],[-1,.25],[0,0],[NaN,Infinity]]) {input.setVirtualAxis(x,y);samples.push({...state});}
console.log(JSON.stringify(samples));
'''
        samples = json.loads(subprocess.check_output(["node", "-e", script], cwd=ROOT, text=True))
        self.assertEqual(samples[0], {"16":32767,"17":0,"18":0,"19":16384})
        self.assertEqual(samples[1], {"16":0,"17":32767,"18":8192,"19":0})
        self.assertEqual(samples[2], {"16":0,"17":0,"18":0,"19":0})
        self.assertEqual(samples[3], samples[2])


if __name__ == "__main__":
    unittest.main()
