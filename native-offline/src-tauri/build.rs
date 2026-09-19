fn main() {
    println!("cargo:rerun-if-changed=src/azahar_host.mm");
    println!("cargo:rerun-if-changed=src/azahar_host.h");
    println!("cargo:rerun-if-changed=src/vulkan_frontend.mm");
    println!("cargo:rerun-if-changed=src/vulkan_frontend.h");
    println!("cargo:rerun-if-changed=../vendor/moltenvk/macos-arm64/include/vulkan/vulkan.h");

    // Build scripts execute on the host; select native sources by target.
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("macos") {
        cc::Build::new()
            .cpp(true)
            .file("src/azahar_host.mm")
            .file("src/vulkan_frontend.mm")
            .include("../vendor/moltenvk/macos-arm64/include")
            .flag("-std=c++20")
            .flag("-fobjc-arc")
            .flag("-mmacosx-version-min=13.4")
            .compile("emulatorrust_azahar_host");
        println!("cargo:rustc-link-lib=framework=AppKit");
        println!("cargo:rustc-link-lib=framework=AVFoundation");
        println!("cargo:rustc-link-lib=framework=Metal");
        println!("cargo:rustc-link-lib=framework=MetalKit");
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
            "native_controller_lan_stop",
            "native_controller_lan_status",
            "native_controller_lan_refresh",
            "switch_companion_detect",
            "switch_companion_launch",
            "switch_companion_launch_rom",
            "switch_companion_status",
            "switch_companion_stop",
            "switch_companion_focus",
            "switch_companion_input",
            "switch_companion_analog",
            "switch_companion_audio",
            "ui_control_result",
        ]),
    ))
    .expect("failed to generate Tauri capabilities");
}
