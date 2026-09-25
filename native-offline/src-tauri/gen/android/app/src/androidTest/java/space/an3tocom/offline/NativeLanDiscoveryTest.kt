// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
package space.an3tocom.offline

import android.view.View
import android.view.ViewGroup
import android.webkit.WebView
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.isAssignableFrom
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.web.sugar.Web.onWebView
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.filters.LargeTest
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import java.security.MessageDigest
import java.util.Base64
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.json.JSONObject
import org.json.JSONTokener
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Exercises real Android native multicast discovery against the live LAN. */
@RunWith(AndroidJUnit4::class)
@LargeTest
class NativeLanDiscoveryTest {

    private val keepAppOpen: Boolean = InstrumentationRegistry.getArguments()
        .getString("keepAppOpen") == "true"
    private val directSyncTarget: String = InstrumentationRegistry.getArguments()
        .getString("directSyncTarget")
        .orEmpty()
        .also { target ->
            require(target.isEmpty() || Regex("^direct:[0-9.]+:[0-9]{1,5}$").matches(target)) {
                "directSyncTarget must be a private IPv4 debug endpoint"
            }
        }
    private val directSyncCode: String = InstrumentationRegistry.getArguments()
        .getString("directSyncCode")
        .orEmpty()
        .also { code ->
            require(code.isEmpty() || Regex("^[0-9]{6}$").matches(code)) {
                "directSyncCode must be six decimal digits"
            }
        }

    @Test
    fun discoversMacSyncAdvertisementOnTheLan() {
        val scenario = ActivityScenario.launch(MainActivity::class.java)
        try {
            awaitWebView()
            onWebView().forceJavascriptEnabled()
            awaitNativeSync(scenario)

            val initiation = evalJson(
                scenario,
                """(function(){
                    window.__an3LanDiscoveryProbe = {done:false, peers:[]};
                    var api = window.AN3NativeSync;
                    if (!api || typeof api.discover !== "function") {
                      window.__an3LanDiscoveryProbe = {
                        done:true,
                        error:"native Sync discovery API unavailable",
                        peers:[]
                      };
                      return JSON.stringify({available:false});
                    }
                    try {
                      var request = api.discover();
                      if (!request || typeof request.then !== "function") {
                        window.__an3LanDiscoveryProbe = {
                          done:true,
                          error:"native discovery did not return a Promise",
                          peers:[]
                        };
                      } else {
                        request.then(function(peers){
                          window.__an3LanDiscoveryProbe = {
                            done:true,
                            error:"",
                            peers:(peers || []).map(function(peer){
                              return {
                                port:Number(peer.port),
                                sync:Array.isArray(peer.capabilities) && peer.capabilities.indexOf("sync") >= 0
                              };
                            })
                          };
                        }).catch(function(error){
                          window.__an3LanDiscoveryProbe = {
                            done:true,
                            error:String(error && error.message || error),
                            peers:[]
                          };
                        });
                      }
                      return JSON.stringify({available:true});
                    } catch (error) {
                      window.__an3LanDiscoveryProbe = {
                        done:true,
                        error:String(error && error.message || error),
                        peers:[]
                      };
                      return JSON.stringify({available:true, threw:true});
                    }
                })()""",
            )
            assertTrue("native Sync discovery API is not available", initiation.optBoolean("available"))

            val deadline = System.currentTimeMillis() + 12_000
            var probe = JSONObject()
            while (System.currentTimeMillis() < deadline) {
                probe = evalJson(
                    scenario,
                    "JSON.stringify(window.__an3LanDiscoveryProbe || {done:false,peers:[]})",
                )
                if (probe.optBoolean("done")) break
                Thread.sleep(200)
            }
            assertTrue("native LAN discovery did not complete", probe.optBoolean("done"))
            assertTrue("native LAN discovery returned an error", probe.optString("error").isEmpty())

            val peers = probe.optJSONArray("peers")
            val foundMacSyncPeer = peers != null && (0 until peers.length()).any { index ->
                val peer = peers.optJSONObject(index)
                peer?.optInt("port") == 47833 && peer.optBoolean("sync")
            }
            assertTrue("the phone did not discover the live Mac Sync advertisement", foundMacSyncPeer)
        } finally {
            if (!keepAppOpen) scenario.close()
        }
    }

