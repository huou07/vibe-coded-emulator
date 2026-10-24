# SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
# SPDX-License-Identifier: GPL-3.0-or-later
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
        for label in (toolbar["menu"], toolbar["pad"], toolbar["layout"], toolbar["save"],
                      toolbar["quickSave"], toolbar["quickLoad"], toolbar["cursorLock"], *toolbar["speed"]):
            self.assertIn(label, native)
            self.assertIn(label, android)
            self.assertIn(label, web)

    def test_shared_auto_save_mode_parses_the_same_for_android_and_linux(self):
        model = json.loads((ROOT / "native-offline/shared/player-ui.json").read_text())["autoSave"]
        self.assertEqual(model["label"], "Auto Save")
        self.assertEqual(model["titles"], ["Off", "On game exit", "Every 30 seconds", "Every 10 seconds", "Every 5 seconds"])
        self.assertEqual(model["tokens"], ["off", "exit", "30", "10", "5"])
        native = (ROOT / "native-offline/shared/generated/player_ui.h").read_text()
        self.assertIn('auto_save_label = "Auto Save"', native)
        for title in model["titles"]:
            self.assertIn(json.dumps(title), native)
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "auto_save_mode.cpp"
            source_path.write_text(
                '#include "native-offline/native-runtime/core/auto_save_mode.h"\n'
                '#include <iostream>\n'
                'int main(){for(const char* v:{"off","exit","30","10","5","60","nope","0","3601",""}){'
                'auto s=an3::parse_auto_save_mode(v);'
                'if(!s){std::cout<<v<<" invalid\\n";continue;}'
                'std::cout<<v<<" "<<s->enabled<<" "<<s->on_exit<<" "<<s->interval<<"\\n";}}'
            )
            binary = Path(directory) / "auto_save_mode"
            subprocess.run(["c++", "-std=c++20", "-I", str(ROOT), str(source_path), "-o", str(binary)], check=True, capture_output=True)
            output = subprocess.check_output([str(binary)], text=True)
        parsed = {}
        for line in output.splitlines():
            value, _, result = line.partition(" ")
            parsed[value] = result
        self.assertEqual(parsed["off"], "0 0 60")
        self.assertEqual(parsed["exit"], "0 1 60")
        self.assertEqual(parsed["30"], "1 0 30")
        self.assertEqual(parsed["10"], "1 0 10")
        self.assertEqual(parsed["5"], "1 0 5")
        # A legacy numeric interval still enables periodic autosave.
        self.assertEqual(parsed["60"], "1 0 60")
        self.assertEqual(parsed[""], "0 0 60")
        for invalid in ("nope", "0", "3601"):
            self.assertEqual(parsed[invalid], "invalid")

    def test_macos_native_shell_uses_the_shared_auto_save_model(self):
        host = (ROOT / "native-offline/src-tauri/src/azahar_host.mm").read_text()
        # macOS must consume the same header and generated model as Android/Linux.
        self.assertIn('#include "../../native-runtime/core/auto_save_mode.h"', host)
        self.assertIn("an3::parse_auto_save_mode", host)
        self.assertIn("player_ui::auto_save_titles", host)
        self.assertIn("player_ui::auto_save_tokens", host)
        # The earlier boolean + interval keys stay readable for migration.
        self.assertIn("kNativeAutoSaveModeDefaultsKey", host)
        self.assertIn("kNativeAutoSaveDefaultsKey", host)
        # No private copy of the shared titles/tokens may remain.
        self.assertNotIn("native_auto_save_mode_titles", host)
        self.assertNotIn("native_auto_save_mode_tokens", host)
        for title in ('@"Off"', '@"On game exit"', '@"Every 30 seconds"', '@"Every 10 seconds"', '@"Every 5 seconds"'):
            self.assertNotIn(title, host)

    def test_shared_screen_layouts_are_generated_and_complete(self):
        schema = json.loads((ROOT / "native-offline/shared/native-layout-schema.json").read_text())
        self.assertEqual(schema["version"], 2)
        generated = (ROOT / "native-offline/shared/generated/native_layouts.h").read_text()
        for system in ("nds", "3ds"):
            entries = schema["systems"][system]
            # The point of the feature: more than the old two-option cycle.
            self.assertGreater(len(entries), 2, system)
            for item in entries:
                for value in (item["id"], item["label"], item["coreValue"]):
                    self.assertIn(value, generated)
        # Persisted ids keep their meaning after the list grew.
        self.assertEqual(schema["systems"]["nds"][0]["id"], "left-right")
        self.assertEqual(schema["systems"]["3ds"][0]["coreValue"], "side_by_side")
        self.assertEqual(schema["systems"]["3ds"][1]["coreValue"], "default")
        # macOS and Linux consume the generated header instead of a private copy.
        for path in ("native-offline/src-tauri/src/azahar_host.mm",
                     "native-offline/native-runtime/platform/linux/linux_controls.cpp"):
            source = (ROOT / path).read_text()
            self.assertIn("shared/generated/native_layouts.h", source)
            self.assertIn("native_layouts::nds", source)

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
