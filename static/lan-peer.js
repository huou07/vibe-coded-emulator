// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
(function () {
  "use strict";

  // This is the small, platform-neutral contract shared by installed AN3
  // clients. Native adapters implement the actual socket/discovery work; the
  // browser bundle only validates the records crossing that boundary.
  var VERSION = 1;
  var SERVICE = "an3-peer";
  var CAPABILITIES = Object.freeze(["sync", "controller"]);
  var DEVICE_ID = /^[A-Za-z0-9._-]{8,64}$/;
  var CAPABILITY = /^[a-z][a-z0-9-]{0,31}$/;
  var SENSITIVE = /^(?:account|email|token|accessToken|refreshToken|password|credential|secret|auth)$/i;

  var fail = function (message) { throw new Error(message); };

  var normalizeCapabilities = function (values) {
    if (!Array.isArray(values)) fail("LAN peer capabilities are missing.");
    var seen = new Set();
    var result = values.map(function (value) {
      var capability = String(value || "").trim();
      if (!CAPABILITY.test(capability) || seen.has(capability)) fail("LAN peer capabilities are invalid.");
      seen.add(capability);
      return capability;
    }).sort();
    return result;
  };

  // Discovery is deliberately a minimum-information record. The source
  // address comes from the local discovery socket, not from a broadcast field.
  var normalizeAdvertisement = function (record) {
    record = record && typeof record === "object" ? record : fail("LAN peer advertisement is invalid.");
    Object.keys(record).forEach(function (key) {
      if (SENSITIVE.test(key)) fail("LAN peer discovery cannot contain credentials or account data.");
    });
    if (String(record.service || "") !== SERVICE) fail("LAN peer service is incompatible.");
    if (Number(record.version) !== VERSION) fail("LAN peer protocol version is incompatible.");
    var deviceId = String(record.deviceId || record.id || "").trim();
    if (!DEVICE_ID.test(deviceId)) fail("LAN peer device identity is invalid.");
    var port = Number(record.port);
    if (!Number.isInteger(port) || port < 1 || port > 65535) fail("LAN peer endpoint is invalid.");
    var capabilities = normalizeCapabilities(record.capabilities);
    return Object.freeze({
      service: SERVICE,
      version: VERSION,
      deviceId: deviceId,
      port: port,
      capabilities: capabilities,
      name: String(record.name || "AN3 device").trim().slice(0, 64),
    });
  };

  var validateHandshake = function (hello, requiredCapability) {
    var peer = normalizeAdvertisement(hello);
    var capability = String(requiredCapability || "").trim();
    if (!CAPABILITY.test(capability) || !peer.capabilities.includes(capability)) {
      fail("LAN peer does not advertise the requested capability.");
    }
    return peer;
  };

  var requiredMethods = ["manifest", "plan", "publish", "blob", "resolve"];
  var asSyncTransport = function (transport) {
    if (!transport || typeof transport !== "object") fail("A direct LAN peer transport is required.");
    requiredMethods.forEach(function (method) {
      if (typeof transport[method] !== "function") fail("The LAN peer transport is missing " + method + ".");
    });
    return Object.freeze({
      manifest: transport.manifest.bind(transport),
      plan: transport.plan.bind(transport),
      publish: transport.publish.bind(transport),
      blob: transport.blob.bind(transport),
      resolve: transport.resolve.bind(transport),
      sameAccount: typeof transport.sameAccount === "function"
        ? transport.sameAccount.bind(transport)
        : async function () { return false; },
      development: transport.development === true,
      discover: typeof transport.discover === "function" ? transport.discover.bind(transport) : async function () { return []; },
      close: typeof transport.close === "function" ? transport.close.bind(transport) : async function () {},
    });
  };

  var setTransport = function (transport) {
    globalThis.AN3LanPeerTransport = asSyncTransport(transport);
    return globalThis.AN3LanPeerTransport;
  };

  globalThis.AN3LanPeer = Object.freeze({
    version: VERSION,
    service: SERVICE,
    capabilities: CAPABILITIES,
    normalizeAdvertisement: normalizeAdvertisement,
    validateHandshake: validateHandshake,
    asSyncTransport: asSyncTransport,
    setTransport: setTransport,
  });
})();