    @Test
    fun reconnectsAndReadsAuthenticatedManifestForSharedFixture() {
        val scenario = ActivityScenario.launch(MainActivity::class.java)
        try {
            awaitWebView()
            onWebView().forceJavascriptEnabled()
            awaitNativeSync(scenario)

            val initiation = evalJson(
                scenario,
                """(function(){
                    window.__an3RememberedPeerProbe = {
                      done:false, stage:"init", remembered:0, connected:0, pingOk:false,
                      advertisedPeerCount:0, rememberedPeerAdvertised:false,
                      localFixtureCount:0, localManifestItemCount:0, localGbaItemCount:0,
                      remoteFixtureCount:0, sameFixtureContent:false,
                      localFixtureSystem:"", localFixtureSize:0,
                      remoteSystemMatchCount:0, remoteSizeMatchCount:0, matchingRemoteFixtureCount:0,
                      conflictProtected:false, conflictPlanCount:0, remoteSaveIntegrityCount:0,
                      localStateCount:0, remoteStateCount:0, verifiedRemoteStateCount:0,
                      sameStateContents:false, safeStateTransfer:false,
                      statePlanReadCount:0, stateConflictCount:0, stateUploadCount:0,
                      stateDownloadCount:0, stateNoopCount:0,
                      localSaveCount:0, remoteSaveCount:0, sameSaveContents:false, safeSaveTransfer:false,
                      localSaveMarker:false, localSaveCounter:-1, remoteSaveMarker:false, remoteSaveCounter:-1,
                      saveUploadCount:0, saveConflictCount:0, destinationSaveCount:0, verifiedSaveTransfer:false,
                      states:[], reconnectErrors:0, runtimeError:false, failureCategory:""
                    };
                    var stage = "init";
                    (async function(){
                      try {
                        stage = "sync-init";
                        var api = window.AN3NativeSync;
                        var initial = await api.init();
                        var remembered = (initial.peers || []).filter(function(peer){ return Boolean(peer.deviceId); });
                        stage = "discover";
                        var advertisements = await api.discover();
                        var rememberedPeerAdvertised = remembered.some(function(rememberedPeer){
                          return (advertisements || []).some(function(advertisedPeer){
                            return advertisedPeer.deviceId === rememberedPeer.deviceId;
                          });
                        });
                        window.__an3RememberedPeerProbe.remembered = remembered.length;
                        window.__an3RememberedPeerProbe.advertisedPeerCount = (advertisements || []).length;
                        window.__an3RememberedPeerProbe.rememberedPeerAdvertised = rememberedPeerAdvertised;
                        window.__an3RememberedPeerProbe.states = (initial.peers || []).map(function(peer){ return String(peer.state || "unknown"); });
                        var reconnectErrors = 0;
                        if (!remembered.length) {
                          window.__an3RememberedPeerProbe = {
                            done:true, remembered:0, connected:0, pingOk:false,
                            advertisedPeerCount:(advertisements || []).length, rememberedPeerAdvertised:false,
                            localFixtureCount:0, localManifestItemCount:0, localGbaItemCount:0,
                            remoteFixtureCount:0, sameFixtureContent:false,
                            localFixtureSystem:"", localFixtureSize:0,
                            remoteSystemMatchCount:0, remoteSizeMatchCount:0, matchingRemoteFixtureCount:0,
                            conflictProtected:false, conflictPlanCount:0, remoteSaveIntegrityCount:0,
                            localStateCount:0, remoteStateCount:0, verifiedRemoteStateCount:0,
                            sameStateContents:false, safeStateTransfer:false,
                            statePlanReadCount:0, stateConflictCount:0, stateUploadCount:0,
                            stateDownloadCount:0, stateNoopCount:0,
                            localSaveCount:0, remoteSaveCount:0, sameSaveContents:false, safeSaveTransfer:false,
                            localSaveMarker:false, localSaveCounter:-1, remoteSaveMarker:false, remoteSaveCounter:-1,
                            saveUploadCount:0, saveConflictCount:0, destinationSaveCount:0, verifiedSaveTransfer:false,
                            states:[], reconnectErrors:0, runtimeError:Boolean(initial.error), failureCategory:"no-peer"
                          };
                          return;
                        }
                        if (!rememberedPeerAdvertised) {
                          window.__an3RememberedPeerProbe.done = true;
                          window.__an3RememberedPeerProbe.stage = stage;
                          window.__an3RememberedPeerProbe.failureCategory = "advertisement-mismatch";
                          return;
                        }
                        stage = "reconnect";
                        await Promise.all(remembered.map(function(peer){
                          return peer.state === "connected" ? Promise.resolve() : api.reconnect(peer.deviceId).catch(function(){ reconnectErrors += 1; });
                        }));
                        var deadline = Date.now() + 18_000;
                        while (Date.now() < deadline) {
                          stage = "status";
                          var current = await api.status();
                          var connected = (current.peers || []).filter(function(peer){ return peer.state === "connected"; }).length;
                          window.__an3RememberedPeerProbe = {
                            done:false,
                            stage:stage,
                            remembered:(current.peers || []).length,
                            connected:connected,
                            advertisedPeerCount:(advertisements || []).length,
                            rememberedPeerAdvertised:rememberedPeerAdvertised,
                            pingOk:false,
                            states:(current.peers || []).map(function(peer){ return String(peer.state || "unknown"); }),
                            reconnectErrors:reconnectErrors,
                            runtimeError:Boolean(current.error),
                            failureCategory:""
                          };
                          if (connected > 0) {
                            stage = "authenticated-ping";
                            var ping = await api.request("ping", {});
                            var pingOk = Boolean(ping && ping.ok === true && typeof ping.peerId === "string" && ping.peerId.length > 0);
                            window.__an3RememberedPeerProbe.connected = connected;
                            window.__an3RememberedPeerProbe.pingOk = pingOk;
                            var fixtureHash = "28ce2a0220d178e4f79b8ae93a0a0aa1316e442f5979edfbeb837af7fa0d61bc";
                            var invoke = window.AN3NativeInvoke && window.AN3NativeInvoke();
                            if (typeof invoke !== "function") throw new Error("native invoke bridge unavailable");
                            stage = "local-library-manifest";
                            var localManifest = await invoke("native_sync_library_manifest", {});
                            var localItems = localManifest.items || [];
                            var localFixture = localItems.filter(function(item){
                              return String(item.contentHash || "").toLowerCase() === fixtureHash;
                            });
                            window.__an3RememberedPeerProbe.localManifestItemCount = localItems.length;
                            window.__an3RememberedPeerProbe.localGbaItemCount = localItems.filter(function(item){ return item.system === "gba"; }).length;
                            window.__an3RememberedPeerProbe.localFixtureCount = localFixture.length;
                            stage = "remote-library-manifest";
                            var remoteManifest = await api.request("library-manifest", {});
                            var remoteFixture = (remoteManifest.items || []).filter(function(item){
                              return String(item.contentHash || "").toLowerCase() === fixtureHash;
                            });
                            window.__an3RememberedPeerProbe.remoteFixtureCount = remoteFixture.length;
                            var sameFixtureContent = false;
                            var localCandidate = null;
                            stage = "local-game-identity-and-save-read";
                            for (var index = 0; index < localFixture.length; index += 1) {
                              var candidate = localFixture[index];
                              var identity = await api.gameIdentity("gba", candidate.romId);
                              var records = await api.storage("save", "gba", candidate.romId, identity).readAll();
                              localCandidate = {item:candidate, identity:identity, records:records};
                              if (records.length) break;
                            }
                            if (!localCandidate) throw new Error("fixture game identity unavailable");
                            var matchingRemoteFixtures = remoteFixture.filter(function(remoteItem){
                              return remoteItem.system === localCandidate.item.system
                                && Number(remoteItem.size) === Number(localCandidate.item.size)
                                && String(remoteItem.contentHash || "").toLowerCase() === String(localCandidate.item.contentHash || "").toLowerCase();
                            });
                            sameFixtureContent = matchingRemoteFixtures.length > 0;
                            window.__an3RememberedPeerProbe.sameFixtureContent = sameFixtureContent;
                            var remoteSystemMatchCount = remoteFixture.filter(function(remoteItem){
                              return remoteItem.system === localCandidate.item.system;
                            }).length;
                            var remoteSizeMatchCount = remoteFixture.filter(function(remoteItem){
                              return Number(remoteItem.size) === Number(localCandidate.item.size);
                            }).length;
                            window.__an3RememberedPeerProbe.localFixtureSystem = String(localCandidate.item.system || "");
                            window.__an3RememberedPeerProbe.localFixtureSize = Number(localCandidate.item.size) || 0;
                            window.__an3RememberedPeerProbe.remoteSystemMatchCount = remoteSystemMatchCount;
                            window.__an3RememberedPeerProbe.remoteSizeMatchCount = remoteSizeMatchCount;
                            window.__an3RememberedPeerProbe.matchingRemoteFixtureCount = matchingRemoteFixtures.length;
                            var hashBytes = async function(bytes) {
                              var digest = new Uint8Array(await window.crypto.subtle.digest("SHA-256", bytes));
                              return Array.from(digest).map(function(byte){ return byte.toString(16).padStart(2, "0"); }).join("");
                            };
                            stage = "local-state-preflight";
                            var localStateRecords = await api.storage("state", "gba", localCandidate.item.romId, localCandidate.identity).readAll();
                            var localStateDetails = await Promise.all(localStateRecords.map(async function(record){
                              var value = record.state;
                              var bytes = value && typeof value.arrayBuffer === "function"
                                ? new Uint8Array(await value.arrayBuffer())
                                : value instanceof Uint8Array ? value : new Uint8Array(value || []);
                              return {
                                key:String(record.key || record.id || ""),
                                size:bytes.byteLength,
                                hash:await hashBytes(bytes),
                                modifiedAt:Number(record.updatedAt) || 0
                              };
                            }));
                            var remoteStateTargets = [];
                            var remoteStateManifests = [];
                            for (var stateIndex = 0; stateIndex < matchingRemoteFixtures.length; stateIndex += 1) {
                              stage = "remote-state-manifest-" + (stateIndex + 1);
                              var stateRom = matchingRemoteFixtures[stateIndex];
                              var stateContext = {
                                system:"gba",
                                romId:stateRom.romId,
                                identity:{system:"gba", core:"mgba", gameId:localCandidate.identity.gameId, romHash:localCandidate.identity.romHash}
                              };
                              var stateManifest = await api.transport.manifest("state", stateContext);
                              remoteStateManifests.push({context:stateContext, manifest:stateManifest});
                              (stateManifest.items || []).forEach(function(item){
                                remoteStateTargets.push({context:stateContext, item:item, detail:{
                                  key:String(item.key || ""),
                                  size:Number(item.size),
                                  hash:String(item.contentHash || "").toLowerCase()
                                }});
                              });
                            }
                            stage = "remote-state-integrity-readback";
                            var verifiedRemoteStateCount = 0;
                            var remoteStateDetails = remoteStateTargets.map(function(target){ return target.detail; });
                            for (var remoteStateIndex = 0; remoteStateIndex < remoteStateTargets.length; remoteStateIndex += 1) {
                              var stateTarget = remoteStateTargets[remoteStateIndex];
                              var stateBytes = await api.transport.blob("state", stateTarget.item, stateTarget.context);
                              if (stateBytes.byteLength === stateTarget.detail.size
                                  && await hashBytes(stateBytes) === stateTarget.detail.hash) {
                                verifiedRemoteStateCount += 1;
                              }
                            }
                            var sameStateContents = localStateDetails.length > 0 && remoteStateDetails.length > 0
                              && remoteStateDetails.every(function(remote){
                                return localStateDetails.some(function(local){
                                  return remote.key === local.key && remote.size === local.size && remote.hash === local.hash;
                                });
                              });
                            var safeStateTransfer = localStateDetails.length === 0 || remoteStateDetails.length === 0 || sameStateContents;
                            stage = "remote-state-plan";
                            var statePlanReadCount = 0;
                            var stateConflictCount = 0;
                            var stateUploadCount = 0;
                            var stateDownloadCount = 0;
                            var stateNoopCount = 0;
                            var localStateByKey = new Map(localStateDetails.map(function(item){ return [item.key, item]; }));
                            var localStateDeviceId = globalThis.AN3SyncTransfer.deviceId();
                            for (var planIndex = 0; planIndex < remoteStateManifests.length; planIndex += 1) {
                              var planManifest = remoteStateManifests[planIndex].manifest;
                              var remotePlanItems = planManifest.items || [];
                              var remoteStateByKey = new Map(remotePlanItems.map(function(item){ return [String(item.key || ""), item]; }));
                              var stateKeys = Array.from(new Set(Array.from(localStateByKey.keys()).concat(Array.from(remoteStateByKey.keys())))).sort();
                              var stateRecords = stateKeys.map(function(key){
                                var localItem = localStateByKey.get(key);
                                var remoteItem = remoteStateByKey.get(key);
                                return {
                                  key:key,
                                  local:localItem ? {content_hash:localItem.hash, size:localItem.size, modified_at:localItem.modifiedAt, device_id:localStateDeviceId} : undefined,
                                  remote:remoteItem ? {content_hash:String(remoteItem.contentHash || "").toLowerCase(), size:Number(remoteItem.size), device_id:String(remoteItem.deviceId || "")} : undefined
                                };
                              });
                              var statePlan = await api.transport.plan({mode:"lan", sameLan:true, kind:"state", records:stateRecords});
                              statePlanReadCount += 1;
                              (statePlan.transfers || []).forEach(function(transfer){
                                if (transfer.direction === "conflict") stateConflictCount += 1;
                                else if (transfer.direction === "upload") stateUploadCount += 1;
                                else if (transfer.direction === "download") stateDownloadCount += 1;
                                else if (transfer.direction === "none") stateNoopCount += 1;
                              });
                            }
                            window.__an3RememberedPeerProbe.localStateCount = localStateDetails.length;
                            window.__an3RememberedPeerProbe.remoteStateCount = remoteStateDetails.length;
                            window.__an3RememberedPeerProbe.verifiedRemoteStateCount = verifiedRemoteStateCount;
                            window.__an3RememberedPeerProbe.sameStateContents = sameStateContents;
                            window.__an3RememberedPeerProbe.safeStateTransfer = safeStateTransfer;
                            window.__an3RememberedPeerProbe.statePlanReadCount = statePlanReadCount;
                            window.__an3RememberedPeerProbe.stateConflictCount = stateConflictCount;
                            window.__an3RememberedPeerProbe.stateUploadCount = stateUploadCount;
                            window.__an3RememberedPeerProbe.stateDownloadCount = stateDownloadCount;
                            window.__an3RememberedPeerProbe.stateNoopCount = stateNoopCount;
                            var localSaveDetails = await Promise.all(localCandidate.records.map(async function(record){
                              var bytes = record.bytes instanceof Uint8Array ? record.bytes : new Uint8Array(record.bytes || []);
                              return {
                                key:String(record.key || record.id || ""),
                                size:bytes.byteLength,
                                hash:await hashBytes(bytes),
                                marker:bytes.length >= 4 && String.fromCharCode.apply(null, Array.from(bytes.slice(0, 4))) === "AN3B",
                                counter:bytes.length > 4 ? bytes[4] : -1
                              };
                            }));
                            window.__an3RememberedPeerProbe.localSaveCount = localSaveDetails.length;
                            window.__an3RememberedPeerProbe.localSaveMarker = Boolean(localSaveDetails[0] && localSaveDetails[0].marker);
                            window.__an3RememberedPeerProbe.localSaveCounter = localSaveDetails[0] ? localSaveDetails[0].counter : -1;
                            var remoteSaveSets = [];
                            var collectRemoteSaveTargets = async function() {
                              var targets = [];
                              remoteSaveSets = [];
                              for (var remoteIndex = 0; remoteIndex < matchingRemoteFixtures.length; remoteIndex += 1) {
                                stage = "remote-save-manifest-" + (remoteIndex + 1);
                                var remoteItem = matchingRemoteFixtures[remoteIndex];
                                var remoteContext = {
                                  system:"gba",
                                  romId:remoteItem.romId,
                                  identity:{system:"gba", core:"mgba", gameId:localCandidate.identity.gameId, romHash:localCandidate.identity.romHash}
                                };
                                var manifest = await api.transport.manifest("save", remoteContext);
                                var sets = (manifest.sets || []).filter(function(set){
                                  return set.gameId === localCandidate.identity.gameId && set.romHash === localCandidate.identity.romHash;
                                });
                                sets.forEach(function(set){
                                  remoteSaveSets.push({context:remoteContext, set:set});
                                  (set.members || []).forEach(function(member){
                                    targets.push({context:remoteContext, member:member, detail:{
                                      key:String(member.key || ""),
                                      size:Number(member.size),
                                      hash:String(member.contentHash || "").toLowerCase()
                                    }});
                                  });
                                });
                              }
                              return targets;
                            };
                            stage = "fixture-content-preflight";
                            if (!sameFixtureContent) throw new Error("fixture content identity precondition failed");
                            stage = "remote-save-preflight";
                            var remoteSaveTargets = await collectRemoteSaveTargets();
                            var remoteSaveDetails = remoteSaveTargets.map(function(target){ return target.detail; });
                            var sameSaveContents = localSaveDetails.length > 0 && remoteSaveDetails.length > 0
                              && remoteSaveDetails.every(function(remote){
                                return localSaveDetails.some(function(local){
                                  return remote.key === local.key && remote.size === local.size && remote.hash === local.hash;
                                });
                              });
                            stage = "remote-save-integrity-readback";
                            var remoteSaveIntegrityCount = 0;
                            for (var targetIndex = 0; targetIndex < remoteSaveTargets.length; targetIndex += 1) {
                              var target = remoteSaveTargets[targetIndex];
                              var remoteBytes = await api.transport.blob("save", target.member, target.context);
                              if (remoteBytes.byteLength === target.detail.size
                                  && await hashBytes(remoteBytes) === target.detail.hash) {
                                remoteSaveIntegrityCount += 1;
                              }
                            }
                            var safeSaveTransfer = localSaveDetails.length === 0 || remoteSaveDetails.length === 0 || sameSaveContents;
                            window.__an3RememberedPeerProbe.localSaveCount = localSaveDetails.length;
                            window.__an3RememberedPeerProbe.remoteSaveCount = remoteSaveDetails.length;
                            window.__an3RememberedPeerProbe.sameSaveContents = sameSaveContents;
                            window.__an3RememberedPeerProbe.safeSaveTransfer = safeSaveTransfer;
                            window.__an3RememberedPeerProbe.remoteSaveIntegrityCount = remoteSaveIntegrityCount;
                            window.__an3RememberedPeerProbe.localSaveMarker = Boolean(localSaveDetails[0] && localSaveDetails[0].marker);
                            window.__an3RememberedPeerProbe.localSaveCounter = localSaveDetails[0] ? localSaveDetails[0].counter : -1;
                            window.__an3RememberedPeerProbe.remoteSaveMarker = false;
                            window.__an3RememberedPeerProbe.remoteSaveCounter = -1;
                            if (!localSaveDetails.length) {
                              throw new Error("fixture save source is unavailable");
                            }
                            if (!safeSaveTransfer) {
                              stage = "conflict-engine-plan";
                              var localSet = await globalThis.AN3SyncTransfer.buildSaveSet(localCandidate.identity, localCandidate.records);
                              var divergentSets = remoteSaveSets.filter(function(entry){
                                return entry.set.manifestHash !== localSet.manifestHash;
                              });
                              var conflictPlanCount = 0;
                              var noWritePlanCount = 0;
                              var unchangedRemoteSetCount = 0;
                              var writeAttempts = 0;
                              var selectedEntry = null;
                              var guardedTransport = {
                                development:false,
                                sameAccount:function(context){ return api.transport.sameAccount(context); },
                                manifest:function(){ return Promise.resolve({items:[],sets:selectedEntry ? [selectedEntry.set] : []}); },
                                plan:function(payload){ return api.transport.plan(payload); },
                                publish:function(){ writeAttempts += 1; throw new Error("physical conflict test blocked a write"); },
                                blob:function(kind, item, context){ return api.transport.blob(kind, item, context); },
                                resolve:function(payload){ return api.transport.resolve(payload); }
                              };
                              var sourceStorage = api.storage("save", "gba", localCandidate.item.romId, localCandidate.identity);
                              var guardedStorage = {
                                readAll:function(){ return sourceStorage.readAll(); },
                                put:function(){ writeAttempts += 1; throw new Error("physical conflict test blocked a local write"); },
                                putSet:function(){ writeAttempts += 1; throw new Error("physical conflict test blocked a local write"); }
                              };
                              for (var conflictIndex = 0; conflictIndex < divergentSets.length; conflictIndex += 1) {
                                selectedEntry = divergentSets[conflictIndex];
                                var result = await globalThis.AN3SyncTransfer.syncSave({
                                  mode:"lan",
                                  sameLan:true,
                                  transport:guardedTransport,
                                  storage:guardedStorage,
                                  identity:localCandidate.identity,
                                  deviceId:globalThis.AN3SyncTransfer.deviceId(),
                                  context:{kind:"save", system:"gba", romId:selectedEntry.context.romId, identity:localCandidate.identity}
                                });
                                if (Number(result.counts.conflicts || 0) === 1) conflictPlanCount += 1;
                                if (Number(result.counts.uploaded || 0) === 0 && Number(result.counts.downloaded || 0) === 0) noWritePlanCount += 1;
                                var afterManifest = await api.transport.manifest("save", selectedEntry.context);
                                var afterSet = (afterManifest.sets || []).find(function(set){ return set.setId === selectedEntry.set.setId; });
                                if (afterSet && afterSet.manifestHash === selectedEntry.set.manifestHash) unchangedRemoteSetCount += 1;
                              }
                              var conflictProtected = divergentSets.length > 0
                                && conflictPlanCount === divergentSets.length
                                && noWritePlanCount === divergentSets.length
                                && unchangedRemoteSetCount === divergentSets.length
                                && remoteSaveIntegrityCount === remoteSaveDetails.length
                                && writeAttempts === 0;
                              if (!conflictProtected) throw new Error("the live save conflict was not safely planned");
                              window.__an3RememberedPeerProbe.done = true;
                              window.__an3RememberedPeerProbe.stage = "conflict-protected-no-write";
                              window.__an3RememberedPeerProbe.conflictProtected = true;
                              window.__an3RememberedPeerProbe.conflictPlanCount = conflictPlanCount;
                              window.__an3RememberedPeerProbe.remoteSaveIntegrityCount = remoteSaveIntegrityCount;
                              window.__an3RememberedPeerProbe.saveConflictCount = conflictPlanCount;
                              window.__an3RememberedPeerProbe.saveUploadCount = 0;
                              window.__an3RememberedPeerProbe.saveDownloadCount = 0;
                              window.__an3RememberedPeerProbe.failureCategory = "";
                              return;
                            }
                            var saveTransfer = {counts:{uploaded:0, conflicts:0}};
                            if (remoteSaveDetails.length === 0) {
                              stage = "authenticated-save-upload";
                              saveTransfer = await api.syncGame("gba", localCandidate.item.romId, "save");
                            }
                            stage = "remote-save-readback";
                            var destinationTargets = await collectRemoteSaveTargets();
                            var destinationTarget = destinationTargets.find(function(target){
                              return localSaveDetails.some(function(local){
                                return target.detail.key === local.key && target.detail.size === local.size && target.detail.hash === local.hash;
                              });
                            });
                            var destinationDetails = destinationTargets.map(function(target){ return target.detail; });
                            var destinationBytes = destinationTarget
                              ? await api.transport.blob("save", destinationTarget.member, destinationTarget.context)
                              : new Uint8Array();
                            var destinationHash = destinationBytes.length ? await hashBytes(destinationBytes) : "";
                            var destinationMarker = destinationBytes.length >= 4
                              && String.fromCharCode.apply(null, Array.from(destinationBytes.slice(0, 4))) === "AN3B";
                            var destinationCounter = destinationBytes.length > 4 ? destinationBytes[4] : -1;
                            var verifiedSaveTransfer = Number(saveTransfer?.counts?.conflicts || 0) === 0
                              && Boolean(destinationTarget)
                              && destinationHash === localSaveDetails[0].hash
                              && destinationMarker === localSaveDetails[0].marker
                              && destinationCounter === localSaveDetails[0].counter;
                            window.__an3RememberedPeerProbe = {
                              done:true,
                              stage:"complete",
                              remembered:(current.peers || []).length,
                              connected:connected,
                              advertisedPeerCount:(advertisements || []).length,
                              rememberedPeerAdvertised:rememberedPeerAdvertised,
                              pingOk:pingOk,
                              localFixtureCount:localFixture.length,
                              localManifestItemCount:localItems.length,
                              localGbaItemCount:localItems.filter(function(item){ return item.system === "gba"; }).length,
                              remoteFixtureCount:remoteFixture.length,
                              sameFixtureContent:sameFixtureContent,
                              conflictProtected:false,
                              conflictPlanCount:0,
                              remoteSaveIntegrityCount:remoteSaveIntegrityCount,
                              localStateCount:localStateDetails.length,
                              remoteStateCount:remoteStateDetails.length,
                              verifiedRemoteStateCount:verifiedRemoteStateCount,
                              sameStateContents:sameStateContents,
                              safeStateTransfer:safeStateTransfer,
                              statePlanReadCount:statePlanReadCount,
                              stateConflictCount:stateConflictCount,
                              stateUploadCount:stateUploadCount,
                              stateDownloadCount:stateDownloadCount,
                              stateNoopCount:stateNoopCount,
                              localSaveCount:localSaveDetails.length,
                              remoteSaveCount:remoteSaveDetails.length,
                              sameSaveContents:sameSaveContents,
                              safeSaveTransfer:safeSaveTransfer,
                              localSaveMarker:Boolean(localSaveDetails[0] && localSaveDetails[0].marker),
                              localSaveCounter:localSaveDetails[0] ? localSaveDetails[0].counter : -1,
                              remoteSaveMarker:destinationMarker,
                              remoteSaveCounter:destinationCounter,
                              saveUploadCount:Number(saveTransfer?.counts?.uploaded || 0),
                              saveConflictCount:Number(saveTransfer?.counts?.conflicts || 0),
                              destinationSaveCount:destinationDetails.length,
                              verifiedSaveTransfer:verifiedSaveTransfer,
                              states:(current.peers || []).map(function(peer){ return String(peer.state || "unknown"); }),
                              reconnectErrors:reconnectErrors,
                              runtimeError:Boolean(current.error),
                              failureCategory:""
                            };
                            return;
                          }
                          await new Promise(function(resolve){ setTimeout(resolve, 300); });
                        }
                        window.__an3RememberedPeerProbe.done = true;
                        window.__an3RememberedPeerProbe.failureCategory = "timeout";
                      } catch (error) {
                        var message = String(error && error.message || error);
                        var failureCategory = /trust|pair|auth|code/i.test(message) ? "auth"
                          : /connect|network|socket|timeout|unavailable/i.test(message) ? "network" : "native";
                        window.__an3RememberedPeerProbe = {
                          done:true,
                          stage:stage,
                          remembered:window.__an3RememberedPeerProbe.remembered || 0,
                          connected:window.__an3RememberedPeerProbe.connected || 0,
                          advertisedPeerCount:window.__an3RememberedPeerProbe.advertisedPeerCount || 0,
                          rememberedPeerAdvertised:window.__an3RememberedPeerProbe.rememberedPeerAdvertised || false,
                          pingOk:window.__an3RememberedPeerProbe.pingOk || false,
                          localFixtureCount:window.__an3RememberedPeerProbe.localFixtureCount || 0,
                          localManifestItemCount:window.__an3RememberedPeerProbe.localManifestItemCount || 0,
                          localGbaItemCount:window.__an3RememberedPeerProbe.localGbaItemCount || 0,
                          remoteFixtureCount:window.__an3RememberedPeerProbe.remoteFixtureCount || 0,
                          sameFixtureContent:window.__an3RememberedPeerProbe.sameFixtureContent || false,
                          conflictProtected:window.__an3RememberedPeerProbe.conflictProtected || false,
                          conflictPlanCount:window.__an3RememberedPeerProbe.conflictPlanCount || 0,
                          remoteSaveIntegrityCount:window.__an3RememberedPeerProbe.remoteSaveIntegrityCount || 0,
                          localStateCount:window.__an3RememberedPeerProbe.localStateCount || 0,
                          remoteStateCount:window.__an3RememberedPeerProbe.remoteStateCount || 0,
                          verifiedRemoteStateCount:window.__an3RememberedPeerProbe.verifiedRemoteStateCount || 0,
                          sameStateContents:window.__an3RememberedPeerProbe.sameStateContents || false,
                          safeStateTransfer:window.__an3RememberedPeerProbe.safeStateTransfer || false,
                          statePlanReadCount:window.__an3RememberedPeerProbe.statePlanReadCount || 0,
                          stateConflictCount:window.__an3RememberedPeerProbe.stateConflictCount || 0,
                          stateUploadCount:window.__an3RememberedPeerProbe.stateUploadCount || 0,
                          stateDownloadCount:window.__an3RememberedPeerProbe.stateDownloadCount || 0,
                          stateNoopCount:window.__an3RememberedPeerProbe.stateNoopCount || 0,
                          localFixtureSystem:window.__an3RememberedPeerProbe.localFixtureSystem || "",
                          localFixtureSize:window.__an3RememberedPeerProbe.localFixtureSize || 0,
                          remoteSystemMatchCount:window.__an3RememberedPeerProbe.remoteSystemMatchCount || 0,
                          remoteSizeMatchCount:window.__an3RememberedPeerProbe.remoteSizeMatchCount || 0,
                          matchingRemoteFixtureCount:window.__an3RememberedPeerProbe.matchingRemoteFixtureCount || 0,
                          localSaveCount:window.__an3RememberedPeerProbe.localSaveCount || 0,
                          remoteSaveCount:window.__an3RememberedPeerProbe.remoteSaveCount || 0,
                          sameSaveContents:window.__an3RememberedPeerProbe.sameSaveContents || false,
                          safeSaveTransfer:window.__an3RememberedPeerProbe.safeSaveTransfer || false,
                          localSaveMarker:window.__an3RememberedPeerProbe.localSaveMarker || false,
                          localSaveCounter:window.__an3RememberedPeerProbe.localSaveCounter ?? -1,
                          remoteSaveMarker:window.__an3RememberedPeerProbe.remoteSaveMarker || false,
                          remoteSaveCounter:window.__an3RememberedPeerProbe.remoteSaveCounter ?? -1,
                          saveUploadCount:window.__an3RememberedPeerProbe.saveUploadCount || 0,
                          saveConflictCount:window.__an3RememberedPeerProbe.saveConflictCount || 0,
                          destinationSaveCount:window.__an3RememberedPeerProbe.destinationSaveCount || 0,
                          verifiedSaveTransfer:window.__an3RememberedPeerProbe.verifiedSaveTransfer || false,
                          states:window.__an3RememberedPeerProbe.states || [],
                          reconnectErrors:window.__an3RememberedPeerProbe.reconnectErrors || 0,
                          runtimeError:window.__an3RememberedPeerProbe.runtimeError || false,
                          failureCategory:failureCategory
                        };
                      }
                    })();
                    return JSON.stringify({started:true});
                })()""",
            )
            assertTrue("stored-trust reconnect probe did not start", initiation.optBoolean("started"))

            val deadline = System.currentTimeMillis() + 24_000
            var probe = JSONObject()
            while (System.currentTimeMillis() < deadline) {
                probe = evalJson(
                    scenario,
                    "JSON.stringify(window.__an3RememberedPeerProbe || {done:false})",
                )
                if (probe.optBoolean("done")) break
                Thread.sleep(250)
            }
            android.util.Log.i(
                "AN3SyncPreflight",
                "stage=${probe.optString("stage")} " +
                    "advertisements=${probe.optInt("advertisedPeerCount")} " +
                    "rememberedPeerAdvertised=${probe.optBoolean("rememberedPeerAdvertised")} " +
                    "manifest localFixtures=${probe.optInt("localFixtureCount")} " +
                    "remoteFixtures=${probe.optInt("remoteFixtureCount")} " +
                    "localSystem=${probe.optString("localFixtureSystem")} " +
                    "localSize=${probe.optInt("localFixtureSize")} " +
                    "remoteSystemMatches=${probe.optInt("remoteSystemMatchCount")} " +
                    "remoteSizeMatches=${probe.optInt("remoteSizeMatchCount")} " +
                    "exactFixtureMatches=${probe.optInt("matchingRemoteFixtureCount")} " +
                    "sameContent=${probe.optBoolean("sameFixtureContent")} " +
                    "failure=${probe.optString("failureCategory")}",
            )
            android.util.Log.i(
                "AN3SyncPreflight",
                "save localCount=${probe.optInt("localSaveCount")} " +
                    "remoteCount=${probe.optInt("remoteSaveCount")} " +
                    "identical=${probe.optBoolean("sameSaveContents")} " +
                    "safe=${probe.optBoolean("safeSaveTransfer")} " +
                    "conflictPlans=${probe.optInt("conflictPlanCount")} " +
                    "integrity=${probe.optInt("remoteSaveIntegrityCount")} " +
                    "protected=${probe.optBoolean("conflictProtected")} " +
                    "stage=${probe.optString("stage")}",
            )
            android.util.Log.i(
                "AN3SyncPreflight",
                "state local=${probe.optInt("localStateCount")} " +
                    "remote=${probe.optInt("remoteStateCount")} " +
                    "verified=${probe.optInt("verifiedRemoteStateCount")} " +
                    "same=${probe.optBoolean("sameStateContents")} " +
                    "safe=${probe.optBoolean("safeStateTransfer")} " +
                    "plans=${probe.optInt("statePlanReadCount")} " +
                    "conflicts=${probe.optInt("stateConflictCount")} " +
                    "uploads=${probe.optInt("stateUploadCount")} " +
                    "downloads=${probe.optInt("stateDownloadCount")} " +
                    "unchanged=${probe.optInt("stateNoopCount")}",
            )
            assertTrue(
                "an authenticated Mac save-state blob failed its manifest size/SHA-256 check",
                probe.optInt("verifiedRemoteStateCount") == probe.optInt("remoteStateCount"),
            )
            assertTrue(
                "the Mac did not return an authenticated planner result for every matching fixture",
                probe.optInt("statePlanReadCount") == probe.optInt("matchingRemoteFixtureCount"),
            )
            assertTrue("the app did not remember the completed Sync pairing", probe.optInt("remembered") > 0)
            assertTrue(
                "the remembered trusted peer was not present in the current LAN advertisement " +
                    "(advertisements=${probe.optInt("advertisedPeerCount")}, failure=${probe.optString("failureCategory")})",
                probe.optBoolean("rememberedPeerAdvertised"),
            )
            assertTrue(
                "the remembered Mac Sync peer did not reconnect with stored trust " +
                    "(states=${probe.optJSONArray("states")}, reconnectErrors=${probe.optInt("reconnectErrors")}, " +
                    "runtimeError=${probe.optBoolean("runtimeError")}, failure=${probe.optString("failureCategory")})",
                probe.optInt("connected") > 0,
            )
            assertTrue(
                "the authenticated direct Sync request did not receive a valid response " +
                    "(connected=${probe.optInt("connected")}, stage=${probe.optString("stage")}, " +
                    "failure=${probe.optString("failureCategory")})",
                probe.optBoolean("pingOk"),
            )
            assertTrue(
                "the phone library manifest did not contain the known homebrew fixture " +
                    "(items=${probe.optInt("localManifestItemCount")}, gba=${probe.optInt("localGbaItemCount")}, " +
                    "failure=${probe.optString("failureCategory")})",
                probe.optInt("localFixtureCount") > 0,
            )
            assertTrue(
                "the Mac manifest did not contain the known homebrew fixture " +
                    "(failure=${probe.optString("failureCategory")})",
                probe.optInt("remoteFixtureCount") > 0,
            )
            assertTrue(
                "the peers disagree on the shared fixture content identity " +
                    "(local=${probe.optInt("localFixtureCount")}, remote=${probe.optInt("remoteFixtureCount")}, " +
                    "stage=${probe.optString("stage")}, failure=${probe.optString("failureCategory")})",
                probe.optBoolean("sameFixtureContent"),
            )
            assertTrue(
                "the phone fixture did not expose its native SRAM record " +
                    "(local=${probe.optInt("localSaveCount")}, remote=${probe.optInt("remoteSaveCount")}, " +
                    "marker=${probe.optBoolean("localSaveMarker")}, counter=${probe.optInt("localSaveCounter")})",
                probe.optInt("localSaveCount") > 0 && probe.optBoolean("localSaveMarker"),
            )
            if (probe.optBoolean("conflictProtected")) {
                assertTrue(
                    "the divergent authenticated save was not preserved without writes " +
                        "(remote=${probe.optInt("remoteSaveCount")}, conflictPlans=${probe.optInt("conflictPlanCount")}, " +
                        "integrity=${probe.optInt("remoteSaveIntegrityCount")}, uploads=${probe.optInt("saveUploadCount")})",
                    probe.optInt("remoteSaveCount") > 0 && !probe.optBoolean("sameSaveContents")
                        && probe.optInt("conflictPlanCount") > 0
                        && probe.optInt("remoteSaveIntegrityCount") == probe.optInt("remoteSaveCount")
                        && probe.optInt("saveUploadCount") == 0,
                )
                return
            }
            assertTrue("save preflight did not establish a safe direction", probe.optBoolean("safeSaveTransfer"))
            android.util.Log.i(
                "AN3SyncPreflight",
                "localCount=${probe.optInt("localSaveCount")} " +
                    "remoteCount=${probe.optInt("remoteSaveCount")} " +
                    "identical=${probe.optBoolean("sameSaveContents")} " +
                    "counter=${probe.optInt("localSaveCounter")}",
            )
            assertTrue(
                "Android-to-Mac authenticated save transfer failed integrity/marker verification " +
                    "(uploaded=${probe.optInt("saveUploadCount")}, conflicts=${probe.optInt("saveConflictCount")}, " +
                    "destination=${probe.optInt("destinationSaveCount")}, marker=${probe.optBoolean("remoteSaveMarker")}, " +
                    "sourceCounter=${probe.optInt("localSaveCounter")}, destinationCounter=${probe.optInt("remoteSaveCounter")})",
                probe.optBoolean("verifiedSaveTransfer"),
            )
        } finally {
            if (!keepAppOpen) scenario.close()
        }
    }

