// Generated from native-offline/shared/input-actions-schema.json; edit the shared model.
(function (root, factory) {
  const model = factory();
  if (typeof module === "object" && module.exports) module.exports = model;
  else root.AN3InputActions = model;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const model = {
  "version": 1,
  "buttons": {
    "B": {
      "wire": "b",
      "libretro": 0,
      "label": "B"
    },
    "Y": {
      "wire": "y",
      "libretro": 1,
      "label": "Y"
    },
    "SELECT": {
      "wire": "select",
      "libretro": 2,
      "label": "Select"
    },
    "START": {
      "wire": "start",
      "libretro": 3,
      "label": "Start"
    },
    "UP": {
      "wire": "up",
      "libretro": 4,
      "label": "Up"
    },
    "DOWN": {
      "wire": "down",
      "libretro": 5,
      "label": "Down"
    },
    "LEFT": {
      "wire": "left",
      "libretro": 6,
      "label": "Left"
    },
    "RIGHT": {
      "wire": "right",
      "libretro": 7,
      "label": "Right"
    },
    "A": {
      "wire": "a",
      "libretro": 8,
      "label": "A"
    },
    "X": {
      "wire": "x",
      "libretro": 9,
      "label": "X"
    },
    "L": {
      "wire": "l",
      "libretro": 10,
      "label": "L"
    },
    "R": {
      "wire": "r",
      "libretro": 11,
      "label": "R"
    }
  },
  "utility": {
    "QUICK_SAVE": {
      "wire": "quick_save",
      "label": "Quick Save"
    },
    "QUICK_LOAD": {
      "wire": "quick_load",
      "label": "Quick Load"
    },
    "SPEED_UP": {
      "wire": "speed_up",
      "label": "Speed Up"
    },
    "SPEED_DOWN": {
      "wire": "speed_down",
      "label": "Speed Down"
    },
    "OPEN_MENU": {
      "wire": "open_menu",
      "label": "Menu"
    }
  },
  "directionalControls": [
    {
      "id": "dpad",
      "label": "D-Pad"
    },
    {
      "id": "joystick",
      "label": "Analog Joystick"
    },
    {
      "id": "circular",
      "label": "Circular D-pad"
    }
  ],
  "speeds": [
    "0.5",
    "1",
    "2",
    "4",
    "8"
  ],
  "circular": {
    "deadzone": 0.3,
    "hysteresisDegrees": 6,
    "sectors": [
      {
        "id": "E",
        "center": 0,
        "actions": [
          "RIGHT"
        ]
      },
      {
        "id": "NE",
        "center": 45,
        "actions": [
          "UP",
          "RIGHT"
        ]
      },
      {
        "id": "N",
        "center": 90,
        "actions": [
          "UP"
        ]
      },
      {
        "id": "NW",
        "center": 135,
        "actions": [
          "UP",
          "LEFT"
        ]
      },
      {
        "id": "W",
        "center": 180,
        "actions": [
          "LEFT"
        ]
      },
      {
        "id": "SW",
        "center": 225,
        "actions": [
          "DOWN",
          "LEFT"
        ]
      },
      {
        "id": "S",
        "center": 270,
        "actions": [
          "DOWN"
        ]
      },
      {
        "id": "SE",
        "center": 315,
        "actions": [
          "DOWN",
          "RIGHT"
        ]
      }
    ]
  }
};
  const sectors = model.circular.sectors;
  const deadzone = model.circular.deadzone;
  const hysteresis = model.circular.hysteresisDegrees;
  const sectorIds = sectors.map((sector) => sector.id);
  const sectorCenters = sectors.map((sector) => sector.center);
  const sectorActions = sectors.map((sector) => sector.actions.slice());

  model.buttonActions = Object.keys(model.buttons);
  model.wireToId = {};
  model.idToWire = {};
  for (const [action, button] of Object.entries(model.buttons)) {
    model.wireToId[button.wire] = button.libretro;
    model.idToWire[button.libretro] = button.wire;
  }
  model.utilityActions = Object.keys(model.utility);
  model.utilityWireToAction = {};
  for (const [action, entry] of Object.entries(model.utility)) model.utilityWireToAction[entry.wire] = action;

  // Directional geometry for a pointer normalized so one radius is 1.0.
  model.circularDirections = function (dx, dy, previous) {
    if (!Number.isFinite(dx) || !Number.isFinite(dy)) return {actions: [], region: null};
    if (Math.hypot(dx, dy) < deadzone) return {actions: [], region: null};
    let angle = Math.atan2(-dy, dx) * 180 / Math.PI;
    if (angle < 0) angle += 360;
    if (previous) {
      const index = sectorIds.indexOf(previous);
      if (index >= 0) {
        let distance = Math.abs(angle - sectorCenters[index]);
        if (distance > 180) distance = 360 - distance;
        if (distance <= 22.5 + hysteresis) return {actions: sectorActions[index].slice(), region: sectorIds[index]};
      }
    }
    let best = 0;
    let bestDistance = Infinity;
    for (let index = 0; index < sectorIds.length; index += 1) {
      let distance = Math.abs(angle - sectorCenters[index]);
      if (distance > 180) distance = 360 - distance;
      if (distance < bestDistance) { bestDistance = distance; best = index; }
    }
    return {actions: sectorActions[best].slice(), region: sectorIds[best]};
  };

  return model;
});
