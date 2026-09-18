// Generated from native-offline/shared/native-settings-schema.json; edit the shared model.
(function (root, factory) {
  const model = factory();
  if (typeof module === "object" && module.exports) module.exports = model;
  else root.NativeSettingsModel = model;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const schema = {
  "version": 1,
  "store": "an3-native-game",
  "systems": [
    "gba",
    "nds",
    "3ds",
    "switch"
  ],
  "systemLabels": {
    "gba": "GBA",
    "nds": "NDS",
    "3ds": "3DS",
    "switch": "Switch"
  },
  "renderer": {
    "id": "renderer",
    "label": "Renderer",
    "category": "graphics",
    "type": "enum",
    "storage": "string",
    "values": [
      "auto",
      "vulkan",
      "opengl"
    ],
    "labels": {
      "auto": "Auto",
      "vulkan": "Vulkan",
      "opengl": "OpenGL ES"
    },
    "min": null,
    "max": null,
    "default": "auto",
    "legacyKeys": [
      "renderer"
    ],
    "legacyResolve": null,
    "restart": "renderer",
    "note": "Applies on the next launch. Auto picks the stable backend for each system.",
    "external": true
  },
  "global": [
    {
      "id": "volume",
      "label": "Volume",
      "category": "audio",
      "type": "int",
      "storage": "int",
      "values": [],
      "labels": {},
      "min": 0,
      "max": 100,
      "default": "100",
      "legacyKeys": [],
      "legacyResolve": null,
      "restart": "none",
      "note": null,
      "external": true
    },
    {
      "id": "mute",
      "label": "Mute",
      "category": "audio",
      "type": "bool",
      "storage": "bool",
      "values": [],
      "labels": {},
      "min": null,
      "max": null,
      "default": "false",
      "legacyKeys": [],
      "legacyResolve": null,
      "restart": "none",
      "note": null,
      "external": true
    },
    {
      "id": "latency",
      "label": "Audio latency",
      "category": "audio",
      "type": "enum",
      "storage": "int",
      "values": [
        "32",
        "64",
        "96",
        "128"
      ],
      "labels": {
        "32": "32 ms",
        "64": "64 ms",
        "96": "96 ms",
        "128": "128 ms"
      },
      "min": null,
      "max": null,
      "default": "64",
      "legacyKeys": [],
      "legacyResolve": null,
      "restart": "none",
      "note": null,
      "external": true
    },
    {
      "id": "quality",
      "label": "Resampler quality",
      "category": "audio",
      "type": "enum",
      "storage": "string",
      "values": [
        "low",
        "medium",
        "high"
      ],
      "labels": {
        "low": "Low",
        "medium": "Medium",
        "high": "High"
      },
      "min": null,
      "max": null,
      "default": "medium",
      "legacyKeys": [],
      "legacyResolve": null,
      "restart": "none",
      "note": null,
      "external": true
    },
    {
      "id": "autosave-mode",
      "label": "Auto Save",
      "category": "emulation",
      "type": "enum",
      "storage": "string",
      "values": [
        "off",
        "exit",
        "30",
        "10",
        "5"
      ],
      "labels": {
        "5": "Every 5 seconds",
        "10": "Every 10 seconds",
        "30": "Every 30 seconds",
        "off": "Off",
        "exit": "On game exit"
      },
      "min": null,
      "max": null,
      "default": null,
      "legacyKeys": [],
      "legacyResolve": "native-autosave",
      "restart": "none",
      "note": null,
      "external": true
    },
    {
      "id": "show-fps",
      "label": "Show FPS",
      "category": "display",
      "type": "bool",
      "storage": "bool",
      "values": [],
      "labels": {},
      "min": null,
      "max": null,
      "default": "false",
      "legacyKeys": [],
      "legacyResolve": null,
      "restart": "none",
      "note": null,
      "external": true
    },
    {
      "id": "start-fullscreen",
      "label": "Start fullscreen on launch",
      "category": "display",
      "type": "bool",
      "storage": "bool",
      "values": [],
      "labels": {},
      "min": null,
      "max": null,
      "default": "true",
      "legacyKeys": [],
      "legacyResolve": null,
      "restart": "app",
      "note": null,
      "external": true
    },
    {
      "id": "key-map",
      "label": "Keyboard map",
      "category": "controls",
      "type": "string",
      "storage": "string",
      "values": [],
      "labels": {},
      "min": null,
      "max": null,
      "default": "{}",
      "legacyKeys": [],
      "legacyResolve": null,
      "restart": "none",
      "note": null,
      "external": false
    },
    {
      "id": "controller-server",
      "label": "Controller server",
      "category": "network",
      "type": "string",
      "storage": "string",
      "values": [],
      "labels": {},
      "min": null,
      "max": null,
      "default": "",
      "legacyKeys": [],
      "legacyResolve": null,
      "restart": "none",
      "note": null,
      "external": false
    }
  ],
  "graphics": {
    "gba": [
      {
        "id": "renderer",
        "label": "Renderer",
        "category": "graphics",
        "type": "enum",
        "storage": "string",
        "values": [
          "auto",
          "vulkan",
          "opengl"
        ],
        "labels": {
          "auto": "Auto",
          "vulkan": "Vulkan",
          "opengl": "OpenGL ES"
        },
        "min": null,
        "max": null,
        "default": "auto",
        "legacyKeys": [
          "renderer"
        ],
        "legacyResolve": null,
        "restart": "renderer",
        "note": "Applies on the next launch. Auto picks the stable backend for each system.",
        "external": true
      }
    ],
    "nds": [
      {
        "id": "renderer",
        "label": "Renderer",
        "category": "graphics",
        "type": "enum",
        "storage": "string",
        "values": [
          "auto",
          "vulkan",
          "opengl"
        ],
        "labels": {
          "auto": "Auto",
          "vulkan": "Vulkan",
          "opengl": "OpenGL ES"
        },
        "min": null,
        "max": null,
        "default": "auto",
        "legacyKeys": [
          "renderer"
        ],
        "legacyResolve": null,
        "restart": "renderer",
        "note": "Applies on the next launch. Auto picks the stable backend for each system.",
        "external": true
      },
      {
        "id": "screen-layout",
        "label": "Screen layout",
        "category": "graphics",
        "type": "enum",
        "storage": "string",
        "values": [
          "left-right",
          "right-left",
          "top-bottom",
          "bottom-top",
          "hybrid-top",
          "hybrid-bottom",
          "flipped-hybrid-top",
          "flipped-hybrid-bottom",
          "largescreen-top",
          "largescreen-bottom",
          "flipped-largescreen-top",
          "flipped-largescreen-bottom"
        ],
        "labels": {
          "left-right": "Left / Right",
          "right-left": "Right / Left",
          "top-bottom": "Top / Bottom",
          "bottom-top": "Bottom / Top",
          "hybrid-top": "Hybrid (focus top)",
          "hybrid-bottom": "Hybrid (focus bottom)",
          "flipped-hybrid-top": "Flipped hybrid (focus top)",
          "flipped-hybrid-bottom": "Flipped hybrid (focus bottom)",
          "largescreen-top": "Large screen (top)",
          "largescreen-bottom": "Large screen (bottom)",
          "flipped-largescreen-top": "Flipped large screen (top)",
          "flipped-largescreen-bottom": "Flipped large screen (bottom)"
        },
        "min": null,
        "max": null,
        "default": "left-right",
        "legacyKeys": [
          "screen-layout-nds",
          "nds-layout"
        ],
        "legacyResolve": null,
        "restart": "game",
        "note": "Applies immediately in-game and on the next launch outside the game.",
        "external": true
      }
    ],
    "3ds": [
      {
        "id": "renderer",
        "label": "Renderer",
        "category": "graphics",
        "type": "enum",
        "storage": "string",
        "values": [
          "auto",
          "vulkan",
          "opengl"
        ],
        "labels": {
          "auto": "Auto",
          "vulkan": "Vulkan",
          "opengl": "OpenGL ES"
        },
        "min": null,
        "max": null,
        "default": "auto",
        "legacyKeys": [
          "renderer"
        ],
        "legacyResolve": null,
        "restart": "renderer",
        "note": "Applies on the next launch. Auto picks the stable backend for each system.",
        "external": true
      },
      {
        "id": "screen-layout",
        "label": "Screen layout",
        "category": "graphics",
        "type": "enum",
        "storage": "string",
        "values": [
          "left-right",
          "top-bottom",
          "single-screen",
          "large-screen"
        ],
        "labels": {
          "left-right": "Side by Side",
          "top-bottom": "Top / Bottom",
          "single-screen": "Single Screen",
          "large-screen": "Large Screen"
        },
        "min": null,
        "max": null,
        "default": "left-right",
        "legacyKeys": [
          "screen-layout-3ds",
          "nds-layout"
        ],
        "legacyResolve": null,
        "restart": "game",
        "note": "Applies immediately in-game and on the next launch outside the game.",
        "external": true
      }
    ],
    "switch": [
      {
        "id": "renderer",
        "label": "Renderer",
        "category": "graphics",
        "type": "enum",
        "storage": "string",
        "values": [
          "auto",
          "vulkan",
          "opengl"
        ],
        "labels": {
          "auto": "Auto",
          "vulkan": "Vulkan",
          "opengl": "OpenGL ES"
        },
        "min": null,
        "max": null,
        "default": "auto",
        "legacyKeys": [
          "renderer"
        ],
        "legacyResolve": null,
        "restart": "renderer",
        "note": "Applies on the next launch. Auto picks the stable backend for each system.",
        "external": true
      }
    ]
  },
  "emulation": {
    "gba": [],
    "nds": [],
    "3ds": [],
    "switch": []
  },
  "availability": {
    "switch": {
      "android": "Nintendo Switch is not supported on Android. Settings are stored but cannot launch here.",
      "ios": "Nintendo Switch is not supported on iOS."
    }
  },
  "pinnedCoreOptions": {
    "gba": [],
    "nds": [
      "melonds_render_mode",
      "melonds_screen_layout1",
      "melonds_number_of_screen_layouts",
      "melonds_touch_mode"
    ],
    "3ds": [
      "citra_graphics_api",
      "citra_use_hw_shader",
      "citra_use_disk_shader_cache",
      "citra_layout_option"
    ],
    "switch": []
  }
};

  const platform = (ua) => {
    const text = String(ua || (typeof navigator !== "undefined" ? navigator.userAgent : "") || "");
    if (/Android/i.test(text)) return "android";
    if (/iPhone|iPad|iPod/i.test(text)) return "ios";
    return "desktop";
  };

  const key = (id, system) => (system == null ? id : id + "-" + system);

  const definitionsFor = (system) => [...(schema.graphics[system] || []), ...(schema.emulation[system] || [])];

  const externalGlobal = () => schema.global.filter((definition) => definition.external);

  const valuesOf = (definition) => definition.values || [];

  const labelOf = (definition, value) => (definition.labels && definition.labels[value]) || value;

  const validate = (definition, value) => {
    if (value == null) return { ok: false, reason: "Missing value" };
    if (definition.type === "bool") {
      const normal = String(value).toLowerCase();
      if (normal === "true" || normal === "false") return { ok: true, value: normal };
      return { ok: false, reason: "Expected true or false" };
    }
    if (definition.type === "int") {
      const number = Number(value);
      if (!Number.isInteger(number) || number < definition.min || number > definition.max) return { ok: false, reason: "Expected an integer between " + definition.min + " and " + definition.max };
      return { ok: true, value: String(number) };
    }
    if (definition.type === "enum") {
      const text = String(value);
      if (!valuesOf(definition).includes(text)) return { ok: false, reason: "Unsupported value" };
      return { ok: true, value: text };
    }
    return { ok: true, value: String(value) };
  };

  const coerce = (definition, value) => {
    const result = validate(definition, value);
    if (result.ok) return result.value;
    return definition.default != null ? definition.default : (valuesOf(definition)[0] != null ? valuesOf(definition)[0] : "");
  };

  // Stored per-system value, then the documented legacy fallback, then default.
  const effective = (definition, system, stored, legacy) => {
    const own = stored ? stored[key(definition.id, system)] : undefined;
    const ownCheck = validate(definition, own);
    if (ownCheck.ok) return ownCheck.value;
    for (const legacyKey of definition.legacyKeys || []) {
      const candidate = legacy ? legacy[legacyKey] : undefined;
      const legacyCheck = validate(definition, candidate);
      if (legacyCheck.ok) return legacyCheck.value;
    }
    return definition.default;
  };

  const buildEdit = (definition, system, value) => {
    const result = validate(definition, value);
    if (!result.ok) return null;
    return { key: key(definition.id, system), value: result.value };
  };

  const resetGraphicsEdits = (system, defaultValue) => {
    const edits = {};
    for (const definition of schema.graphics[system] || []) {
      const value = defaultValue ? defaultValue(definition, system) : definition.default;
      edits[key(definition.id, system)] = coerce(definition, value);
    }
    return edits;
  };

  const isAvailable = (system, currentPlatform) => !(schema.availability[system] && schema.availability[system][currentPlatform || platform()]);

  const unavailableReason = (system, currentPlatform) => {
    const entry = schema.availability[system];
    return entry ? (entry[currentPlatform || platform()] || null) : null;
  };

  return {
    version: schema.version,
    store: schema.store,
    systems: schema.systems,
    systemLabels: schema.systemLabels,
    renderer: schema.renderer,
    global: schema.global,
    graphics: schema.graphics,
    emulation: schema.emulation,
    pinnedCoreOptions: schema.pinnedCoreOptions,
    platform,
    key,
    definitionsFor,
    externalGlobal,
    valuesOf,
    labelOf,
    validate,
    coerce,
    effective,
    buildEdit,
    resetGraphicsEdits,
    isAvailable,
    unavailableReason,
  };
});