    @Test
    fun syncsOnlySelectedSyntheticRomAndVerifiesNativeFinalize() {
        val targetHash = InstrumentationRegistry.getArguments()
            .getString("selectedLibraryHash")
            .orEmpty()
            .lowercase()
        assertTrue(
            "Pass the SHA-256 of the isolated Mac homebrew ROM as selectedLibraryHash",
            targetHash.matches(Regex("^[a-f0-9]{64}$")),
        )

        val scenario = ActivityScenario.launch(MainActivity::class.java)
        try {
            awaitWebView()
            onWebView().forceJavascriptEnabled()
            awaitNativeSync(scenario)
            val initiation = evalJson(
                scenario,
                """(function(){
                    var probe = window.__an3SelectedRomSyncProbe = {
                      done:false, stage:"init", failureCategory:"", remembered:false,
                      advertised:false, connected:false, pingOk:false, remoteTargetCount:0,
                      localTargetCount:0, localManifestShape:false, remoteManifestShape:false,
                      targetHashValid:false, alreadyPresent:false, transferCount:0, selectedOnly:false,
                      downloaded:0, uploaded:0, conflicts:0, nativeVerified:false,
                      libraryRecognized:false, remoteUnchanged:false, unrelatedLocalUnchanged:false,
                      progressComplete:false, progressBytes:0, progressTotalBytes:0,
                      saveStateArtifactsNoop:false, lastPhase:"", lastSubstate:""
                    };
                    var fail = function(stage, category) {
                      probe.done = true; probe.stage = stage; probe.failureCategory = category;
                    };
                    (async function(){
                      try {
                        var api = window.AN3NativeSync;
                        var initial = await api.init();
                        var remembered = (initial.peers || []).filter(function(peer){ return Boolean(peer.deviceId); });
                        probe.remembered = remembered.length > 0;
                        if (!remembered.length) return fail("peer", "no-remembered-peer");
                        var advertisements = await api.discover();
                        var peer = remembered.find(function(rememberedPeer){
                          return (advertisements || []).some(function(advertisedPeer){
                            return advertisedPeer.deviceId === rememberedPeer.deviceId;
                          });
                        });
                        probe.advertised = Boolean(peer);
                        if (!peer) return fail("discovery", "peer-not-advertised");
                        if (peer.state !== "connected") await api.reconnect(peer.deviceId);
                        var deadline = Date.now() + 18_000;
                        while (Date.now() < deadline) {
                          var status = await api.status();
                          probe.connected = (status.peers || []).some(function(item){ return item.state === "connected"; });
                          if (probe.connected) break;
                          await new Promise(function(resolve){ setTimeout(resolve, 250); });
                        }
                        if (!probe.connected) return fail("reconnect", "not-connected");
                        var ping = await api.request("ping", {});
                        probe.pingOk = Boolean(ping && ping.ok === true && typeof ping.peerId === "string" && ping.peerId.length > 0);
                        if (!probe.pingOk) return fail("ping", "unauthenticated-response");
                        var invoke = window.AN3NativeInvoke && window.AN3NativeInvoke();
                        if (typeof invoke !== "function") return fail("bridge", "native-bridge-unavailable");
                        probe.stage = "local-manifest";
                        var localBefore = await invoke("native_sync_library_manifest", {});
                        probe.localManifestShape = Boolean(localBefore && Array.isArray(localBefore.items));
                        if (!probe.localManifestShape) return fail("local-manifest-shape", "invalid-local-manifest");
                        probe.stage = "remote-manifest";
                        var remoteBefore = await api.request("library-manifest", {});
                        probe.remoteManifestShape = Boolean(remoteBefore && Array.isArray(remoteBefore.items));
                        if (!probe.remoteManifestShape) return fail("remote-manifest-shape", "invalid-remote-manifest");
                        probe.stage = "target-selection";
                        var selectedHash = "$targetHash";
                        probe.targetHashValid = /^[a-f0-9]{64}$/.test(selectedHash);
                        if (!probe.targetHashValid) return fail("target-hash", "invalid-selected-hash");
                        var remoteItems = remoteBefore.items || [];
                        var localItems = localBefore.items || [];
                        var targets = remoteItems.filter(function(item){
                          return item.system === "gba" && String(item.contentHash || "").toLowerCase() === selectedHash;
                        });
                        probe.remoteTargetCount = targets.length;
                        probe.localTargetCount = localItems.filter(function(item){
                          return String(item.contentHash || "").toLowerCase() === selectedHash;
                        }).length;
                        if (targets.length !== 1 || probe.localTargetCount > 1) return fail("preflight", "target-not-unique");
                        var target = targets[0];
                        var localTarget = localItems.find(function(item){ return item.key === target.key; });
                        if (probe.localTargetCount === 1) {
                          if (!localTarget || localTarget.size !== target.size
                              || String(localTarget.contentHash || "").toLowerCase() !== selectedHash
                              || localTarget.extension !== target.extension || localTarget.system !== target.system) {
                            return fail("preflight", "local-content-conflict");
                          }
                          probe.alreadyPresent = true;
                        } else if (localTarget) {
                          return fail("preflight", "local-key-conflict");
                        }
                        var canonical = function(items, omitKey) {
                          return JSON.stringify((items || []).filter(function(item){ return item.key !== omitKey; }).map(function(item){
                            return [String(item.key || ""), String(item.extension || ""), String(item.system || ""), Number(item.size), String(item.contentHash || "").toLowerCase()];
                          }).sort(function(a,b){ return a[0].localeCompare(b[0]); }));
                        };
                        var phases = [];
                        var lastCompleted = 0;
                        var lastTotal = 0;
                        var result = {transfers:[], counts:{uploaded:0, downloaded:0, conflicts:0}, artifacts:[]};
                        if (probe.alreadyPresent) {
                          phases.push("already-present", "complete");
                          lastCompleted = target.size;
                          lastTotal = target.size;
                        } else {
                          probe.stage = "selected-sync";
                          result = await api.syncLibrary({
                            keys:[target.key],
                            onState:function(state){
                              var phase = String(state.phase || "");
                              phases.push(phase);
                              probe.lastPhase = phase;
                              if (state.state && typeof state.state === "string") probe.lastSubstate = state.state;
                              lastCompleted = Number(state.completedBytes) || lastCompleted;
                              lastTotal = Number(state.totalBytes) || lastTotal;
                            }
                          });
                        }
                        probe.transferCount = (result.transfers || []).length;
                        probe.selectedOnly = probe.alreadyPresent || (probe.transferCount === 1
                          && result.transfers[0].key === target.key && result.transfers[0].direction === "download");
                        probe.downloaded = Number(result.counts && result.counts.downloaded) || 0;
                        probe.uploaded = Number(result.counts && result.counts.uploaded) || 0;
                        probe.conflicts = Number(result.counts && result.counts.conflicts) || 0;
                        var localAfter = await invoke("native_sync_library_manifest", {});
                        var remoteAfter = await api.request("library-manifest", {});
                        var localFinal = (localAfter.items || []).find(function(item){ return item.key === target.key; });
                        var remoteFinal = (remoteAfter.items || []).find(function(item){ return item.key === target.key; });
                        probe.nativeVerified = Boolean(localFinal && localFinal.size === target.size
                          && String(localFinal.contentHash || "").toLowerCase() === selectedHash
                          && remoteFinal && remoteFinal.size === target.size
                          && String(remoteFinal.contentHash || "").toLowerCase() === selectedHash);
                        probe.remoteUnchanged = canonical(remoteBefore.items) === canonical(remoteAfter.items);
                        probe.unrelatedLocalUnchanged = canonical(localBefore.items, target.key) === canonical(localAfter.items, target.key);
                        var library = globalThis.AN3OfflineLibrary;
                        var libraryItems = library && typeof library.list === "function" ? await library.list() : [];
                        probe.libraryRecognized = (libraryItems || []).some(function(item){
                          return String(item.id || "") === target.romId && String(item.system || "").toLowerCase() === "gba";
                        });
                        var artifacts = result.artifacts || [];
                        probe.saveStateArtifactsNoop = probe.alreadyPresent || (artifacts.length === 2 && artifacts.every(function(artifact){
                          var counts = artifact.result && artifact.result.counts || {};
                          return Number(counts.uploaded || 0) === 0 && Number(counts.downloaded || 0) === 0
                            && Number(counts.conflicts || 0) === 0;
                        }));
                        probe.progressComplete = phases.indexOf("downloading") >= 0 && phases.indexOf("complete") >= 0
                          && lastCompleted === target.size && lastTotal === target.size;
                        probe.progressBytes = lastCompleted;
                        probe.progressTotalBytes = lastTotal;
                        probe.done = true;
                        probe.stage = "complete";
                      } catch (error) {
                        var message = String(error && error.message || error);
                        var category = /trust|auth|account/i.test(message) ? "auth"
                          : /connect|network|socket|timeout/i.test(message) ? "network" : "native-or-sync";
                        fail(probe.stage, category);
                      }
                    })();
                    return JSON.stringify({started:true});
                })()""",
            )
            assertTrue("selected ROM sync probe did not start", initiation.optBoolean("started"))

            val deadline = System.currentTimeMillis() + 60_000
            var probe = JSONObject()
            while (System.currentTimeMillis() < deadline) {
                probe = evalJson(
                    scenario,
                    "JSON.stringify(window.__an3SelectedRomSyncProbe || {done:false})",
                )
                if (probe.optBoolean("done")) break
                Thread.sleep(250)
            }
            android.util.Log.i(
                "AN3LibrarySync",
                        "stage=${probe.optString("stage")} failure=${probe.optString("failureCategory")} " +
                        "selected=${probe.optBoolean("selectedOnly")} downloaded=${probe.optInt("downloaded")} " +
                        "alreadyPresent=${probe.optBoolean("alreadyPresent")} " +
                        "remoteTargets=${probe.optInt("remoteTargetCount")} localTargets=${probe.optInt("localTargetCount")} " +
                        "localManifestShape=${probe.optBoolean("localManifestShape")} remoteManifestShape=${probe.optBoolean("remoteManifestShape")} " +
                        "targetHashValid=${probe.optBoolean("targetHashValid")} " +
                        "nativeVerified=${probe.optBoolean("nativeVerified")} recognized=${probe.optBoolean("libraryRecognized")} " +
                    "remoteUnchanged=${probe.optBoolean("remoteUnchanged")} unrelatedLocalUnchanged=${probe.optBoolean("unrelatedLocalUnchanged")} " +
                    "lastPhase=${probe.optString("lastPhase")} lastSubstate=${probe.optString("lastSubstate")} " +
                    "progress=${probe.optLong("progressBytes")}/${probe.optLong("progressTotalBytes")}",
            )
            assertTrue("selected ROM sync did not finish", probe.optBoolean("done"))
            assertTrue("authenticated Mac peer was not remembered and advertised", probe.optBoolean("remembered") && probe.optBoolean("advertised"))
            assertTrue("selected ROM sync did not reconnect and authenticate", probe.optBoolean("connected") && probe.optBoolean("pingOk"))
            assertTrue("selected ROM preflight did not find exactly one remote target", probe.optInt("remoteTargetCount") == 1 && probe.optInt("localTargetCount") <= 1)
            assertTrue(
                "syncLibrary transferred an unselected item",
                probe.optBoolean("selectedOnly")
                    && probe.optInt("transferCount") == (if (probe.optBoolean("alreadyPresent")) 0 else 1),
            )
            assertTrue(
                "selected ROM was neither downloaded cleanly nor already present as the exact same file",
                if (probe.optBoolean("alreadyPresent")) probe.optInt("downloaded") == 0
                else probe.optInt("downloaded") == 1 && probe.optInt("uploaded") == 0 && probe.optInt("conflicts") == 0,
            )
            assertTrue("native finalization did not expose the matching SHA-256/size on both peers", probe.optBoolean("nativeVerified"))
            assertTrue("the receiving app did not recognize the synced homebrew entry", probe.optBoolean("libraryRecognized"))
            assertTrue("targeted ROM sync changed the Mac or unrelated phone library entries", probe.optBoolean("remoteUnchanged") && probe.optBoolean("unrelatedLocalUnchanged"))
            assertTrue(
                "ROM transfer progress did not finish at the declared byte total",
                probe.optBoolean("alreadyPresent") || probe.optBoolean("progressComplete"),
            )
            assertTrue("the new ROM unexpectedly caused save/savestate writes", probe.optBoolean("saveStateArtifactsNoop"))
        } finally {
            if (!keepAppOpen) scenario.close()
        }
    }

