fn main() {
    println!("cargo:rerun-if-changed=src/azahar_host.mm");
    println!("cargo:rerun-if-changed=src/azahar_host.h");
    println!("cargo:rerun-if-changed=src/vulkan_frontend.mm");
    println!("cargo:rerun-if-changed=src/vulkan_frontend.h");
    println!("cargo:rerun-if-changed=src/hosted_frame_consumer.mm");
    println!("cargo:rerun-if-changed=src/hosted_frame_consumer.h");
    println!("cargo:rerun-if-changed=../../native/eden-bridge/src/an3_eden_hosted_frame.c");
    println!("cargo:rerun-if-changed=../../native/eden-bridge/src/an3_eden_hosted_frame_shm.c");
    println!("cargo:rerun-if-changed=../../native/eden-bridge/include/an3_eden_hosted_frame.h");
    println!("cargo:rerun-if-changed=../../native/eden-bridge/include/an3_eden_hosted_frame_shm.h");
    println!("cargo:rerun-if-changed=../vendor/moltenvk/macos-arm64/include/vulkan/vulkan.h");

    // Build scripts execute on the host; select native sources by target.
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("macos") {
        cc::Build::new()
            .cpp(true)
            .file("src/azahar_host.mm")
            .file("src/vulkan_frontend.mm")
            .file("src/hosted_frame_consumer.mm")
            .include("../vendor/moltenvk/macos-arm64/include")
            .include("../../native/eden-bridge/include")
            .flag("-std=c++20")
            .flag("-fobjc-arc")
            .flag("-mmacosx-version-min=13.4")
            .compile("emulatorrust_azahar_host");
        // Pure-C hosted-frame ring + shared-memory transport (no Eden, no Tauri).
        cc::Build::new()
            .file("../../native/eden-bridge/src/an3_eden_hosted_frame.c")
            .file("../../native/eden-bridge/src/an3_eden_hosted_frame_shm.c")
            .include("../../native/eden-bridge/include")
            .flag("-mmacosx-version-min=13.4")
            .compile("an3_eden_hosted_frame");
        println!("cargo:rustc-link-lib=framework=AppKit");
        println!("cargo:rustc-link-lib=framework=AVFoundation");
        println!("cargo:rustc-link-lib=framework=IOSurface");
        println!("cargo:rustc-link-lib=framework=Metal");
        println!("cargo:rustc-link-lib=framework=MetalKit");
        println!("cargo:rustc-link-lib=framework=CoreImage");
        println!("cargo:rustc-link-lib=framework=QuartzCore");
        println!("cargo:rustc-link-lib=framework=UniformTypeIdentifiers");
        println!("cargo:rustc-link-lib=framework=CoreVideo");
        println!("cargo:rustc-link-lib=c++");
    }

    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        let native_runtime = "../vendor/runtime/windows-x64/an3-native-runtime.exe";
        println!("cargo:rerun-if-changed={native_runtime}");
        println!("cargo:rerun-if-changed=../vendor/runtime/windows-x64/manifest.json");
        assert!(std::path::Path::new(native_runtime).is_file(),
            "Build the bundled portable Windows runtime with scripts/build-windows-runtime.ps1 first");
    }

    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "pick_and_import_native_rom",
            "remove_native_rom",
            "native_capabilities",
            "start_native_game",
            "stop_native_game",
            "set_native_input",
            "native_controller_start",
            "native_controller_stop",
            "native_controller_status",
            "native_controller_lan_start",
            "native_controller_lan_join",
            "native_controller_lan_send",
            "native_controller_lan_stop",
            "native_controller_lan_status",
            "native_controller_lan_refresh",
            "native_latency_start",
            "native_latency_snapshot",
            "native_latency_stop",
            "native_sync_start",
            "native_sync_join",
            "native_sync_status",
            "native_sync_stop",
            "native_sync_discover",
            "native_sync_forget",
            "native_sync_request",
            "native_sync_identity",
            "native_sync_account_context",
            "native_sync_set_account_proof",
            "native_sync_mark_account_verified",
            "native_sync_game_identity",
            "native_sync_storage_read",
            "native_sync_storage_write",
            "native_sync_library_manifest",
            "native_sync_library_read_chunk",
            "native_sync_library_upload_status",
            "native_sync_library_write_chunk",
            "switch_companion_detect",
            "switch_companion_launch",
            "switch_companion_launch_rom",
            "switch_companion_hosted_frame_supported",
            "switch_companion_status",
            "switch_companion_stop",
            "switch_companion_focus",
            "switch_companion_input",
            "switch_companion_analog",
            "switch_companion_audio",
            "switch_companion_hosted_frame",
            "switch_companion_hosted_frame_start",
            "switch_companion_hosted_frame_stop",
            "switch_companion_hosted_frame_stats",
            "switch_companion_hosted_frame_verify",
            "ui_control_result",
        ]),
    ))
    .expect("failed to generate Tauri capabilities");
}