    @Test
    fun uploadsOnlySelectedSyntheticRomToMacAndVerifiesNativeFinalize() {
        val romId = InstrumentationRegistry.getArguments().getString("uploadRomId").orEmpty().lowercase()
        val targetHash = InstrumentationRegistry.getArguments().getString("uploadRomHash").orEmpty().lowercase()
        val romTitle = InstrumentationRegistry.getArguments().getString("uploadRomTitle").orEmpty()
        val encodedBytes = InstrumentationRegistry.getArguments().getString("uploadRomBase64").orEmpty()
        assertTrue("Pass a UUID-shaped synthetic upload ROM identity", romId.matches(Regex("^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")))
        assertTrue("Pass the synthetic upload ROM SHA-256", targetHash.matches(Regex("^[a-f0-9]{64}$")))
        assertTrue("Pass a synthetic AN3SYNCROM* title", romTitle.matches(Regex("^AN3SYNCROM[0-9]{1,2}$")) && romTitle.length <= 12)
        assertTrue("Pass a bounded base64 synthetic ROM fixture", encodedBytes.length in 4..8192)
        val fixtureBytes = try { Base64.getDecoder().decode(encodedBytes) } catch (error: IllegalArgumentException) {
            throw AssertionError("The synthetic ROM fixture is not valid base64", error)
        }
        assertTrue("The synthetic ROM fixture must be 512 bytes", fixtureBytes.size == 512)
        val fixtureHash = MessageDigest.getInstance("SHA-256").digest(fixtureBytes)
            .joinToString("") { "%02x".format(it) }
        assertTrue("The synthetic ROM bytes do not match uploadRomHash", fixtureHash == targetHash)

        val scenario = ActivityScenario.launch(MainActivity::class.java)
        try {
            awaitWebView()
            onWebView().forceJavascriptEnabled()
            awaitNativeSync(scenario)
            connectDirectPeer(scenario)
            val initiation = evalJson(
                scenario,
                """(function(){
                    var probe = window.__an3SelectedRomUploadProbe = {
                      done:false, stage:"init", failureCategory:"", remembered:false, advertised:false,
                      direct:false,
                      connected:false, pingOk:false, targetAbsent:false, localFinalized:false,
                      libraryRecognized:false, emptyArtifacts:false, selectedOnly:false, uploaded:0,
                      downloaded:0, conflicts:0, nativeVerified:false, remoteBlobVerified:false,
                      remoteUnchanged:false, unrelatedLocalUnchanged:false, artifactsNoop:false,
                      progressComplete:false, progressBytes:0, progressTotalBytes:0, lastPhase:""
                    };
                    var fail = function(stage, category) { probe.done = true; probe.stage = stage; probe.failureCategory = category; };
                    var hashBytes = async function(bytes) {
                      var digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
                      return Array.from(digest).map(function(byte){ return byte.toString(16).padStart(2, "0"); }).join("");
                    };
                    var canonical = function(items, omitKey) {
                      return JSON.stringify((items || []).filter(function(item){ return item.key !== omitKey; }).map(function(item){
                        return [String(item.key || ""), String(item.extension || ""), String(item.system || ""), Number(item.size), String(item.contentHash || "").toLowerCase()];
                      }).sort(function(a,b){ return a[0].localeCompare(b[0]); }));
                    };
                    (async function(){
                      try {
                        var api = window.AN3NativeSync;
                        var initial = await api.init();
                        var remembered = (initial.peers || []).filter(function(peer){ return Boolean(peer.deviceId); });
                        probe.remembered = remembered.length > 0;
                        if (!remembered.length) return fail("peer", "no-remembered-peer");
                        var directTarget = "$directSyncTarget";
                        probe.direct = Boolean(directTarget);
                        var advertisements = directTarget ? [] : await api.discover();
                        var peer = directTarget
                          ? remembered.find(function(saved){ return saved.state === "connected"; })
                          : remembered.find(function(saved){
                              return (advertisements || []).some(function(item){ return item.deviceId === saved.deviceId; });
                            });
                        probe.advertised = Boolean(peer) && !directTarget;
                        if (!peer) return fail("discovery", "peer-not-advertised");
                        if (peer.state !== "connected") await api.reconnect(peer.deviceId);
                        var deadline = Date.now() + 18_000;
                        while (Date.now() < deadline) {
                          var status = await api.status();
                          probe.connected = (status.peers || []).some(function(item){ return item.state === "connected"; });
                          if (probe.connected) break;
                          await new Promise(function(resolve){ setTimeout(resolve, 250); });
                        }
                        if (!probe.connected) return fail("reconnect", "not-connected");
                        var ping = await api.request("ping", {});
                        probe.pingOk = Boolean(ping && ping.ok === true && typeof ping.peerId === "string" && ping.peerId.length > 0);
                        if (!probe.pingOk) return fail("ping", "unauthenticated-response");
                        var invoke = window.AN3NativeInvoke && window.AN3NativeInvoke();
                        if (typeof invoke !== "function") return fail("bridge", "native-bridge-unavailable");
                        var romId = "$romId";
                        var hash = "$targetHash";
                        var key = "rom:" + romId;
                        var encoded = "$encodedBytes";
                        var bytes = Uint8Array.from(atob(encoded), function(character){ return character.charCodeAt(0); });
                        if (bytes.byteLength !== 512 || await hashBytes(bytes) !== hash) return fail("fixture", "fixture-integrity-failed");
                        probe.stage = "library-preflight";
                        var localBefore = await invoke("native_sync_library_manifest", {});
                        var remoteBefore = await api.request("library-manifest", {});
                        var localItems = localBefore && Array.isArray(localBefore.items) ? localBefore.items : null;
                        var remoteItems = remoteBefore && Array.isArray(remoteBefore.items) ? remoteBefore.items : null;
                        if (!localItems || !remoteItems) return fail("library-preflight", "manifest-shape-invalid");
                        probe.targetAbsent = !localItems.some(function(item){ return item.key === key || String(item.contentHash || "").toLowerCase() === hash; })
                          && !remoteItems.some(function(item){ return item.key === key || String(item.contentHash || "").toLowerCase() === hash; });
                        if (!probe.targetAbsent) return fail("library-preflight", "synthetic-target-already-exists");
                        probe.stage = "native-source-finalize";
                        await invoke("native_sync_library_write_chunk", {payload:{
                          romId:romId, extension:"gba", size:bytes.byteLength, contentHash:hash,
                          offset:0, data:encoded
                        }});
                        var localSeeded = await invoke("native_sync_library_manifest", {});
                        var source = (localSeeded.items || []).find(function(item){ return item.key === key; });
                        probe.localFinalized = Boolean(source && source.size === bytes.byteLength
                          && String(source.contentHash || "").toLowerCase() === hash);
                        if (!probe.localFinalized) return fail("native-source-finalize", "local-rom-not-finalized");
                        var identity = await api.gameIdentity("gba", romId);
                        var library = globalThis.AN3OfflineLibrary;
                        if (!library || typeof library.put !== "function") return fail("library", "library-adapter-unavailable");
                        await library.put({
                          id:romId, title:"$romTitle", name:romId + ".gba", system:"gba",
                          size:bytes.byteLength, romHash:hash, addedAt:Date.now(), nativeRomId:romId,
                          nativePath:"/native-rom/" + romId + ".gba"
                        });
                        var libraryItems = await library.list();
                        probe.libraryRecognized = (libraryItems || []).some(function(item){
                          return String(item.id || "") === romId && String(item.system || "").toLowerCase() === "gba";
                        });
                        var artifactSnapshots = {};
                        for (var kind of ["save", "state"]) {
                          var context = {kind:kind, system:"gba", romId:romId, identity:identity};
                          var local = await api.storage(kind, "gba", romId, identity).readAll();
                          var remote = await api.transport.manifest(kind, context);
                          var remoteCount = kind === "save"
                            ? (remote.sets || []).filter(function(set){ return set.gameId === identity.gameId && set.romHash === identity.romHash; }).length
                            : (remote.items || []).length;
                          artifactSnapshots[kind] = {local:local.length, remote:remoteCount};
                          if (local.length || remoteCount) return fail("artifact-preflight-" + kind, "existing-artifact-preserved");
                        }
                        probe.emptyArtifacts = true;
                        probe.stage = "selected-upload";
                        var phases = [];
                        var completed = 0;
                        var total = 0;
                        var result = await api.syncLibrary({keys:[key], onState:function(state){
                          var phase = String(state && state.phase || "");
                          phases.push(phase);
                          probe.lastPhase = phase;
                          completed = Number(state && state.completedBytes) || completed;
                          total = Number(state && state.totalBytes) || total;
                        }});
                        probe.selectedOnly = Boolean(result && result.transfers && result.transfers.length === 1
                          && result.transfers[0].key === key && result.transfers[0].direction === "upload");
                        probe.uploaded = Number(result.counts && result.counts.uploaded) || 0;
                        probe.downloaded = Number(result.counts && result.counts.downloaded) || 0;
                        probe.conflicts = Number(result.counts && result.counts.conflicts) || 0;
                        var artifacts = result.artifacts || [];
                        probe.artifactsNoop = ["save", "state"].every(function(kind){
                          var artifact = artifacts.find(function(item){ return item.kind === kind; });
                          var counts = artifact && artifact.result && artifact.result.counts || {};
                          return Boolean(artifact) && Number(counts.uploaded || 0) === 0
                            && Number(counts.downloaded || 0) === 0 && Number(counts.conflicts || 0) === 0;
                        });
                        var localAfter = await invoke("native_sync_library_manifest", {});
                        var remoteAfter = await api.request("library-manifest", {});
                        var localTarget = (localAfter.items || []).find(function(item){ return item.key === key; });
                        var remoteTarget = (remoteAfter.items || []).find(function(item){ return item.key === key; });
                        probe.nativeVerified = Boolean(localTarget && localTarget.size === bytes.byteLength
                          && String(localTarget.contentHash || "").toLowerCase() === hash
                          && remoteTarget && remoteTarget.size === bytes.byteLength
                          && String(remoteTarget.contentHash || "").toLowerCase() === hash);
                        probe.remoteUnchanged = canonical(remoteBefore.items, key) === canonical(remoteAfter.items, key);
                        probe.unrelatedLocalUnchanged = canonical(localBefore.items) === canonical(localAfter.items, key);
                        var remoteBlob = await api.request("library-blob", {
                          romId:romId, extension:"gba", size:bytes.byteLength,
                          contentHash:hash, offset:0, length:bytes.byteLength
                        });
                        var remoteBytes = Uint8Array.from(atob(String(remoteBlob && remoteBlob.data || "")), function(character){ return character.charCodeAt(0); });
                        probe.remoteBlobVerified = remoteBytes.byteLength === bytes.byteLength && await hashBytes(remoteBytes) === hash;
                        probe.progressComplete = phases.indexOf("uploading") >= 0 && phases.indexOf("complete") >= 0
                          && completed === bytes.byteLength && total === bytes.byteLength;
                        probe.progressBytes = completed;
                        probe.progressTotalBytes = total;
                        probe.done = true;
                        probe.stage = "complete";
                      } catch (error) {
                        var message = String(error && error.message || error);
                        var category = /trust|auth|account/i.test(message) ? "auth"
                          : /connect|network|socket|timeout/i.test(message) ? "network" : "native-or-sync";
                        fail(probe.stage, category);
                      }
                    })();
                    return JSON.stringify({started:true});
                })()""",
            )
            assertTrue("selected upload probe did not start", initiation.optBoolean("started"))

            val deadline = System.currentTimeMillis() + 60_000
            var probe = JSONObject()
            while (System.currentTimeMillis() < deadline) {
                probe = evalJson(scenario, "JSON.stringify(window.__an3SelectedRomUploadProbe || {done:false})")
                if (probe.optBoolean("done")) break
                Thread.sleep(250)
            }
            android.util.Log.i(
                "AN3LibraryUpload",
                "stage=${probe.optString("stage")} failure=${probe.optString("failureCategory")} " +
                    "targetAbsent=${probe.optBoolean("targetAbsent")} localFinalized=${probe.optBoolean("localFinalized")} " +
                    "selected=${probe.optBoolean("selectedOnly")} uploaded=${probe.optInt("uploaded")} " +
                    "downloaded=${probe.optInt("downloaded")} conflicts=${probe.optInt("conflicts")} " +
                    "nativeVerified=${probe.optBoolean("nativeVerified")} blobVerified=${probe.optBoolean("remoteBlobVerified")} " +
                    "remoteUnchanged=${probe.optBoolean("remoteUnchanged")} unrelatedLocalUnchanged=${probe.optBoolean("unrelatedLocalUnchanged")} " +
                    "libraryRecognized=${probe.optBoolean("libraryRecognized")} artifactsNoop=${probe.optBoolean("artifactsNoop")} " +
                    "progress=${probe.optLong("progressBytes")}/${probe.optLong("progressTotalBytes")} lastPhase=${probe.optString("lastPhase")}",
            )
            assertTrue("selected synthetic upload did not finish", probe.optBoolean("done"))
            assertTrue(
                "authenticated Mac peer was not remembered and connected",
                probe.optBoolean("remembered") && (probe.optBoolean("advertised") || probe.optBoolean("direct"))
                    && probe.optBoolean("connected") && probe.optBoolean("pingOk"),
            )
            assertTrue("the selected synthetic ROM already existed on one peer", probe.optBoolean("targetAbsent"))
            assertTrue("the local test ROM did not finalize before transfer", probe.optBoolean("localFinalized"))
            assertTrue("the selected upload was not the only ROM transfer", probe.optBoolean("selectedOnly") && probe.optInt("uploaded") == 1 && probe.optInt("downloaded") == 0 && probe.optInt("conflicts") == 0)
            assertTrue("the Mac native library did not finalize the exact ROM bytes", probe.optBoolean("nativeVerified") && probe.optBoolean("remoteBlobVerified"))
            assertTrue("the Mac library or unrelated Android entries changed", probe.optBoolean("remoteUnchanged") && probe.optBoolean("unrelatedLocalUnchanged"))
            assertTrue("the Android app did not recognize the local synthetic ROM", probe.optBoolean("libraryRecognized"))
            assertTrue("save/state artifact manifests were not empty or unexpected writes occurred", probe.optBoolean("emptyArtifacts") && probe.optBoolean("artifactsNoop"))
            assertTrue("ROM upload progress did not finish at the declared byte total", probe.optBoolean("progressComplete"))
        } finally {
            if (!keepAppOpen) scenario.close()
        }
    }

    @Test
    fun syncsFreshSyntheticSramFromPhysicalPhoneToMac() {
        val romId = InstrumentationRegistry.getArguments().getString("saveRomId").orEmpty().lowercase()
        val romHash = InstrumentationRegistry.getArguments().getString("saveRomHash").orEmpty().lowercase()
        val romTitle = InstrumentationRegistry.getArguments().getString("saveRomTitle").orEmpty()
        val resumeInterruptedRom5 = InstrumentationRegistry.getArguments().getString("resumeInterruptedRom5") == "true"
        assertTrue("Pass the paired synthetic ROM UUID", romId.matches(Regex("^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")))
        assertTrue("Pass the paired synthetic ROM SHA-256", romHash.matches(Regex("^[a-f0-9]{64}$")))
        assertTrue("Pass a fresh AN3SYNCROM* homebrew title", romTitle.matches(Regex("^AN3SYNCROM[0-9]{1,2}$")) && romTitle.length <= 12)
        if (resumeInterruptedRom5) {
            assertTrue(
                "The interrupted-save recovery is restricted to its exact synthetic ROM5 fixture",
                romId == "35449eec-f404-44f8-a962-b6388fba514a" &&
                    romHash == "491f640b78e89a6f86ac99ad1dbf2dd4bbb6139c805312f3124a1ed4ed02a655" &&
                    romTitle == "AN3SYNCROM5",
            )
        }

        val scenario = ActivityScenario.launch(MainActivity::class.java)
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
        try {
            awaitWebView()
            onWebView().forceJavascriptEnabled()
            awaitNativeSync(scenario)
            connectDirectPeer(scenario)
            val preflight = evalJson(
                scenario,
                """(function(){
                    var probe = window.__an3SyntheticSramSyncProbe = {
                      done:false, stage:"preflight", failureCategory:"", paired:false, advertised:false,
                      direct:false,
                      connected:false, pingOk:false, romExact:false, localSaveEmpty:false, resumeEligible:false,
                      localSaveCount:0, initialCounter:255, resumeCounter:-1, skipGameBoot:false,
                      remoteSaveEmpty:false, localStateEmpty:false, remoteStateEmpty:false,
                      gameClicked:false, nativeGameStarted:false, localSramVerified:false,
                      remoteSaveUploaded:false, remoteSramVerified:false, localSramUnchanged:false,
                      localCounter:-1, remoteCounter:-1
                    };
                    var fail = function(stage, category) { probe.done = true; probe.stage = stage; probe.failureCategory = category; };
                    var hashBytes = async function(bytes) {
                      var digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
                      return Array.from(digest).map(function(byte){ return byte.toString(16).padStart(2, "0"); }).join("");
                    };
                    var remoteSetsFor = function(manifest, identity) {
                      return (manifest && manifest.sets || []).filter(function(set){
                        return set.gameId === identity.gameId && set.romHash === identity.romHash;
                      });
                    };
                    var resumeInterruptedRom5 = $resumeInterruptedRom5;
                    (async function(){
                      try {
                        var api = window.AN3NativeSync;
                        var initial = await api.init();
                        var remembered = (initial.peers || []).filter(function(peer){ return Boolean(peer.deviceId); });
                        probe.paired = remembered.length > 0;
                        if (!remembered.length) return fail("peer", "no-remembered-peer");
                        var directTarget = "$directSyncTarget";
                        probe.direct = Boolean(directTarget);
                        var advertisements = directTarget ? [] : await api.discover();
                        var peer = directTarget
                          ? remembered.find(function(saved){ return saved.state === "connected"; })
                          : remembered.find(function(saved){
                              return (advertisements || []).some(function(item){ return item.deviceId === saved.deviceId; });
                            });
                        probe.advertised = Boolean(peer) && !directTarget;
                        if (!peer) return fail("discovery", "peer-not-advertised");
                        if (peer.state !== "connected") await api.reconnect(peer.deviceId);
                        var deadline = Date.now() + 18_000;
                        while (Date.now() < deadline) {
                          var status = await api.status();
                          probe.connected = (status.peers || []).some(function(item){ return item.state === "connected"; });
                          if (probe.connected) break;
                          await new Promise(function(resolve){ setTimeout(resolve, 250); });
                        }
                        if (!probe.connected) return fail("reconnect", "not-connected");
                        var ping = await api.request("ping", {});
                        probe.pingOk = Boolean(ping && ping.ok === true && typeof ping.peerId === "string" && ping.peerId.length > 0);
                        if (!probe.pingOk) return fail("ping", "unauthenticated-response");
                        var invoke = window.AN3NativeInvoke && window.AN3NativeInvoke();
                        if (typeof invoke !== "function") return fail("bridge", "native-bridge-unavailable");
                        var romId = "$romId";
                        var romHash = "$romHash";
                        var localManifest = await invoke("native_sync_library_manifest", {});
                        var localRom = (localManifest.items || []).filter(function(item){ return item.romId === romId; });
                        var remoteManifest = await api.request("library-manifest", {});
                        var remoteRom = (remoteManifest.items || []).filter(function(item){ return item.romId === romId; });
                        probe.romExact = localRom.length === 1 && remoteRom.length === 1
                          && String(localRom[0].contentHash || "").toLowerCase() === romHash
                          && String(remoteRom[0].contentHash || "").toLowerCase() === romHash
                          && Number(localRom[0].size) === Number(remoteRom[0].size);
                        if (!probe.romExact) return fail("rom-preflight", "peers-do-not-have-exact-rom");
                        var identity = await api.gameIdentity("gba", romId);
                        var saveContext = {kind:"save", system:"gba", romId:romId, identity:identity};
                        var stateContext = {kind:"state", system:"gba", romId:romId, identity:identity};
                        var localSave = await api.storage("save", "gba", romId, identity).readAll();
                        var remoteSave = await api.transport.manifest("save", saveContext);
                        var localState = await api.storage("state", "gba", romId, identity).readAll();
                        var remoteState = await api.transport.manifest("state", stateContext);
                        probe.localSaveCount = localSave.length;
                        probe.localSaveEmpty = localSave.length === 0;
                        if (resumeInterruptedRom5 && localSave.length === 1) {
                          var interruptedBytes = localSave[0].bytes instanceof Uint8Array
                            ? localSave[0].bytes : new Uint8Array(localSave[0].bytes || []);
                          var interruptedSignature = interruptedBytes.length >= 4
                            && String.fromCharCode.apply(null, Array.from(interruptedBytes.slice(0, 4))) === "AN3B";
                          var interruptedCounter = interruptedBytes.length > 4 ? interruptedBytes[4] : -1;
                          var expectedInterruptedBytes = new Uint8Array(32768);
                          expectedInterruptedBytes.fill(255);
                          expectedInterruptedBytes.set([65, 78, 51, 66, interruptedCounter & 255]);
                          var interruptedHash = await hashBytes(interruptedBytes);
                          var expectedInterruptedHash = await hashBytes(expectedInterruptedBytes);
                          probe.resumeEligible = interruptedBytes.byteLength === 32768 && interruptedSignature
                            && (interruptedCounter === 0 || interruptedCounter === 1)
                            && interruptedHash === expectedInterruptedHash;
                          probe.resumeCounter = interruptedCounter;
                          probe.skipGameBoot = probe.resumeEligible && interruptedCounter === 1;
                        }
                        probe.initialCounter = probe.resumeEligible ? probe.resumeCounter : 255;
                        probe.remoteSaveEmpty = remoteSetsFor(remoteSave, identity).length === 0 && !(remoteSave.items || []).length;
                        probe.localStateEmpty = localState.length === 0;
                        probe.remoteStateEmpty = !(remoteState.items || []).length;
                        if ((!probe.localSaveEmpty && !probe.resumeEligible) || !probe.remoteSaveEmpty || !probe.localStateEmpty || !probe.remoteStateEmpty) {
                          return fail("artifact-preflight", "existing-artifact-preserved");
                        }
                        if (probe.skipGameBoot) {
                          probe.done = true;
                          probe.stage = "recovered-save";
                          return;
                        }
                        probe.stage = "library-launch";
                        await globalThis.AN3RerenderLibrary?.();
                        var navigation = document.querySelector('[data-nav="library"]');
                        if (!navigation) return fail("library-launch", "library-navigation-unavailable");
                        navigation.click();
                        await globalThis.AN3RerenderLibrary?.();
                        var title = Array.from(document.querySelectorAll("h4")).find(function(node){ return node.textContent === "$romTitle"; });
                        var launch = title && title.closest("article")?.querySelector('[data-testid="game-launch"]');
                        if (!launch) return fail("library-launch", "synthetic-game-launch-button-missing");
                        launch.click();
                        probe.gameClicked = true;
                        probe.done = true;
                        probe.stage = "await-native-game";
                      } catch (error) {
                        var message = String(error && error.message || error);
                        var category = /trust|auth|account/i.test(message) ? "auth"
                          : /connect|network|socket|timeout/i.test(message) ? "network" : "native-or-ui";
                        fail(probe.stage, category);
                      }
                    })();
                    return JSON.stringify({started:true});
                })()""",
            )
            assertTrue("synthetic SRAM preflight did not start", preflight.optBoolean("started"))
            val preflightDeadline = System.currentTimeMillis() + 30_000
            var probe = JSONObject()
            while (System.currentTimeMillis() < preflightDeadline) {
                probe = evalJson(scenario, "JSON.stringify(window.__an3SyntheticSramSyncProbe || {done:false})")
                if (probe.optBoolean("done")) break
                Thread.sleep(250)
            }
            assertTrue("synthetic SRAM preflight did not finish", probe.optBoolean("done"))
            assertTrue(
                "authenticated Mac peer was unavailable",
                probe.optBoolean("paired") && (probe.optBoolean("advertised") || probe.optBoolean("direct"))
                    && probe.optBoolean("connected") && probe.optBoolean("pingOk"),
            )
            assertTrue("the fresh synthetic ROM was not byte-identical on both peers", probe.optBoolean("romExact"))
            assertTrue(
                "unsafe existing artifacts; no game or Sync write was attempted " +
                    "(phone save count=${probe.optInt("localSaveCount")}, empty=${probe.optBoolean("localSaveEmpty")}, " +
                    "exact interrupted ROM5 save=${probe.optBoolean("resumeEligible")}, " +
                    "Mac save empty=${probe.optBoolean("remoteSaveEmpty")}, phone state empty=${probe.optBoolean("localStateEmpty")}, " +
                    "Mac state empty=${probe.optBoolean("remoteStateEmpty")})",
                (probe.optBoolean("localSaveEmpty") || probe.optBoolean("resumeEligible")) && probe.optBoolean("remoteSaveEmpty") &&
                    probe.optBoolean("localStateEmpty") && probe.optBoolean("remoteStateEmpty"),
            )
            if (probe.optBoolean("skipGameBoot")) {
                assertTrue("the recovered ROM5 save was not an exact counter-1 fixture", probe.optBoolean("resumeEligible") && probe.optInt("resumeCounter") == 1)
            } else {
                assertTrue("the actual synthetic game was not selected through the library UI", probe.optBoolean("gameClicked"))
            }

            var gameProcessStarted = false
            var gameProcessRetainedAfterExit = false
            if (!probe.optBoolean("skipGameBoot")) {
                assertTrue("the native GBA game/menu did not appear", device.wait(Until.hasObject(By.text("Menu")), 30_000))
                val gameStartDeadline = System.currentTimeMillis() + 15_000
                while (System.currentTimeMillis() < gameStartDeadline) {
                    gameProcessStarted = device.executeShellCommand("pidof space.an3tocom.offline:game").trim().isNotEmpty()
                    if (gameProcessStarted) break
                    Thread.sleep(200)
                }
                assertTrue("the separate native game process did not start", gameProcessStarted)
                Thread.sleep(4_000)
                gameProcessRetainedAfterExit = exitNativeGameToLibrary(device)

                val firstExpectedCounter = (probe.optInt("initialCounter", 255) + 1) and 0xff
                val firstSram = readSyntheticSram(scenario, romId, firstExpectedCounter)
                assertTrue("the first game boot did not produce valid 32 KiB AN3B SRAM", firstSram.optBoolean("valid"))
                assertTrue(
                    "the first boot did not persist the expected SRAM counter " +
                        "(expected=$firstExpectedCounter actual=${firstSram.optInt("counter", -1)})",
                    firstSram.optInt("counter", -1) == firstExpectedCounter,
                )
                if (firstSram.optInt("counter") == 0) {
                    launchSyntheticSramGame(scenario, device, romTitle)
                    exitNativeGameToLibrary(device)
                    val secondSram = readSyntheticSram(scenario, romId, 1)
                    assertTrue("the second game boot did not preserve valid AN3B SRAM", secondSram.optBoolean("valid"))
                    assertTrue(
                        "the second boot did not advance the persisted SRAM counter " +
                            "(expected=1 actual=${secondSram.optInt("counter", -1)})",
                        secondSram.optInt("counter", -1) == 1,
                    )
                }
            } else {
                val recoveredSram = readSyntheticSram(scenario, romId, 1)
                assertTrue("the exact recovered ROM5 SRAM was not readable through native Sync", recoveredSram.optBoolean("valid"))
                assertTrue("the recovered synthetic SRAM counter changed before upload", recoveredSram.optInt("counter", -1) == 1)
            }

            val uploadInitiation = evalJson(
                scenario,
                """(function(){
                    var probe = window.__an3SyntheticSramSyncProbe;
                    probe.done = false;
                    probe.stage = "save-upload";
                    probe.failureCategory = "";
                    var fail = function(category) {
                      probe.done = true; probe.stage = "save-upload"; probe.failureCategory = category;
                    };
                    (async function(){
                    try {
                      var api = window.AN3NativeSync;
                      var romId = "$romId";
                      var identity = await api.gameIdentity("gba", romId);
                      var context = {kind:"save", system:"gba", romId:romId, identity:identity};
                      var localBefore = await api.storage("save", "gba", romId, identity).readAll();
                      if (localBefore.length !== 1) return fail("native-sram-missing");
                      var record = localBefore[0];
                      var bytes = record.bytes instanceof Uint8Array ? record.bytes : new Uint8Array(record.bytes || []);
                      var localHash = await (async function(value){
                        var digest = new Uint8Array(await crypto.subtle.digest("SHA-256", value));
                        return Array.from(digest).map(function(byte){ return byte.toString(16).padStart(2, "0"); }).join("");
                      })(bytes);
                      var signature = bytes.length >= 4 && String.fromCharCode.apply(null, Array.from(bytes.slice(0, 4))) === "AN3B";
                      var counter = bytes.length > 4 ? bytes[4] : -1;
                      probe.localSramVerified = bytes.byteLength === 32768 && signature && counter > 0;
                      probe.localCounter = counter;
                      if (!probe.localSramVerified) return fail("synthetic-sram-marker-invalid");
                      var remoteBefore = await api.transport.manifest("save", context);
                      var remoteSets = (remoteBefore.sets || []).filter(function(set){ return set.gameId === identity.gameId && set.romHash === identity.romHash; });
                      if (remoteSets.length || (remoteBefore.items || []).length) return fail("remote-save-preflight-not-empty");
                      var result = await api.syncGame("gba", romId, "save", function(phase){ probe.lastPhase = String(phase || ""); });
                      var remoteAfter = await api.transport.manifest("save", context);
                      var sets = (remoteAfter.sets || []).filter(function(set){ return set.gameId === identity.gameId && set.romHash === identity.romHash; });
                      var set = sets.length === 1 ? sets[0] : null;
                      var member = set && (set.members || []).find(function(item){ return Number(item.size) === bytes.byteLength && String(item.contentHash || "").toLowerCase() === localHash; });
                      if (member) {
                        var remoteBytes = await api.transport.blob("save", member, context);
                        var remoteHash = await (async function(value){
                          var digest = new Uint8Array(await crypto.subtle.digest("SHA-256", value));
                          return Array.from(digest).map(function(byte){ return byte.toString(16).padStart(2, "0"); }).join("");
                        })(remoteBytes);
                        probe.remoteSramVerified = remoteBytes.byteLength === bytes.byteLength && remoteHash === localHash
                          && String.fromCharCode.apply(null, Array.from(remoteBytes.slice(0, 4))) === "AN3B"
                          && remoteBytes[4] === counter;
                      }
                      var localAfter = await api.storage("save", "gba", romId, identity).readAll();
                      var localAfterBytes = localAfter[0] && (localAfter[0].bytes instanceof Uint8Array ? localAfter[0].bytes : new Uint8Array(localAfter[0].bytes || []));
                      var localAfterHash = localAfterBytes ? await (async function(value){
                        var digest = new Uint8Array(await crypto.subtle.digest("SHA-256", value));
                        return Array.from(digest).map(function(byte){ return byte.toString(16).padStart(2, "0"); }).join("");
                      })(localAfterBytes) : "";
                      probe.localSramUnchanged = localAfter.length === 1 && localAfterHash === localHash;
                      probe.remoteSaveUploaded = Number(result.counts && result.counts.uploaded) === 1
                        && Number(result.counts && result.counts.downloaded || 0) === 0
                        && Number(result.counts && result.counts.conflicts || 0) === 0;
                      probe.done = true;
                      probe.stage = "complete";
                    } catch (error) {
                      var message = String(error && error.message || error);
                      var category = /trust|auth|account/i.test(message) ? "auth"
                        : /connect|network|socket|timeout/i.test(message) ? "network" : "native-or-sync";
                      fail(category);
                    }
                    })();
                    return JSON.stringify({started:true});
                })()""",
            )
            assertTrue("actual SRAM upload probe did not start", uploadInitiation.optBoolean("started"))
            val uploadDeadline = System.currentTimeMillis() + 45_000
            while (System.currentTimeMillis() < uploadDeadline) {
                probe = evalJson(scenario, "JSON.stringify(window.__an3SyntheticSramSyncProbe || {done:false})")
                if (probe.optBoolean("done")) break
                Thread.sleep(250)
            }
            android.util.Log.i(
                "AN3SramSync",
                "stage=${probe.optString("stage")} failure=${probe.optString("failureCategory")} " +
                    "paired=${probe.optBoolean("paired")} gameStarted=${gameProcessStarted} " +
                    "gameProcessRetainedAfterActivityFinish=$gameProcessRetainedAfterExit " +
                    "sramVerified=${probe.optBoolean("localSramVerified")} uploaded=${probe.optBoolean("remoteSaveUploaded")} " +
                    "remoteVerified=${probe.optBoolean("remoteSramVerified")} localUnchanged=${probe.optBoolean("localSramUnchanged")} " +
                    "counter=${probe.optInt("localCounter")} lastPhase=${probe.optString("lastPhase")}",
            )
            assertTrue("actual SRAM transfer did not finish", probe.optBoolean("done"))
            assertTrue("the synthetic ROM did not generate a valid 32 KiB AN3B SRAM save", probe.optBoolean("localSramVerified"))
            assertTrue("the Mac did not receive exactly one conflict-free save set", probe.optBoolean("remoteSaveUploaded"))
            assertTrue("the Mac's native save blob failed size/SHA/marker/counter readback", probe.optBoolean("remoteSramVerified"))
            assertTrue("the phone's generated SRAM changed during upload", probe.optBoolean("localSramUnchanged"))
        } finally {
            if (!keepAppOpen) scenario.close()
        }
    }

    @Test
    fun syncsDeterministicMacSramToAndroidAndRestoresThroughCore() {
        val romId = InstrumentationRegistry.getArguments().getString("reverseRomId").orEmpty().lowercase()
        val romHash = InstrumentationRegistry.getArguments().getString("reverseRomHash").orEmpty().lowercase()
        val romTitle = InstrumentationRegistry.getArguments().getString("reverseRomTitle").orEmpty()
        assertTrue("Pass a UUID-shaped reverse-sync ROM identity", romId.matches(Regex("^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")))
        assertTrue("Pass the reverse-sync ROM SHA-256", romHash.matches(Regex("^[a-f0-9]{64}$")))
        assertTrue("Pass a synthetic AN3SYNCROM* title", romTitle.matches(Regex("^AN3SYNCROM[0-9]{1,2}$")) && romTitle.length <= 12)
        assertTrue("Pass the emulator's authenticated direct Mac endpoint", directSyncTarget.isNotEmpty())

        val scenario = ActivityScenario.launch(MainActivity::class.java)
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
        try {
            awaitWebView()
            onWebView().forceJavascriptEnabled()
            awaitNativeSync(scenario)
            connectDirectPeer(scenario)

            val initiation = evalJson(
                scenario,
                """(function(){
                    var probe = window.__an3ReverseSramProbe = {
                      done:false, stage:"init", failureCategory:"", peerConnected:false, pingOk:false,
                      localRom:false, remoteRom:false, identityExact:false,
                      localSaveEmpty:false, localStateEmpty:false, remoteStateEmpty:false,
                      remoteSaveExact:false, sourceBytesVerified:false, downloaded:false,
                      destinationHash:"", destinationCounter:-1, error:""
                    };
                    var fail = function(stage, category, error) {
                      probe.done = true; probe.stage = stage; probe.failureCategory = category;
                      probe.error = String(error || "");
                    };
                    var hashBytes = async function(bytes) {
                      var digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
                      return Array.from(digest).map(function(byte){ return byte.toString(16).padStart(2, "0"); }).join("");
                    };
                    var canonical = function(items) {
                      return JSON.stringify((items || []).map(function(item){
                        return [String(item.key || ""), String(item.extension || ""), String(item.system || ""), Number(item.size), String(item.contentHash || "").toLowerCase()];
                      }).sort(function(a,b){ return a[0].localeCompare(b[0]); }));
                    };
                    (async function(){
                      try {
                        var api = window.AN3NativeSync;
                        var status = await api.status();
                        probe.peerConnected = (status.peers || []).filter(function(peer){ return peer.state === "connected"; }).length === 1;
                        if (!probe.peerConnected) return fail("peer", "authenticated-mac-not-connected");
                        var ping = await api.request("ping", {});
                        probe.pingOk = Boolean(ping && ping.ok === true && typeof ping.peerId === "string" && ping.peerId.length > 0);
                        if (!probe.pingOk) return fail("peer", "authenticated-ping-failed");
                        var invoke = window.AN3NativeInvoke && window.AN3NativeInvoke();
                        if (typeof invoke !== "function") return fail("bridge", "native-bridge-unavailable");

                        probe.stage = "rom-preflight";
                        var localBefore = await invoke("native_sync_library_manifest", {});
                        var remoteBefore = await api.request("library-manifest", {});
                        var key = "rom:" + "$romId";
                        var localRom = (localBefore.items || []).filter(function(item){ return item.key === key; });
                        var remoteRom = (remoteBefore.items || []).filter(function(item){ return item.key === key; });
                        probe.localRom = localRom.length === 1 && localRom[0].system === "gba"
                          && Number(localRom[0].size) === 512 && String(localRom[0].contentHash || "").toLowerCase() === "$romHash";
                        probe.remoteRom = remoteRom.length === 1 && remoteRom[0].system === "gba"
                          && Number(remoteRom[0].size) === 512 && String(remoteRom[0].contentHash || "").toLowerCase() === "$romHash";
                        if (!probe.localRom || !probe.remoteRom) return fail("rom-preflight", "exact-rom-not-present-on-both-peers");

                        probe.stage = "identity-preflight";
                        var identity = await api.gameIdentity("gba", "$romId");
                        probe.identityExact = identity && identity.system === "gba" && identity.core === "mgba"
                          && String(identity.romHash || "").toLowerCase() === "$romHash";
                        if (!probe.identityExact) return fail("identity-preflight", "rom-save-identity-mismatch");
                        var context = {kind:"save", system:"gba", romId:"$romId", identity:identity};
                        var stateContext = {kind:"state", system:"gba", romId:"$romId", identity:identity};
                        var localSaveStorage = api.storage("save", "gba", "$romId", identity);
                        var localStateStorage = api.storage("state", "gba", "$romId", identity);
                        var localSaveBefore = await localSaveStorage.readAll();
                        var localStateBefore = await localStateStorage.readAll();
                        var remoteSaveBefore = await api.transport.manifest("save", context);
                        var remoteStateBefore = await api.transport.manifest("state", stateContext);
                        var remoteSets = (remoteSaveBefore.sets || []).filter(function(set){
                          return set.gameId === identity.gameId && set.romHash === identity.romHash;
                        });
                        var remoteMembers = remoteSets.length === 1 ? (remoteSets[0].members || []) : [];
                        probe.localSaveEmpty = localSaveBefore.length === 0;
                        probe.localStateEmpty = localStateBefore.length === 0;
                        probe.remoteStateEmpty = (remoteStateBefore.items || []).length === 0
                          && (remoteStateBefore.sets || []).length === 0;
                        if (!probe.localSaveEmpty || !probe.localStateEmpty || !probe.remoteStateEmpty) {
                          return fail("artifact-preflight", "existing-android-save-or-state-preserved");
                        }
                        if (remoteSets.length !== 1 || remoteMembers.length !== 1) {
                          return fail("artifact-preflight", "mac-must-have-exactly-one-source-save-member");
                        }

                        var seed = new Uint8Array(32768);
                        seed.fill(255);
                        seed.set([65, 78, 51, 66, 1]);
                        var expectedSourceHash = await hashBytes(seed);
                        var member = remoteMembers[0];
                        var sourceBytes = await api.transport.blob("save", member, context);
                        var sourceHash = await hashBytes(sourceBytes);
                        probe.sourceBytesVerified = sourceBytes.byteLength === 32768
                          && sourceHash === expectedSourceHash
                          && String.fromCharCode.apply(null, Array.from(sourceBytes.slice(0, 4))) === "AN3B"
                          && sourceBytes[4] === 1;
                        probe.remoteSaveExact = Number(member.size) === 32768
                          && String(member.contentHash || "").toLowerCase() === expectedSourceHash
                          && probe.sourceBytesVerified;
                        if (!probe.remoteSaveExact) return fail("source-preflight", "mac-source-sram-not-the-deterministic-counter-one-fixture");

                        probe.stage = "authenticated-download";
                        var result = await api.syncGame("gba", "$romId", "save");
                        probe.downloaded = Number(result.counts && result.counts.downloaded) === 1
                          && Number(result.counts && result.counts.uploaded) === 0
                          && Number(result.counts && result.counts.conflicts) === 0;
                        if (!probe.downloaded) return fail("authenticated-download", "save-transfer-was-not-one-conflict-free-download");

                        var localSaveAfter = await localSaveStorage.readAll();
                        var localBytes = localSaveAfter.length === 1
                          ? (localSaveAfter[0].bytes instanceof Uint8Array ? localSaveAfter[0].bytes : new Uint8Array(localSaveAfter[0].bytes || []))
                          : new Uint8Array();
                        probe.destinationHash = localBytes.length ? await hashBytes(localBytes) : "";
                        probe.destinationCounter = localBytes.length > 4 ? localBytes[4] : -1;
                        if (localBytes.byteLength !== 32768 || probe.destinationHash !== expectedSourceHash
                            || probe.destinationCounter !== 1) {
                          return fail("destination-readback", "android-save-bytes-do-not-match-mac-source");
                        }
                        var remoteAfter = await api.transport.manifest("save", context);
                        var remoteAfterSet = (remoteAfter.sets || []).find(function(set){
                          return set.gameId === identity.gameId && set.romHash === identity.romHash;
                        });
                        var remoteAfterMember = remoteAfterSet && (remoteAfterSet.members || []).find(function(item){ return item.key === member.key; });
                        probe.sourceUnchangedAfterDownload = Boolean(remoteAfterMember
                          && Number(remoteAfterMember.size) === Number(member.size)
                          && String(remoteAfterMember.contentHash || "").toLowerCase() === expectedSourceHash);
                        probe.unrelatedLibrariesUnchanged = canonical(localBefore.items) === canonical(await invoke("native_sync_library_manifest", {}).then(function(value){ return value.items; }))
                          && canonical(remoteBefore.items) === canonical((await api.request("library-manifest", {})).items);
                        if (!probe.sourceUnchangedAfterDownload || !probe.unrelatedLibrariesUnchanged) {
                          return fail("post-download-preflight", "source-or-unrelated-library-changed");
                        }
                        probe.done = true;
                        probe.stage = "download-verified";
                      } catch (error) {
                        var message = String(error && error.message || error);
                        var category = /trust|auth|pair|account/i.test(message) ? "auth"
                          : /connect|network|socket|timeout/i.test(message) ? "network" : "native-or-sync";
                        fail(probe.stage, category, message);
                      }
                    })();
                    return JSON.stringify({started:true});
                })()""",
            )
            assertTrue("reverse SRAM Sync probe did not start", initiation.optBoolean("started"))

            val deadline = System.currentTimeMillis() + 60_000
            var probe = JSONObject()
            while (System.currentTimeMillis() < deadline) {
                probe = evalJson(scenario, "JSON.stringify(window.__an3ReverseSramProbe || {done:false})")
                if (probe.optBoolean("done")) break
                Thread.sleep(250)
            }
            android.util.Log.i(
                "AN3ReverseSramSync",
                "stage=${probe.optString("stage")} failure=${probe.optString("failureCategory")} " +
                    "peer=${probe.optBoolean("peerConnected")} ping=${probe.optBoolean("pingOk")} " +
                    "localRom=${probe.optBoolean("localRom")} remoteRom=${probe.optBoolean("remoteRom")} " +
                    "sourceVerified=${probe.optBoolean("sourceBytesVerified")} downloaded=${probe.optBoolean("downloaded")} " +
                    "destination=${probe.optString("destinationHash")} counter=${probe.optInt("destinationCounter", -1)}",
            )
            assertTrue("reverse SRAM Sync did not finish (${probe.optString("error")})", probe.optBoolean("done"))
            assertTrue("the authenticated Mac peer was not connected and ping-verified", probe.optBoolean("peerConnected") && probe.optBoolean("pingOk"))
            assertTrue("the exact synthetic ROM was not present on both peers", probe.optBoolean("localRom") && probe.optBoolean("remoteRom") && probe.optBoolean("identityExact"))
            assertTrue("the Android save/state preflight found existing artifacts; no write was attempted", probe.optBoolean("localSaveEmpty") && probe.optBoolean("localStateEmpty") && probe.optBoolean("remoteStateEmpty"))
            assertTrue("the Mac source save did not match the exact deterministic 32 KiB counter-1 SRAM", probe.optBoolean("remoteSaveExact"))
            assertTrue("the Mac save was not downloaded exactly once with no upload or conflict", probe.optBoolean("downloaded"))
            assertTrue("the Android native SRAM bytes do not match the Mac source hash", probe.optString("destinationHash") == "b14852cd8b9871d604299af27d647603a8ccdb077e7537dcfd6f90e4659840e5" && probe.optInt("destinationCounter", -1) == 1)
            assertTrue("the Mac source or unrelated library entries changed during download", probe.optBoolean("sourceUnchangedAfterDownload") && probe.optBoolean("unrelatedLibrariesUnchanged"))

            launchSyntheticSramGame(scenario, device, romTitle)
            exitNativeGameToLibrary(device)
            val restored = readSyntheticSram(scenario, romId, 2)
            assertTrue("the Android core did not restore and advance the downloaded SRAM", restored.optBoolean("valid") && restored.optInt("counter", -1) == 2)

            val finalization = evalJson(
                scenario,
                """(function(){
                    var probe = window.__an3ReverseSramFinalizeProbe = {done:false, localRestored:false, macUnchanged:false, stateEmpty:false, error:""};
                    var hashBytes = async function(bytes) {
                      var digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
                      return Array.from(digest).map(function(byte){ return byte.toString(16).padStart(2, "0"); }).join("");
                    };
                    (async function(){
                      try {
                        var api = window.AN3NativeSync;
                        var identity = await api.gameIdentity("gba", "$romId");
                        var saveContext = {kind:"save", system:"gba", romId:"$romId", identity:identity};
                        var stateContext = {kind:"state", system:"gba", romId:"$romId", identity:identity};
                        var records = await api.storage("save", "gba", "$romId", identity).readAll();
                        var bytes = records.length === 1 ? (records[0].bytes instanceof Uint8Array ? records[0].bytes : new Uint8Array(records[0].bytes || [])) : new Uint8Array();
                        var expected = new Uint8Array(32768); expected.fill(255); expected.set([65, 78, 51, 66, 2]);
                        probe.localRestored = bytes.byteLength === expected.byteLength && await hashBytes(bytes) === await hashBytes(expected);
                        var remote = await api.transport.manifest("save", saveContext);
                        var set = (remote.sets || []).find(function(item){ return item.gameId === identity.gameId && item.romHash === identity.romHash; });
                        var member = set && (set.members || []).find(function(item){ return item.size === 32768; });
                        var macBytes = member ? await api.transport.blob("save", member, saveContext) : new Uint8Array();
                        var expectedMac = new Uint8Array(32768); expectedMac.fill(255); expectedMac.set([65, 78, 51, 66, 1]);
                        probe.macUnchanged = macBytes.byteLength === expectedMac.byteLength && await hashBytes(macBytes) === await hashBytes(expectedMac);
                        var localStates = await api.storage("state", "gba", "$romId", identity).readAll();
                        var remoteStates = await api.transport.manifest("state", stateContext);
                        probe.stateEmpty = localStates.length === 0 && (remoteStates.items || []).length === 0 && (remoteStates.sets || []).length === 0;
                        probe.done = true;
                      } catch (error) { probe.error = String(error && error.message || error); probe.done = true; }
                    })();
                    return JSON.stringify({started:true});
                })()""",
            )
            assertTrue("reverse SRAM finalization probe did not start", finalization.optBoolean("started"))
            val finalizeDeadline = System.currentTimeMillis() + 20_000
            var finalized = JSONObject()
            while (System.currentTimeMillis() < finalizeDeadline) {
                finalized = evalJson(scenario, "JSON.stringify(window.__an3ReverseSramFinalizeProbe || {done:false})")
                if (finalized.optBoolean("done")) break
                Thread.sleep(200)
            }
            assertTrue("reverse SRAM finalization probe failed (${finalized.optString("error")})", finalized.optBoolean("done"))
            assertTrue("the Android core did not persist the exact counter-2 restoration result", finalized.optBoolean("localRestored"))
            assertTrue("Android upload overwrote or altered the Mac counter-1 source", finalized.optBoolean("macUnchanged"))
            assertTrue("the reverse SRAM test unexpectedly created save states", finalized.optBoolean("stateEmpty"))
        } finally {
            if (!keepAppOpen) scenario.close()
        }
    }

    @Test
    fun downloadsAndLoadsMacSaveStateThroughAndroidGbaCore() {
        val romId = InstrumentationRegistry.getArguments().getString("restoreRomId").orEmpty().lowercase()
        val romHash = InstrumentationRegistry.getArguments().getString("restoreRomHash").orEmpty().lowercase()
        val romTitle = InstrumentationRegistry.getArguments().getString("restoreRomTitle").orEmpty()
        val romBase64 = InstrumentationRegistry.getArguments().getString("restoreRomBase64").orEmpty()
        val stateHash = InstrumentationRegistry.getArguments().getString("restoreStateHash").orEmpty().lowercase()
        val stateSize = InstrumentationRegistry.getArguments().getString("restoreStateSize")?.toLongOrNull() ?: 0L
        assertTrue("Pass a UUID-shaped restore ROM identity", romId.matches(Regex("^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")))
        assertTrue("Pass the generated GBA ROM SHA-256", romHash.matches(Regex("^[a-f0-9]{64}$")))
        assertTrue("Pass a synthetic AN3SYNCROM* title", romTitle.matches(Regex("^AN3SYNCROM[0-9]{1,2}$")) && romTitle.length <= 12)
        assertTrue("Pass generated ROM bytes", romBase64.isNotEmpty())
        assertTrue("Pass the Mac slot-1 state SHA-256 and size", stateHash.matches(Regex("^[a-f0-9]{64}$")) && stateSize > 0)
        assertTrue("Pass the authenticated Mac endpoint and temporary pairing code", directSyncTarget.isNotEmpty() && directSyncCode.isNotEmpty())

        val scenario = ActivityScenario.launch(MainActivity::class.java)
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
        var gameActive = false
        try {
            awaitWebView()
            onWebView().forceJavascriptEnabled()
            awaitNativeSync(scenario)
            val connection = connectDirectPeer(scenario)
            assertTrue("the Mac peer did not authenticate through the direct LAN path", connection.optBoolean("connected") && connection.optBoolean("pingOk"))

            val initiation = evalJson(
                scenario,
                """(function(){
                    window.__an3StateRestoreProbe = {
                      done:false, stage:"connect", peer:false, ping:false, romExact:false,
                      localArtifactsEmpty:false, sourceExact:false, downloaded:false,
                      localStateExact:false, sourceUnchanged:false, error:""
                    };
                    var probe = window.__an3StateRestoreProbe;
                    var fail = function(stage, error) {
                      probe.stage = stage; probe.error = String(error || ""); probe.done = true;
                    };
                    var hashBytes = async function(bytes) {
                      var digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
                      return Array.from(digest).map(function(byte){ return byte.toString(16).padStart(2, "0"); }).join("");
                    };
                    (async function(){
                      try {
                        var api = window.AN3NativeSync;
                        api.setMode("guest");
                        var initial = await api.init();
                        var remembered = (initial.peers || []).find(function(peer){ return Boolean(peer.deviceId) && peer.state === "connected"; });
                        if (!remembered) return fail("connect", "the authenticated Mac peer was not retained after pairing");
                        var deadline = Date.now() + 20_000;
                        while (Date.now() < deadline) {
                          var status = await api.status();
                          probe.peer = (status.peers || []).some(function(peer){ return peer.state === "connected"; });
                          if (probe.peer) break;
                          await new Promise(function(resolve){ setTimeout(resolve, 250); });
                        }
                        if (!probe.peer) return fail("connect", "remembered Mac peer did not reconnect");
                        var ping = await api.request("ping", {});
                        probe.ping = Boolean(ping && ping.ok === true && typeof ping.peerId === "string");
                        if (!probe.ping) return fail("connect", "authenticated Mac ping failed");

                        probe.stage = "rom-preflight";
                        var invoke = window.AN3NativeInvoke && window.AN3NativeInvoke();
                        if (typeof invoke !== "function") return fail("rom-preflight", "Android native bridge unavailable");
                        var localManifest = await invoke("native_sync_library_manifest", {});
                        var remoteManifest = await api.request("library-manifest", {});
                        var key = "rom:" + "$romId";
                        var localMatches = (localManifest.items || []).filter(function(item){ return item.key === key; });
                        var remoteMatches = (remoteManifest.items || []).filter(function(item){ return item.key === key; });
                        var exactLocal = localMatches.length === 1 && Number(localMatches[0].size) === 512
                          && String(localMatches[0].contentHash || "").toLowerCase() === "$romHash";
                        var exactRemote = remoteMatches.length === 1 && Number(remoteMatches[0].size) === 512
                          && String(remoteMatches[0].contentHash || "").toLowerCase() === "$romHash";
                        if ((localMatches.length !== 0 && !exactLocal) || !exactRemote) {
                          return fail("rom-preflight", "selected lawful GBA ROM identity did not match on both peers");
                        }
                        if (!exactLocal) {
                          var written = await invoke("native_sync_library_write_chunk", {payload:{
                            romId:"$romId", extension:"gba", size:512, contentHash:"$romHash",
                            offset:0, data:"$romBase64"
                          }});
                          if (!written || written.complete !== true) return fail("rom-import", "Android did not finalize the exact ROM");
                          if (!window.AN3OfflineLibrary || typeof window.AN3OfflineLibrary.put !== "function") {
                            return fail("rom-import", "Android library record store unavailable");
                          }
                          await window.AN3OfflineLibrary.put({id:"$romId", title:"$romTitle", name:"$romId.gba",
                            system:"gba", size:512, romHash:"$romHash", addedAt:Date.now(),
                            nativeRomId:"$romId", nativePath:"/native-rom/$romId.gba"});
                          await globalThis.AN3RerenderLibrary?.();
                        }
                        probe.romExact = true;

                        probe.stage = "artifact-preflight";
                        var identity = await api.gameIdentity("gba", "$romId");
                        if (identity.system !== "gba" || identity.core !== "mgba"
                            || String(identity.romHash || "").toLowerCase() !== "$romHash") {
                          return fail("artifact-preflight", "native save identity does not match the selected GBA ROM");
                        }
                        var context = {kind:"state", system:"gba", romId:"$romId", identity:identity};
                        var localSaves = await api.storage("save", "gba", "$romId", identity).readAll();
                        var localStates = await api.storage("state", "gba", "$romId", identity).readAll();
                        var remoteStates = await api.transport.manifest("state", context);
                        var sourceItems = (remoteStates.items || []).filter(function(item){ return item.path === "/data/states/slot1.state"; });
                        probe.localArtifactsEmpty = localSaves.length === 0 && localStates.length === 0;
                        if (!probe.localArtifactsEmpty) return fail("artifact-preflight", "Android already has save/state data for this test identity");
                        if ((remoteStates.items || []).length !== 1 || sourceItems.length !== 1
                            || Number(sourceItems[0].size) !== $stateSize
                            || String(sourceItems[0].contentHash || "").toLowerCase() !== "$stateHash") {
                          return fail("source-preflight", "Mac slot-1 state does not match the exact generated fixture");
                        }
                        var sourceBytes = await api.transport.blob("state", sourceItems[0], context);
                        var sourceHash = await hashBytes(sourceBytes);
                        var marker = -1;
                        for (var i = 0; i + 5 < sourceBytes.length; i++) {
                          if (sourceBytes[i] === 65 && sourceBytes[i+1] === 78 && sourceBytes[i+2] === 51
                              && sourceBytes[i+3] === 66) { marker = i; break; }
                        }
                        probe.sourceExact = sourceBytes.byteLength === $stateSize && sourceHash === "$stateHash"
                          && marker >= 0 && sourceBytes[marker+4] === 0;
                        if (!probe.sourceExact) return fail("source-preflight", "state bytes or embedded counter-0 marker failed verification");

                        probe.stage = "authenticated-download";
                        var result = await api.syncGame("gba", "$romId", "state");
                        probe.downloaded = Number(result.counts && result.counts.downloaded) === 1
                          && Number(result.counts && result.counts.uploaded || 0) === 0
                          && Number(result.counts && result.counts.conflicts || 0) === 0;
                        if (!probe.downloaded) return fail("authenticated-download", "state sync was not exactly one conflict-free download");
                        var localAfter = await api.storage("state", "gba", "$romId", identity).readAll();
                        var received = localAfter.length === 1 ? localAfter[0] : null;
                        var receivedBytes = received && received.state ? new Uint8Array(await received.state.arrayBuffer()) : new Uint8Array();
                        probe.localStateExact = localAfter.length === 1 && received.path === "/data/states/slot1.state"
                          && receivedBytes.byteLength === $stateSize && await hashBytes(receivedBytes) === "$stateHash";
                        var remoteAfter = await api.transport.manifest("state", context);
                        var sourceAfter = (remoteAfter.items || []).find(function(item){ return item.path === "/data/states/slot1.state"; });
                        probe.sourceUnchanged = Boolean(sourceAfter && Number(sourceAfter.size) === $stateSize
                          && String(sourceAfter.contentHash || "").toLowerCase() === "$stateHash");
                        if (!probe.localStateExact || !probe.sourceUnchanged) {
                          return fail("post-download", "received bytes or Mac source changed");
                        }
                        probe.stage = "transfer-verified";
                        probe.done = true;
                      } catch (error) {
                        fail(probe.stage, error && error.message || error);
                      }
                    })();
                    return JSON.stringify({started:true});
                })()""",
            )
            assertTrue("state-restore transfer probe did not start", initiation.optBoolean("started"))
            val transferDeadline = System.currentTimeMillis() + 60_000
            var probe = JSONObject()
            while (System.currentTimeMillis() < transferDeadline) {
                probe = evalJson(scenario, "JSON.stringify(window.__an3StateRestoreProbe || {done:false})")
                if (probe.optBoolean("done")) break
                Thread.sleep(200)
            }
            android.util.Log.i(
                "AN3StateRestore",
                "stage=" + probe.optString("stage") + " peer=" + probe.optBoolean("peer") +
                    " ping=" + probe.optBoolean("ping") + " rom=" + probe.optBoolean("romExact") +
                    " source=" + probe.optBoolean("sourceExact") + " downloaded=" + probe.optBoolean("downloaded") +
                    " local=" + probe.optBoolean("localStateExact") + " error=" + probe.optString("error"),
            )
            assertTrue("state-restore transfer failed (" + probe.optString("error") + ")", probe.optBoolean("done"))
            assertTrue("the authenticated Mac peer was not connected and ping-verified", probe.optBoolean("peer") && probe.optBoolean("ping"))
            assertTrue("the exact lawful GBA ROM was not present on both peers", probe.optBoolean("romExact"))
            assertTrue("Android already had save/state data for this test identity", probe.optBoolean("localArtifactsEmpty"))
            assertTrue("the Mac slot-1 state did not match the generated fixture with counter 0", probe.optBoolean("sourceExact"))
            assertTrue("the Mac state was not downloaded exactly once without upload/conflict", probe.optBoolean("downloaded"))
            assertTrue("the received state hash or unchanged Mac source failed verification", probe.optBoolean("localStateExact") && probe.optBoolean("sourceUnchanged"))

            gameActive = true
            launchSyntheticSramGame(scenario, device, romTitle)
            exitNativeGameToLibrary(device)
            gameActive = false
            val firstBoot = readSyntheticSram(scenario, romId, 0)
            assertTrue("the untouched GBA fixture did not persist its initial counter 0", firstBoot.optInt("counter", -1) == 0)

            gameActive = true
            launchSyntheticSramGame(scenario, device, romTitle)
            exitNativeGameToLibrary(device)
            gameActive = false
            val secondBoot = readSyntheticSram(scenario, romId, 1)
            assertTrue("the second boot did not advance the normal save to counter 1", secondBoot.optInt("counter", -1) == 1)

            gameActive = true
            launchSyntheticSramGame(scenario, device, romTitle)
            assertTrue("the Quick Load control was unavailable", device.wait(Until.hasObject(By.text("Save")), 5_000))
            device.findObject(By.text("Save")).click()
            assertTrue("the save menu did not offer Quick Load", device.wait(Until.hasObject(By.text("Quick Load…")), 5_000))
            device.findObject(By.text("Quick Load…")).click()
            assertTrue("Quick Load did not expose slot 1", device.wait(Until.hasObject(By.text("Slot 1")), 5_000))
            device.findObject(By.text("Slot 1")).click()
            device.waitForIdle()
            exitNativeGameToLibrary(device)
            gameActive = false
            val restored = readSyntheticSram(scenario, romId, 0)
            android.util.Log.i(
                "AN3StateRestore",
                "first=" + firstBoot.optInt("counter") + " second=" + secondBoot.optInt("counter") +
                    " restored=" + restored.optInt("counter"),
            )
            assertTrue("the transferred slot-1 state did not restore its counter-0 SRAM in the core", restored.optBoolean("valid") && restored.optInt("counter", -1) == 0)

            val finalization = evalJson(
                scenario,
                """(async function(){
                    var api = window.AN3NativeSync;
                    var identity = await api.gameIdentity("gba", "$romId");
                    var states = await api.storage("state", "gba", "$romId", identity).readAll();
                    var record = states.find(function(item){ return item.path === "/data/states/slot1.state"; });
                    var bytes = record && record.state ? new Uint8Array(await record.state.arrayBuffer()) : new Uint8Array();
                    var digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
                    var hash = Array.from(digest).map(function(byte){ return byte.toString(16).padStart(2, "0"); }).join("");
                    return JSON.stringify({stateStillExact:Boolean(record)
                      && bytes.byteLength === $stateSize && hash === "$stateHash"});
                })()""",
            )
            assertTrue("the Android core changed the downloaded source state bytes", finalization.optBoolean("stateStillExact"))
        } finally {
            if (gameActive) runCatching { exitNativeGameToLibrary(device) }
            if (!keepAppOpen) scenario.close()
        }
    }

    @Test
    fun syncsNativeSaveStatesInBothDirections() {
        val romId = InstrumentationRegistry.getArguments().getString("stateRomId").orEmpty().lowercase()
        val romHash = InstrumentationRegistry.getArguments().getString("stateRomHash").orEmpty().lowercase()
        val romTitle = InstrumentationRegistry.getArguments().getString("stateRomTitle").orEmpty()
        val romBase64 = InstrumentationRegistry.getArguments().getString("stateRomBase64").orEmpty()
        val macStateHash = InstrumentationRegistry.getArguments().getString("macStateHash").orEmpty().lowercase()
        val macStateSize = InstrumentationRegistry.getArguments().getString("macStateSize")?.toLongOrNull() ?: 0L
        val androidStateHash = InstrumentationRegistry.getArguments().getString("androidStateHash").orEmpty().lowercase()
        val androidStateSize = InstrumentationRegistry.getArguments().getString("androidStateSize")?.toLongOrNull() ?: 0L
        val androidStateGzipBase64 = InstrumentationRegistry.getArguments().getString("androidStateGzipBase64").orEmpty()
        val androidStateBase64 = runCatching {
            val compressed = android.util.Base64.decode(androidStateGzipBase64, android.util.Base64.NO_WRAP)
            val bytes = java.util.zip.GZIPInputStream(java.io.ByteArrayInputStream(compressed)).use { it.readBytes() }
            android.util.Base64.encodeToString(bytes, android.util.Base64.NO_WRAP)
        }.getOrDefault("")
        assertTrue("Pass a fresh synthetic ROM UUID", romId.matches(Regex("^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")))
        assertTrue("Pass the generated GBA ROM SHA-256", romHash.matches(Regex("^[a-f0-9]{64}$")))
        assertTrue("Pass a synthetic GBA homebrew title", romTitle.matches(Regex("^AN3SYNCROM[0-9]{1,2}$")) && romTitle.length <= 12)
        assertTrue("Pass the generated ROM bytes", romBase64.isNotEmpty())
        assertTrue("Pass the generated Mac state SHA-256 and size", macStateHash.matches(Regex("^[a-f0-9]{64}$")) && macStateSize > 0)
        assertTrue("Pass a distinct generated slot-2 state SHA-256, size, and compressed bytes", androidStateHash.matches(Regex("^[a-f0-9]{64}$")) && androidStateSize > 0 && androidStateHash != macStateHash && androidStateBase64.isNotEmpty())

        val scenario = ActivityScenario.launch(MainActivity::class.java)
        try {
            awaitWebView()
            onWebView().forceJavascriptEnabled()
            awaitNativeSync(scenario)
            connectDirectPeer(scenario)

            val setup = evalJson(
                scenario,
                """(function(){
                    window.__an3StateSyncSetup = {done:false, error:"", romInstalled:false, sourceExact:false,
                      localArtifactsEmpty:false, remoteSaveEmpty:false, sourceStateVerified:false, androidStateStaged:false};
                    (async function(){
                    var probe = window.__an3StateSyncSetup;
                    try {
                      var api = window.AN3NativeSync;
                      var invoke = window.AN3NativeInvoke && window.AN3NativeInvoke();
                      if (typeof invoke !== "function") throw new Error("Android native invoke bridge is unavailable");
                      var localBefore = await invoke("native_sync_library_manifest", {});
                      var remoteBefore = await api.request("library-manifest", {});
                        var localMatches = (localBefore.items || []).filter(function(item){ return item.key === "rom:$romId"; });
                        var remoteMatches = (remoteBefore.items || []).filter(function(item){ return item.key === "rom:$romId"; });
                        probe.localRomMatches = localMatches.length;
                        probe.remoteRomMatches = remoteMatches.length;
                        probe.remoteRom = remoteMatches[0] || null;
                        var localRom = localMatches[0] || null;
                        var localRomMatches = localMatches.length === 1
                          && Number(localRom.size) === 512
                          && String(localRom.contentHash || "").toLowerCase() === "$romHash";
                        if ((localMatches.length !== 0 && !localRomMatches) || remoteMatches.length !== 1
                            || Number(remoteMatches[0].size) !== 512
                            || String(remoteMatches[0].contentHash || "").toLowerCase() !== "$romHash") {
                          throw new Error("test ROM preflight mismatch: " + JSON.stringify({
                            localMatches:localMatches.length, remoteMatches:remoteMatches.length,
                            remote:remoteMatches[0] || null
                          }));
                        }
                        if (!localRomMatches) {
                          var written = await invoke("native_sync_library_write_chunk", {payload:{romId:"$romId", extension:"gba", size:512,
                            contentHash:"$romHash", offset:0, data:"$romBase64"}});
                          if (!written || written.complete !== true) throw new Error("Android ROM import did not finalize");
                        }
                        if (!window.AN3OfflineLibrary || typeof window.AN3OfflineLibrary.put !== "function") {
                          throw new Error("Android library record store is unavailable");
                        }
                        await window.AN3OfflineLibrary.put({id:"$romId", title:"$romTitle", name:"$romId.gba",
                          system:"gba", size:512, romHash:"$romHash", addedAt:Date.now(), nativeRomId:"$romId",
                          nativePath:"/native-rom/$romId.gba"});
                        await globalThis.AN3RerenderLibrary?.();
                        probe.romInstalled = true;

                        var identity = await api.gameIdentity("gba", "$romId");
                        var context = {kind:"save", system:"gba", romId:"$romId", identity:identity};
                        var stateContext = {kind:"state", system:"gba", romId:"$romId", identity:identity};
                        var localSave = await api.storage("save", "gba", "$romId", identity).readAll();
                        var localState = await api.storage("state", "gba", "$romId", identity).readAll();
                        var remoteSave = await api.transport.manifest("save", context);
                        var remoteState = await api.transport.manifest("state", stateContext);
                        var sourceItems = (remoteState.items || []).filter(function(item){ return item.path === "/data/states/slot1.state"; });
                        probe.identity = identity;
                        probe.localSaveCount = localSave.length;
                        probe.localStateCount = localState.length;
                        probe.remoteSaveCount = (remoteSave.items || []).length;
                        probe.remoteSaveSetCount = (remoteSave.sets || []).length;
                        probe.remoteStateCount = (remoteState.items || []).length;
                        probe.sourceStateCount = sourceItems.length;
                        probe.localArtifactsEmpty = localSave.length === 0 && localState.length === 0;
                        probe.remoteSaveEmpty = (remoteSave.items || []).length === 0 && (remoteSave.sets || []).length === 0;
                        if (!probe.localArtifactsEmpty || !probe.remoteSaveEmpty || sourceItems.length !== 1
                            || (remoteState.items || []).length !== 1) {
                          throw new Error("test artifact preflight mismatch: " + JSON.stringify({
                            localSave:localSave.length, localState:localState.length,
                            remoteSave:(remoteSave.items || []).length,
                            remoteSaveSets:(remoteSave.sets || []).length,
                            remoteStates:(remoteState.items || []).map(function(item){ return item.path; })
                          }));
                        }
                        var source = await api.transport.blob("state", sourceItems[0], stateContext);
                        var digest = new Uint8Array(await crypto.subtle.digest("SHA-256", source));
                        var sourceHash = Array.from(digest).map(function(byte){ return byte.toString(16).padStart(2, "0"); }).join("");
                        probe.sourceStateVerified = source.byteLength === $macStateSize && sourceHash === "$macStateHash";
                        probe.sourceExact = identity.system === "gba" && identity.core === "mgba"
                          && String(identity.romHash || "").toLowerCase() === "$romHash";
                        probe.sourceStateSize = source.byteLength;
                        probe.sourceStateHash = sourceHash;
                        if (!probe.sourceStateVerified || !probe.sourceExact) throw new Error("authenticated Mac save-state bytes or game identity did not match the generated fixture");

                        var androidBinary = atob("$androidStateBase64");
                        var androidBytes = new Uint8Array(androidBinary.length);
                        for (var index = 0; index < androidBinary.length; index++) androidBytes[index] = androidBinary.charCodeAt(index);
                        var androidDigest = new Uint8Array(await crypto.subtle.digest("SHA-256", androidBytes));
                        var androidHash = Array.from(androidDigest).map(function(byte){ return byte.toString(16).padStart(2, "0"); }).join("");
                        if (androidBytes.byteLength !== $androidStateSize || androidHash !== "$androidStateHash" || androidHash === sourceHash) {
                          throw new Error("slot-2 save-state fixture failed size/SHA-256 preflight");
                        }
                        await api.storage("state", "gba", "$romId", identity).put({
                          path:"/data/states/slot2.state",
                          state:new Blob([androidBytes], {type:"application/octet-stream"})
                        });
                        var staged = await api.storage("state", "gba", "$romId", identity).readAll();
                        var stagedSlot = staged.find(function(item){ return item.path === "/data/states/slot2.state"; });
                        var stagedBytes = stagedSlot && stagedSlot.state ? new Uint8Array(await stagedSlot.state.arrayBuffer()) : new Uint8Array();
                        var stagedDigest = new Uint8Array(await crypto.subtle.digest("SHA-256", stagedBytes));
                        var stagedHash = Array.from(stagedDigest).map(function(byte){ return byte.toString(16).padStart(2, "0"); }).join("");
                        probe.androidStateStaged = staged.length === 1 && stagedBytes.byteLength === $androidStateSize && stagedHash === "$androidStateHash";
                        if (!probe.androidStateStaged) throw new Error("Android native save-state storage did not preserve the generated slot-2 bytes");
                        probe.done = true;
                      } catch (error) { probe.error = String(error && error.message || error); probe.done = true; }
                    })();
                    return JSON.stringify({started:true});
                })()""",
            )
            assertTrue("save-state setup probe did not start", setup.optBoolean("started"))
            val setupDeadline = System.currentTimeMillis() + 45_000
            var setupResult = JSONObject()
            while (System.currentTimeMillis() < setupDeadline) {
                setupResult = evalJson(scenario, "JSON.stringify(window.__an3StateSyncSetup || {done:false})")
                if (setupResult.optBoolean("done")) break
                Thread.sleep(150)
            }
            assertTrue("save-state setup failed (${setupResult.optString("error")})", setupResult.optBoolean("done"))
            assertTrue("the exact generated ROM was not safely installed on Android (${setupResult})", setupResult.optBoolean("romInstalled") && setupResult.optBoolean("sourceExact"))
            assertTrue("existing Android saves/states or a Mac save were found; no artifact write was attempted", setupResult.optBoolean("localArtifactsEmpty") && setupResult.optBoolean("remoteSaveEmpty"))
            assertTrue("the Mac state blob failed authenticated size/SHA-256 verification", setupResult.optBoolean("sourceStateVerified"))
            assertTrue("Android native storage failed to preserve the generated slot-2 state (${setupResult})", setupResult.optBoolean("androidStateStaged"))
            android.util.Log.i("AN3StateSync", "stage=preflight-complete macSourceVerified=true androidSlot2Verified=true")

            val syncInitiation = evalJson(
                scenario,
                """(function(){
                    window.__an3StateSyncTransfer = {done:false, error:"", uploaded:0, downloaded:0, conflicts:0,
                      sourcePresent:false, localMatches:false, remoteMatches:false};
                    (async function(){
                      var probe = window.__an3StateSyncTransfer;
                      try {
                        var api = window.AN3NativeSync;
                        var result = await api.syncGame("gba", "$romId", "state");
                        probe.uploaded = Number(result.counts && result.counts.uploaded || 0);
                        probe.downloaded = Number(result.counts && result.counts.downloaded || 0);
                        probe.conflicts = Number(result.counts && result.counts.conflicts || 0);
                        var identity = await api.gameIdentity("gba", "$romId");
                        var context = {kind:"state", system:"gba", romId:"$romId", identity:identity};
                        var local = await api.storage("state", "gba", "$romId", identity).readAll();
                        var remote = await api.transport.manifest("state", context);
                        var local1 = local.find(function(item){ return item.path === "/data/states/slot1.state"; });
                        var local2 = local.find(function(item){ return item.path === "/data/states/slot2.state"; });
                        var local1Bytes = local1 && local1.state ? new Uint8Array(await local1.state.arrayBuffer()) : new Uint8Array();
                        var local2Bytes = local2 && local2.state ? new Uint8Array(await local2.state.arrayBuffer()) : new Uint8Array();
                        var hashBytes = async function(bytes){
                          var digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
                          return Array.from(digest).map(function(byte){ return byte.toString(16).padStart(2, "0"); }).join("");
                        };
                        var remote1 = (remote.items || []).find(function(item){ return item.path === "/data/states/slot1.state"; });
                        var remote2 = (remote.items || []).find(function(item){ return item.path === "/data/states/slot2.state"; });
                        var remote2Blob = remote2 ? await api.transport.blob("state", remote2, context) : new Uint8Array();
                        var remote2Bytes = new Uint8Array(remote2Blob);
                        var remote2Hash = await hashBytes(remote2Bytes);
                        probe.localMatches = local.length === 2 && local1 && local2
                          && await hashBytes(local1Bytes) === "$macStateHash"
                          && await hashBytes(local2Bytes) === "$androidStateHash";
                        probe.remoteMatches = (remote.items || []).length === 2 && remote1 && remote2
                          && String(remote1.contentHash || "").toLowerCase() === "$macStateHash"
                          && String(remote2.contentHash || "").toLowerCase() === "$androidStateHash"
                          && remote2Bytes.byteLength === $androidStateSize && remote2Hash === "$androidStateHash";
                        probe.sourcePresent = probe.localMatches && probe.remoteMatches;
                        probe.done = true;
                      } catch (error) { probe.error = String(error && error.message || error); probe.done = true; }
                    })();
                    return JSON.stringify({started:true});
                })()""",
            )
            assertTrue("save-state transfer probe did not start", syncInitiation.optBoolean("started"))
            val syncDeadline = System.currentTimeMillis() + 60_000
            var syncResult = JSONObject()
            while (System.currentTimeMillis() < syncDeadline) {
                syncResult = evalJson(scenario, "JSON.stringify(window.__an3StateSyncTransfer || {done:false})")
                if (syncResult.optBoolean("done")) break
                Thread.sleep(150)
            }
            android.util.Log.i(
                "AN3StateSync",
                "uploaded=${syncResult.optInt("uploaded")} downloaded=${syncResult.optInt("downloaded")} " +
                    "conflicts=${syncResult.optInt("conflicts")} verified=${syncResult.optBoolean("sourcePresent")} " +
                    "error=${syncResult.optString("error")}",
            )
            assertTrue("save-state transfer failed (${syncResult.optString("error")})", syncResult.optBoolean("done"))
            assertTrue("the distinct Mac and Android native states did not sync exactly once in each direction", syncResult.optInt("uploaded") == 1 && syncResult.optInt("downloaded") == 1 && syncResult.optInt("conflicts") == 0)
            assertTrue("the transferred Mac slot-1 and Android slot-2 state hashes did not match on both peers", syncResult.optBoolean("sourcePresent"))
            android.util.Log.i("AN3StateSync", "stage=transfer-verified uploaded=${syncResult.optInt("uploaded")} downloaded=${syncResult.optInt("downloaded")} conflicts=${syncResult.optInt("conflicts")} sourcePresent=${syncResult.optBoolean("sourcePresent")}")
        } finally {
            if (!keepAppOpen) scenario.close()
        }
    }

    @Test
    fun syncsIdenticalSelectedRomAndEmptyArtifactsWithoutWrites() {
        val targetHash = InstrumentationRegistry.getArguments()
            .getString("selectedLibraryHash")
            .orEmpty()
            .lowercase()
        assertTrue("Pass the synthetic ROM SHA-256 as selectedLibraryHash", targetHash.matches(Regex("^[a-f0-9]{64}$")))

        val scenario = ActivityScenario.launch(MainActivity::class.java)
        try {
            awaitWebView()
            onWebView().forceJavascriptEnabled()
            awaitNativeSync(scenario)
            val initiation = evalJson(
                scenario,
                """(function(){
                    var probe = window.__an3EmptyArtifactSyncProbe = {
                      done:false, stage:"init", failureCategory:"", connected:false, pingOk:false,
                      targetUnique:false, emptyPreflight:false, saveComplete:false, stateComplete:false,
                      libraryTransferNoop:false, noWrites:false, lastKind:"", lastSubstate:""
                    };
                    var fail = function(stage, category) {
                      probe.done = true; probe.stage = stage; probe.failureCategory = category;
                    };
                    (async function(){
                      try {
                        var api = window.AN3NativeSync;
                        var initial = await api.init();
                        var remembered = (initial.peers || []).filter(function(peer){ return Boolean(peer.deviceId); });
                        if (!remembered.length) return fail("peer", "no-remembered-peer");
                        var advertisements = await api.discover();
                        var peer = remembered.find(function(rememberedPeer){
                          return (advertisements || []).some(function(item){ return item.deviceId === rememberedPeer.deviceId; });
                        });
                        if (!peer) return fail("discovery", "peer-not-advertised");
                        if (peer.state !== "connected") await api.reconnect(peer.deviceId);
                        var deadline = Date.now() + 18_000;
                        while (Date.now() < deadline) {
                          var status = await api.status();
                          probe.connected = (status.peers || []).some(function(item){ return item.state === "connected"; });
                          if (probe.connected) break;
                          await new Promise(function(resolve){ setTimeout(resolve, 250); });
                        }
                        if (!probe.connected) return fail("reconnect", "not-connected");
                        var ping = await api.request("ping", {});
                        probe.pingOk = Boolean(ping && ping.ok === true && typeof ping.peerId === "string" && ping.peerId.length > 0);
                        if (!probe.pingOk) return fail("ping", "unauthenticated-response");
                        var invoke = window.AN3NativeInvoke && window.AN3NativeInvoke();
                        if (typeof invoke !== "function") return fail("bridge", "native-bridge-unavailable");
                        var library = await invoke("native_sync_library_manifest", {});
                        var targets = (library.items || []).filter(function(item){
                          return String(item.contentHash || "").toLowerCase() === "$targetHash";
                        });
                        probe.targetUnique = targets.length === 1 && targets[0].system === "gba";
                        if (!probe.targetUnique) return fail("rom", "selected-rom-not-unique");
                        var rom = targets[0];
                        var remoteLibrary = await api.request("library-manifest", {});
                        var remoteRom = (remoteLibrary.items || []).filter(function(item){ return item.key === rom.key; });
                        if (remoteRom.length !== 1 || remoteRom[0].size !== rom.size
                            || String(remoteRom[0].contentHash || "").toLowerCase() !== "$targetHash") {
                          return fail("rom", "peers-do-not-have-identical-selected-rom");
                        }
                        var identity = await api.gameIdentity("gba", rom.romId);
                        var snapshots = {};
                        for (var kind of ["save", "state"]) {
                          var context = {kind:kind, system:"gba", romId:rom.romId, identity:identity};
                          var local = await invoke("native_sync_storage_read", {payload:context});
                          var remote = await api.request("manifest", {kind:kind, context:context});
                          if (!local || !Array.isArray(local.records) || !remote || !Array.isArray(remote.items)) {
                            return fail("preflight-" + kind, "invalid-artifact-manifest");
                          }
                          snapshots[kind] = {local:local.records.length, remote:remote.items.length};
                          if (local.records.length || remote.items.length) return fail("preflight-" + kind, "existing-artifacts-preserved");
                        }
                        probe.emptyPreflight = true;
                        probe.stage = "selected-library-sync";
                        probe.lastKind = "library";
                        var libraryResult = await api.syncLibrary({keys:[rom.key], onState:function(state){
                          probe.lastSubstate = String(state && state.phase || "");
                        }});
                        probe.libraryTransferNoop = Boolean(libraryResult && libraryResult.transfers
                          && libraryResult.transfers.length === 1 && libraryResult.transfers[0].key === rom.key
                          && libraryResult.transfers[0].direction === "none"
                          && Number(libraryResult.counts && libraryResult.counts.uploaded || 0) === 0
                          && Number(libraryResult.counts && libraryResult.counts.downloaded || 0) === 0
                          && Number(libraryResult.counts && libraryResult.counts.conflicts || 0) === 0);
                        var artifacts = libraryResult && libraryResult.artifacts || [];
                        probe.saveComplete = artifacts.some(function(item){
                          var counts = item.result && item.result.counts || {};
                          return item.kind === "save" && Number(counts.uploaded || 0) === 0
                            && Number(counts.downloaded || 0) === 0 && Number(counts.conflicts || 0) === 0;
                        });
                        probe.stateComplete = artifacts.some(function(item){
                          var counts = item.result && item.result.counts || {};
                          return item.kind === "state" && Number(counts.uploaded || 0) === 0
                            && Number(counts.downloaded || 0) === 0 && Number(counts.conflicts || 0) === 0;
                        });
                        probe.stage = "post-sync-artifact-verification";
                        var after = {};
                        for (var kind of ["save", "state"]) {
                          var context = {kind:kind, system:"gba", romId:rom.romId, identity:identity};
                          var local = await invoke("native_sync_storage_read", {payload:context});
                          var remote = await api.request("manifest", {kind:kind, context:context});
                          after[kind] = Boolean(local && Array.isArray(local.records) && local.records.length === 0
                            && remote && Array.isArray(remote.items) && remote.items.length === 0);
                        }
                        probe.noWrites = after.save && after.state;
                        probe.done = true;
                        probe.stage = "complete";
                      } catch (error) {
                        var message = String(error && error.message || error);
                        var category = /trust|auth|account/i.test(message) ? "auth"
                          : /connect|network|socket|timeout/i.test(message) ? "network" : "native-or-sync";
                        fail(probe.lastKind ? "sync-" + probe.lastKind : probe.stage, category);
                      }
                    })();
                    return JSON.stringify({started:true});
                })()""",
            )
            assertTrue("empty-artifact sync probe did not start", initiation.optBoolean("started"))

            val deadline = System.currentTimeMillis() + 60_000
            var probe = JSONObject()
            while (System.currentTimeMillis() < deadline) {
                probe = evalJson(scenario, "JSON.stringify(window.__an3EmptyArtifactSyncProbe || {done:false})")
                if (probe.optBoolean("done")) break
                Thread.sleep(250)
            }
            android.util.Log.i(
                "AN3LibrarySync",
                "artifactStage=${probe.optString("stage")} failure=${probe.optString("failureCategory")} " +
                    "targetUnique=${probe.optBoolean("targetUnique")} emptyPreflight=${probe.optBoolean("emptyPreflight")} " +
                    "libraryTransferNoop=${probe.optBoolean("libraryTransferNoop")} " +
                    "saveComplete=${probe.optBoolean("saveComplete")} stateComplete=${probe.optBoolean("stateComplete")} " +
                    "noWrites=${probe.optBoolean("noWrites")} lastKind=${probe.optString("lastKind")} " +
                    "lastSubstate=${probe.optString("lastSubstate")}",
            )
            assertTrue("empty-artifact sync did not finish", probe.optBoolean("done"))
            assertTrue("selected synthetic ROM was not uniquely identified", probe.optBoolean("targetUnique"))
            assertTrue("test refused an existing save/state artifact; it was left unchanged", probe.optBoolean("emptyPreflight"))
            assertTrue("selected library sync did not recognize the identical ROM as a no-op", probe.optBoolean("libraryTransferNoop"))
            assertTrue("save/state sync did not complete without transfers", probe.optBoolean("saveComplete") && probe.optBoolean("stateComplete"))
            assertTrue("empty save/state manifests changed during verification", probe.optBoolean("noWrites"))
        } finally {
            if (!keepAppOpen) scenario.close()
        }
    }

    private fun evalJson(scenario: ActivityScenario<MainActivity>, script: String): JSONObject {
        val raw = evalJs(scenario, script)
        val decoded = JSONTokener(raw).nextValue()
        return JSONObject(if (decoded is String) decoded else decoded.toString())
    }

    private fun connectDirectPeer(scenario: ActivityScenario<MainActivity>): JSONObject {
        if (directSyncTarget.isEmpty()) return JSONObject().put("enabled", false)
        val initiation = evalJson(
            scenario,
            """(function(){
                window.__an3DirectSyncProbe = {done:false, connected:false, pingOk:false, error:"", statusError:"", mode:""};
                (async function(){
                  try {
                    var api = window.AN3NativeSync;
                    api.setMode("guest");
                    await api.init();
                    await api.join("$directSyncCode", "$directSyncTarget");
                    var deadline = Date.now() + 20_000;
                    while (Date.now() < deadline) {
                      var status = await api.status();
                      window.__an3DirectSyncProbe.statusError = String(status.error || "");
                      window.__an3DirectSyncProbe.mode = String(status.mode || "");
                      var connected = (status.peers || []).some(function(peer){ return peer.state === "connected"; });
                      if (connected) {
                        var ping = await api.request("ping", {});
                        window.__an3DirectSyncProbe.connected = true;
                        window.__an3DirectSyncProbe.pingOk = Boolean(ping && ping.ok === true && typeof ping.peerId === "string");
                        window.__an3DirectSyncProbe.done = true;
                        return;
                      }
                      await new Promise(function(resolve){ setTimeout(resolve, 250); });
                    }
                    window.__an3DirectSyncProbe.error = "direct endpoint did not connect";
                    window.__an3DirectSyncProbe.done = true;
                  } catch (error) {
                    window.__an3DirectSyncProbe.error = String(error && error.message || error);
                    window.__an3DirectSyncProbe.done = true;
                  }
                })();
                return JSON.stringify({started:true});
            })()""",
        )
        assertTrue("direct Sync connection probe did not start", initiation.optBoolean("started"))
        val deadline = System.currentTimeMillis() + 30_000
        var probe = JSONObject()
        while (System.currentTimeMillis() < deadline) {
            probe = evalJson(scenario, "JSON.stringify(window.__an3DirectSyncProbe || {done:false})")
            if (probe.optBoolean("done")) break
            Thread.sleep(250)
        }
        assertTrue(
            "direct Sync endpoint did not produce an authenticated peer session: $probe",
            probe.optBoolean("done") && probe.optBoolean("connected") && probe.optBoolean("pingOk"),
        )
        return probe
    }

    private fun readSyntheticSram(scenario: ActivityScenario<MainActivity>, romId: String, expectedCounter: Int): JSONObject {
        val deadline = System.currentTimeMillis() + 5_000
        var result = JSONObject()
        while (System.currentTimeMillis() < deadline) {
            val initiation = evalJson(
                scenario,
                """(function(){
                    var probe = window.__an3SramReadProbe = {done:false, valid:false, size:0, counter:-1, error:""};
                    (async function(){
                      try {
                        var api = window.AN3NativeSync;
                        var identity = await api.gameIdentity("gba", "$romId");
                        var records = await api.storage("save", "gba", "$romId", identity).readAll();
                        if (records.length !== 1) throw new Error("expected one native SRAM record; found " + records.length);
                        var value = records[0].bytes;
                        var bytes = value instanceof Uint8Array ? value : new Uint8Array(value || []);
                        var signature = bytes.length >= 4
                          && String.fromCharCode.apply(null, Array.from(bytes.slice(0, 4))) === "AN3B";
                        probe.size = bytes.byteLength;
                        probe.counter = bytes.length > 4 ? bytes[4] : -1;
                        probe.valid = probe.size === 32768 && signature;
                        probe.done = true;
                      } catch (error) {
                        probe.error = String(error && error.message || error);
                        probe.done = true;
                      }
                    })();
                    return JSON.stringify({started:true});
                })()""",
            )
            assertTrue("native SRAM readback did not start", initiation.optBoolean("started"))
            val attemptDeadline = minOf(deadline, System.currentTimeMillis() + 1_000)
            while (System.currentTimeMillis() < attemptDeadline) {
                result = evalJson(scenario, "JSON.stringify(window.__an3SramReadProbe || {done:false})")
                if (result.optBoolean("done")) break
                Thread.sleep(150)
            }
            if (!result.optBoolean("done")) {
                while (System.currentTimeMillis() < deadline) {
                    result = evalJson(scenario, "JSON.stringify(window.__an3SramReadProbe || {done:false})")
                    if (result.optBoolean("done")) break
                    Thread.sleep(150)
                }
                break
            }
            if (result.optBoolean("valid") && result.optInt("counter", -1) == expectedCounter) return result
            Thread.sleep(200)
        }
        assertTrue(
            "native SRAM did not reach expected counter $expectedCounter within the flush window " +
                "(done=${result.optBoolean("done")}, valid=${result.optBoolean("valid")}, actual=${result.optInt("counter", -1)}, error=${result.optString("error")})",
            result.optBoolean("done") && result.optBoolean("valid") && result.optInt("counter", -1) == expectedCounter,
        )
        return result
    }

    private fun launchSyntheticSramGame(scenario: ActivityScenario<MainActivity>, device: UiDevice, romTitle: String) {
        awaitWebView()
        val initiation = evalJson(
            scenario,
            """(function(){
                var probe = window.__an3SyntheticSecondGameLaunch = {done:false, launched:false, error:""};
                (async function(){
                  try {
                    await globalThis.AN3RerenderLibrary?.();
                    var navigation = document.querySelector('[data-nav="library"]');
                    if (!navigation) throw new Error("library navigation unavailable");
                    navigation.click();
                    await globalThis.AN3RerenderLibrary?.();
                    var title = Array.from(document.querySelectorAll("h4")).find(function(node){ return node.textContent === "$romTitle"; });
                    var launch = title && title.closest("article")?.querySelector('[data-testid="game-launch"]');
                    if (!launch) throw new Error("synthetic game launch button unavailable");
                    launch.click();
                    probe.launched = true;
                    probe.done = true;
                  } catch (error) {
                    probe.error = String(error && error.message || error);
                    probe.done = true;
                  }
                })();
                return JSON.stringify({started:true});
            })()""",
        )
        assertTrue("second synthetic game launch did not start", initiation.optBoolean("started"))
        val launchDeadline = System.currentTimeMillis() + 20_000
        var launch = JSONObject()
        while (System.currentTimeMillis() < launchDeadline) {
            launch = evalJson(scenario, "JSON.stringify(window.__an3SyntheticSecondGameLaunch || {done:false})")
            if (launch.optBoolean("done")) break
            Thread.sleep(200)
        }
        assertTrue("second synthetic game launch failed (${launch.optString("error")})", launch.optBoolean("launched"))
        assertTrue("the second native GBA game/menu did not appear", device.wait(Until.hasObject(By.text("Menu")), 30_000))
        val processDeadline = System.currentTimeMillis() + 15_000
        var processStarted = false
        while (System.currentTimeMillis() < processDeadline) {
            processStarted = device.executeShellCommand("pidof space.an3tocom.offline:game").trim().isNotEmpty()
            if (processStarted) break
            Thread.sleep(200)
        }
        assertTrue("the second separate native game process did not start", processStarted)
        Thread.sleep(4_000)
    }

    private fun exitNativeGameToLibrary(device: UiDevice): Boolean {
        assertTrue("the native game menu button was not available", device.wait(Until.hasObject(By.text("Menu")), 5_000))
        device.findObject(By.text("Menu")).click()
        assertTrue(
            "the native game menu did not offer its supported library exit",
            device.wait(Until.hasObject(By.text("Return to Library")), 10_000),
        )
        device.findObject(By.text("Return to Library")).click()
        device.waitForIdle()
        assertTrue(
            "the native game UI remained visible after its supported Return to Library action",
            device.wait(Until.gone(By.text("Menu")), 20_000),
        )
        awaitWebView()
        // Android may retain the now-background :game process after its Activity finishes.
        // Its PID is diagnostic only; the user-visible Activity transition is the contract.
        return device.executeShellCommand("pidof space.an3tocom.offline:game").trim().isNotEmpty()
    }

    private fun evalJs(scenario: ActivityScenario<MainActivity>, script: String): String {
        val latch = CountDownLatch(1)
        val result = arrayOf<String?>(null)
        scenario.onActivity { activity ->
            val webView = findWebView(activity.window.decorView)
                ?: throw AssertionError("The AN3 WebView is not attached")
            webView.evaluateJavascript(script) { value ->
                result[0] = value
                latch.countDown()
            }
        }
        assertTrue("WebView JavaScript evaluation timed out", latch.await(10, TimeUnit.SECONDS))
        return result[0] ?: "null"
    }

    private fun awaitWebView(timeoutMillis: Long = 20_000) {
        val deadline = System.currentTimeMillis() + timeoutMillis
        var lastError: Throwable? = null
        while (System.currentTimeMillis() < deadline) {
            try {
                onView(isAssignableFrom(WebView::class.java)).check(matches(isDisplayed()))
                return
            } catch (error: Throwable) {
                lastError = error
                Thread.sleep(250)
            }
        }
        throw AssertionError("The AN3 WebView did not attach", lastError)
    }

    private fun awaitNativeSync(scenario: ActivityScenario<MainActivity>, timeoutMillis: Long = 15_000) {
        val deadline = System.currentTimeMillis() + timeoutMillis
        while (System.currentTimeMillis() < deadline) {
            val decoded = JSONTokener(
                evalJs(scenario, "typeof window.AN3NativeSync === 'object' && typeof window.AN3NativeSync.discover === 'function'"),
            ).nextValue()
            if (decoded == true) return
            Thread.sleep(200)
        }
        val diagnostic = runCatching {
            evalJson(
                scenario,
                """JSON.stringify({
                    href:location.href,readyState:document.readyState,
                    globals:{nativeSync:typeof window.AN3NativeSync,syncTransfer:typeof window.AN3SyncTransfer,
                      nativeInvoke:typeof window.AN3NativeInvoke,tauri:typeof window.__TAURI__,tauriInternals:typeof window.__TAURI_INTERNALS__},
                    scripts:Array.from(document.scripts).map(function(script){return script.src}).filter(Boolean),
                    resources:performance.getEntriesByType("resource").map(function(entry){return entry.name})
                      .filter(function(name){return /native-|sync-transfer/.test(name)})
                })""",
            ).toString()
        }.getOrElse { "diagnostic-unavailable:${it.message}" }
        throw AssertionError("The native Sync script did not attach to the WebView ($diagnostic)")
    }

    private fun findWebView(view: View): WebView? {
        if (view is WebView) return view
        if (view is ViewGroup) {
            for (index in 0 until view.childCount) {
                findWebView(view.getChildAt(index))?.let { return it }
            }
        }
        return null
    }
}
