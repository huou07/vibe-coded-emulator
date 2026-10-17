// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#include "linux_controls.h"
#include "../../../shared/generated/player_ui.h"
#include "../../../shared/generated/native_layouts.h"

#include <gtk/gtk.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <functional>
#include <iomanip>
#include <memory>
#include <optional>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace an3 {
namespace {

struct ActionSignal {
    std::function<void()> run;
};

struct ToggleSignal {
    std::function<void(bool)> run;
};

struct RangeSignal {
    std::function<void(double)> run;
};

struct ComboSignal {
    std::function<void(int)> run;
};

struct InputSignal {
    NativeInput* input = nullptr;
    unsigned button = 0;
};

struct AnalogSignal {
    NativeInput* input;
    bool digital;
    bool held = false;
    player_ui::Axis axis;
    GtkWidget* widget = nullptr;
    void set(double x, double y) {
        axis = player_ui::normalize(x, y);
        input->set_analog(static_cast<int16_t>(std::lround(axis.x * 32767.0)),
                          static_cast<int16_t>(std::lround(axis.y * 32767.0)));
        if (digital) {
            input->set_button(4, axis.y < -0.35); input->set_button(5, axis.y > 0.35);
            input->set_button(6, axis.x < -0.35); input->set_button(7, axis.x > 0.35);
        }
        if (widget) gtk_widget_queue_draw(widget);
    }
    void release() {
        held = false;
        if (widget && gtk_widget_has_grab(widget)) gtk_grab_remove(widget);
        set(0, 0);
    }
    void move(double x, double y) {
        const double width = gtk_widget_get_allocated_width(widget), height = gtk_widget_get_allocated_height(widget);
        const double travel = std::max(1.0, std::min(width, height) * 0.5 * player_ui::travel_ratio);
        set((x - width * 0.5) / travel, (y - height * 0.5) / travel);
    }
};

gboolean analog_draw(GtkWidget* widget, cairo_t* cr, gpointer raw) {
    const auto& stick = *static_cast<AnalogSignal*>(raw);
    const double cx = gtk_widget_get_allocated_width(widget) * 0.5, cy = gtk_widget_get_allocated_height(widget) * 0.5;
    const double radius = std::max(1.0, std::min(cx, cy) - 2.0), tau = 6.283185307179586;
    cairo_set_source_rgba(cr, .08, .08, .08, .72); cairo_arc(cr, cx, cy, radius, 0, tau); cairo_fill_preserve(cr);
    cairo_set_source_rgba(cr, 1, 1, 1, .5); cairo_set_line_width(cr, 1.5); cairo_stroke(cr);
    cairo_set_source_rgba(cr, 1, 1, 1, .85);
    cairo_arc(cr, cx + stick.axis.x * radius * player_ui::travel_ratio,
        cy + stick.axis.y * radius * player_ui::travel_ratio, radius * player_ui::thumb_radius_ratio, 0, tau); cairo_fill(cr);
    return TRUE;
}
gboolean analog_press(GtkWidget* widget, GdkEventButton* event, gpointer raw) {
    if (event->button != 1) return FALSE;
    auto* stick = static_cast<AnalogSignal*>(raw); stick->held = true;
    gtk_grab_add(widget); stick->move(event->x, event->y); return TRUE;
}
gboolean analog_motion(GtkWidget*, GdkEventMotion* event, gpointer raw) {
    auto* stick = static_cast<AnalogSignal*>(raw);
    if (stick->held) stick->move(event->x, event->y);
    return stick->held;
}
gboolean analog_release(GtkWidget*, GdkEventButton* event, gpointer raw) {
    if (event->button != 1) return FALSE;
    static_cast<AnalogSignal*>(raw)->release(); return TRUE;
}
gboolean analog_cancel(GtkWidget*, GdkEvent*, gpointer raw) {
    static_cast<AnalogSignal*>(raw)->release(); return FALSE;
}

void action_clicked(GtkWidget*, gpointer value) {
    static_cast<ActionSignal*>(value)->run();
}

void toggle_changed(GtkToggleButton* button, gpointer value) {
    static_cast<ToggleSignal*>(value)->run(gtk_toggle_button_get_active(button));
}

void range_changed(GtkRange* range, gpointer value) {
    static_cast<RangeSignal*>(value)->run(gtk_range_get_value(range));
}

void combo_changed(GtkComboBox* combo, gpointer value) {
    static_cast<ComboSignal*>(value)->run(gtk_combo_box_get_active(combo));
}

void input_pressed(GtkWidget*, gpointer value) {
    auto* action = static_cast<InputSignal*>(value);
    if (action->input) action->input->set_button(action->button, true);
}

void input_released(GtkWidget*, gpointer value) {
    auto* action = static_cast<InputSignal*>(value);
    if (action->input) action->input->set_button(action->button, false);
}

GtkWidget* make_box(GtkOrientation orientation = GTK_ORIENTATION_VERTICAL, int spacing = 8) {
    return gtk_box_new(orientation, spacing);
}

GtkWidget* make_label(const std::string& value, bool wrap = true) {
    GtkWidget* label = gtk_label_new(value.c_str());
    gtk_label_set_xalign(GTK_LABEL(label), 0.0f);
    gtk_label_set_yalign(GTK_LABEL(label), 0.0f);
    gtk_label_set_line_wrap(GTK_LABEL(label), wrap);
    gtk_label_set_selectable(GTK_LABEL(label), true);
    return label;
}

std::string user_facing_error(const std::string& operation, bool ok, const std::string& detail) {
    if (ok) return operation + " completed.";
    return operation + " failed: " + (detail.empty() ? "native core rejected the request" : detail);
}

} // namespace

class LinuxControlPanel::Impl {
  public:
    Impl(NativeCoreHost& host, LinuxSdlAudioBackend& audio, std::string system,
         LinuxControlCallbacks callbacks)
        : host_(host), audio_(audio), system_(std::move(system)), callbacks_(std::move(callbacks)) {}

    ~Impl() {
        if (window_) gtk_widget_destroy(window_);
        window_ = nullptr;
    }

    bool initialize(std::string& error) {
        if (window_) return true;
        int argc = 0;
        char** argv = nullptr;
        if (!gtk_init_check(&argc, &argv)) {
            error = "Native GTK controls are unavailable in this desktop session.";
            return false;
        }

        window_ = gtk_window_new(GTK_WINDOW_TOPLEVEL);
        gtk_window_set_title(GTK_WINDOW(window_), "VibeCodedEmulator Controls");
        gtk_window_set_default_size(GTK_WINDOW(window_), player_ui::panel_width, player_ui::panel_height);
        gtk_container_set_border_width(GTK_CONTAINER(window_), 12);
        g_signal_connect(window_, "delete-event", G_CALLBACK(on_window_close), this);

        GtkWidget* root = make_box();
        gtk_container_add(GTK_CONTAINER(window_), root);
        GtkWidget* heading = make_label("VibeCodedEmulator", false);
        PangoAttrList* attrs = pango_attr_list_new();
        pango_attr_list_insert(attrs, pango_attr_weight_new(PANGO_WEIGHT_BOLD));
        gtk_label_set_attributes(GTK_LABEL(heading), attrs);
        pango_attr_list_unref(attrs);
        gtk_box_pack_start(GTK_BOX(root), heading, false, false, 0);
        feedback_ = make_label("Menu and Pad controls stay separate from the SDL game surface.");
        gtk_box_pack_start(GTK_BOX(root), feedback_, false, false, 0);
        // Match the native DMG action row while retaining GTK's own accessible
        // controls. F2/F3 remain keyboard equivalents, not a second input path.
        GtkWidget* toolbar = make_box(GTK_ORIENTATION_HORIZONTAL, 8);
        gtk_box_pack_start(GTK_BOX(toolbar), button(std::string(player_ui::toolbar_menu), [this] { hide(); }), false, false, 0);
        gtk_box_pack_start(GTK_BOX(toolbar), button(std::string(player_ui::toolbar_pad), [this] { show_pad(); }), false, false, 0);
        if (system_ == "nds" || system_ == "3ds") {
            gtk_box_pack_start(GTK_BOX(toolbar), button(std::string(player_ui::toolbar_layout), [this] {
                show_layout_menu();
            }), false, false, 0);
        }
        gtk_box_pack_start(GTK_BOX(toolbar), button(std::string(player_ui::toolbar_save), [this] {
            show_save_menu();
        }), false, false, 0);
        gtk_box_pack_start(GTK_BOX(root), toolbar, false, false, 0);

        notebook_ = gtk_notebook_new();
        gtk_box_pack_start(GTK_BOX(root), notebook_, true, true, 0);
        const std::array<GtkWidget*, 9> pages = {build_general(), build_graphics(), build_audio(), build_keyboard(),
            build_controller(), build_emulation(), build_saves(), build_diagnostics(), build_about()};
        for (size_t i = 0; i < pages.size(); ++i) {
            const int page = append_page(player_ui::tabs[i].data(), pages[i]);
            if (player_ui::tabs[i] == "Controller") controller_page_ = page;
        }
        refresh();
        return true;
    }

    void pump() {
        while (g_main_context_pending(nullptr)) g_main_context_iteration(nullptr, false);
        const auto now = std::chrono::steady_clock::now();
        if (now - last_refresh_ >= std::chrono::milliseconds(250)) {
            refresh();
            last_refresh_ = now;
        }
    }

    void show() {
        if (!window_) return;
        gtk_widget_show_all(window_);
        gtk_window_present(GTK_WINDOW(window_));
    }

    void hide() {
        if (analog_) analog_->release();
        if (window_) gtk_widget_hide(window_);
    }

    void toggle() {
        if (visible()) hide(); else show();
    }

    void show_pad() {
        show();
        if (notebook_ && controller_page_ >= 0) gtk_notebook_set_current_page(GTK_NOTEBOOK(notebook_), controller_page_);
    }

    bool visible() const { return window_ && gtk_widget_get_visible(window_); }

  private:
    static gboolean on_window_close(GtkWidget*, GdkEvent*, gpointer raw) {
        static_cast<Impl*>(raw)->hide();
        return TRUE;
    }

    int append_page(const char* title, GtkWidget* content) {
        GtkWidget* scroll = gtk_scrolled_window_new(nullptr, nullptr);
        gtk_container_set_border_width(GTK_CONTAINER(scroll), 8);
        gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scroll), GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
        gtk_container_add(GTK_CONTAINER(scroll), content);
        return gtk_notebook_append_page(GTK_NOTEBOOK(notebook_), scroll, gtk_label_new(title));
    }

    GtkWidget* button(const std::string& label, std::function<void()> callback) {
        GtkWidget* result = gtk_button_new_with_label(label.c_str());
        actions_.push_back(std::make_unique<ActionSignal>(ActionSignal{std::move(callback)}));
        g_signal_connect(result, "clicked", G_CALLBACK(action_clicked), actions_.back().get());
        return result;
    }

    GtkWidget* input_button(const std::string& label, unsigned id) {
        GtkWidget* result = gtk_button_new_with_label(label.c_str());
        input_actions_.push_back(std::make_unique<InputSignal>(InputSignal{&host_.input(), id}));
        auto* action = input_actions_.back().get();
        g_signal_connect(result, "pressed", G_CALLBACK(input_pressed), action);
        g_signal_connect(result, "released", G_CALLBACK(input_released), action);
        return result;
    }

    GtkWidget* checkbox(const std::string& label, bool checked, std::function<void(bool)> callback) {
        GtkWidget* result = gtk_check_button_new_with_label(label.c_str());
        gtk_toggle_button_set_active(GTK_TOGGLE_BUTTON(result), checked);
        toggles_.push_back(std::make_unique<ToggleSignal>(ToggleSignal{std::move(callback)}));
        g_signal_connect(result, "toggled", G_CALLBACK(toggle_changed), toggles_.back().get());
        return result;
    }

    GtkWidget* build_general() {
        GtkWidget* box = make_box();
        general_label_ = make_label("Starting native runtime…");
        gtk_box_pack_start(GTK_BOX(box), general_label_, false, false, 0);
        pause_button_ = button("Pause", [this] {
            const auto current = snapshot();
            callbacks_.set_paused(!current.paused);
            status(current.paused ? "Game resumed." : "Game paused. Input was cleared.");
        });
        gtk_box_pack_start(GTK_BOX(box), pause_button_, false, false, 0);
        gtk_box_pack_start(GTK_BOX(box), button("Toggle fullscreen", [this] { callbacks_.toggle_fullscreen(); }), false, false, 0);
        gtk_box_pack_start(GTK_BOX(box), button("Return to library", [this] { callbacks_.return_to_library(); }), false, false, 0);
        gtk_box_pack_start(GTK_BOX(box), make_label("Keyboard: arrows, Z/X, A/S, L/J, Return and Space. F1 changes dual-screen layout, F2 opens Menu, F3 opens Pad, F5/F9 save/load slot 1."), false, false, 0);
        return box;
    }

    GtkWidget* build_graphics() {
        GtkWidget* box = make_box();
        graphics_label_ = make_label("Renderer initializing…");
        gtk_box_pack_start(GTK_BOX(box), graphics_label_, false, false, 0);
        if (system_ == "nds" || system_ == "3ds") {
            gtk_box_pack_start(GTK_BOX(box), make_label("Screen layout · applies immediately and persists for this ROM."), false, false, 0);
            GtkWidget* layouts = make_box(GTK_ORIENTATION_HORIZONTAL, 8);
            gtk_box_pack_start(GTK_BOX(layouts), button("Side by Side", [this] { apply_layout("left-right"); }), true, true, 0);
            gtk_box_pack_start(GTK_BOX(layouts), button("Top / Bottom", [this] { apply_layout("top-bottom"); }), true, true, 0);
            gtk_box_pack_start(GTK_BOX(box), layouts, false, false, 0);
        }
        gtk_box_pack_start(GTK_BOX(box), make_label("Vulkan remains the first native path. GBA and NDS may use the existing desktop OpenGL fallback; 3DS stays Vulkan-only so its core image never takes a GPU-to-CPU-to-GPU path."), false, false, 0);
        return box;
    }

    GtkWidget* build_audio() {
        GtkWidget* box = make_box();
        audio_label_ = make_label("Native SDL audio initializing…");
        gtk_box_pack_start(GTK_BOX(box), audio_label_, false, false, 0);
        gtk_box_pack_start(GTK_BOX(box), make_label("Volume"), false, false, 0);
        GtkWidget* volume = gtk_scale_new_with_range(GTK_ORIENTATION_HORIZONTAL, 0.0, 100.0, 1.0);
        gtk_range_set_value(GTK_RANGE(volume), snapshot().audio.volume * 100.0);
        ranges_.push_back(std::make_unique<RangeSignal>(RangeSignal{[this](double value) {
            if (!audio_.set_volume(static_cast<float>(value / 100.0))) status("Audio volume is outside the supported range.");
        }}));
        g_signal_connect(volume, "value-changed", G_CALLBACK(range_changed), ranges_.back().get());
        gtk_box_pack_start(GTK_BOX(box), volume, false, false, 0);
        gtk_box_pack_start(GTK_BOX(box), checkbox("Mute", snapshot().audio.muted, [this](bool value) {
            audio_.set_muted(value);
            status(value ? "Audio muted." : "Audio unmuted.");
        }), false, false, 0);
        gtk_box_pack_start(GTK_BOX(box), make_label("SDL retains a bounded queue. Audio controls do not drive the core scheduler or renderer."), false, false, 0);
        return box;
    }

    GtkWidget* build_keyboard() {
        GtkWidget* box = make_box();
        gtk_box_pack_start(GTK_BOX(box), make_label("Keyboard input is sampled by the same native input state as the SDL window. It never depends on GUI redraw cadence."), false, false, 0);
        gtk_box_pack_start(GTK_BOX(box), make_label("Arrows: D-pad\nZ / X: B / A\nA / S: Y / X\nL / J: L / R\nSpace / Return: Select / Start\nP: pause · F1: layout · F2: menu · F3: pad · F4: fullscreen · F5/F9: quick save/load slot 1"), false, false, 0);
        gtk_box_pack_start(GTK_BOX(box), button("Release held native input", [this] {
            host_.input().clear();
            status("Held keyboard and controller input released.");
        }), false, false, 0);
        return box;
    }

    GtkWidget* build_controller() {
        GtkWidget* box = make_box();
        gtk_box_pack_start(GTK_BOX(box), make_label("Pad buttons are native SDL input. Hold a button while it is pressed; releasing it clears only that button. A connected controller remains active in the SDL game window."), false, false, 0);
        GtkWidget* joystick = gtk_drawing_area_new();
        gtk_widget_set_size_request(joystick, player_ui::stick_diameter, player_ui::stick_diameter);
        gtk_widget_set_halign(joystick, GTK_ALIGN_START);
        gtk_widget_set_tooltip_text(joystick, "Analog Joystick");
        gtk_widget_add_events(joystick, GDK_BUTTON_PRESS_MASK | GDK_BUTTON_RELEASE_MASK | GDK_POINTER_MOTION_MASK);
        analog_ = std::make_unique<AnalogSignal>(AnalogSignal{&host_.input(), system_ != "3ds", false, {}, joystick});
        g_signal_connect(joystick, "draw", G_CALLBACK(analog_draw), analog_.get());
        g_signal_connect(joystick, "button-press-event", G_CALLBACK(analog_press), analog_.get());
        g_signal_connect(joystick, "motion-notify-event", G_CALLBACK(analog_motion), analog_.get());
        g_signal_connect(joystick, "button-release-event", G_CALLBACK(analog_release), analog_.get());
        g_signal_connect(joystick, "grab-broken-event", G_CALLBACK(analog_cancel), analog_.get());
        g_signal_connect(window_, "focus-out-event", G_CALLBACK(analog_cancel), analog_.get());
        gtk_box_pack_start(GTK_BOX(box), joystick, false, false, 0);
        GtkWidget* grid = gtk_grid_new();
        gtk_grid_set_row_spacing(GTK_GRID(grid), 6);
        gtk_grid_set_column_spacing(GTK_GRID(grid), 6);
        gtk_grid_attach(GTK_GRID(grid), input_button("▲", 4), 1, 0, 1, 1);
        gtk_grid_attach(GTK_GRID(grid), input_button("◀", 6), 0, 1, 1, 1);
        gtk_grid_attach(GTK_GRID(grid), input_button("▼", 5), 1, 1, 1, 1);
        gtk_grid_attach(GTK_GRID(grid), input_button("▶", 7), 2, 1, 1, 1);
        gtk_grid_attach(GTK_GRID(grid), input_button("B", 0), 4, 0, 1, 1);
        gtk_grid_attach(GTK_GRID(grid), input_button("A", 8), 5, 0, 1, 1);
        gtk_grid_attach(GTK_GRID(grid), input_button("Y", 1), 4, 1, 1, 1);
        gtk_grid_attach(GTK_GRID(grid), input_button("X", 9), 5, 1, 1, 1);
        gtk_grid_attach(GTK_GRID(grid), input_button("L", 10), 0, 3, 1, 1);
        gtk_grid_attach(GTK_GRID(grid), input_button("R", 11), 1, 3, 1, 1);
        gtk_grid_attach(GTK_GRID(grid), input_button("Select", 2), 3, 3, 1, 1);
        gtk_grid_attach(GTK_GRID(grid), input_button("Start", 3), 4, 3, 1, 1);
        gtk_box_pack_start(GTK_BOX(box), grid, false, false, 0);
        gtk_box_pack_start(GTK_BOX(box), make_label("Mouse/touch input continues on the lower NDS/3DS screen in the SDL game window. Controller and keyboard mappings remain independent of these buttons."), false, false, 0);
        return box;
    }

    GtkWidget* build_emulation() {
        GtkWidget* box = make_box();
        gtk_box_pack_start(GTK_BOX(box), make_label("Speed"), false, false, 0);
        GtkWidget* speeds = make_box(GTK_ORIENTATION_HORIZONTAL, 6);
        for (const auto& item : std::vector<std::pair<std::string, double>>{{std::string(player_ui::toolbar_speed[0]), .5}, {std::string(player_ui::toolbar_speed[1]), 1.0}, {std::string(player_ui::toolbar_speed[2]), 2.0}, {"x4", 4.0}, {"x8", 8.0}}) {
            gtk_box_pack_start(GTK_BOX(speeds), button(item.first, [this, value = item.second] {
                callbacks_.set_speed(value);
                status("Emulation speed changed. Audio and presentation remain bounded.");
            }), true, true, 0);
        }
        gtk_box_pack_start(GTK_BOX(box), speeds, false, false, 0);
        gtk_box_pack_start(GTK_BOX(box), make_label("Core options · some options require restart"), false, false, 0);
        const auto options = host_.core_options();
        if (options.empty()) {
            gtk_box_pack_start(GTK_BOX(box), make_label("The active core has not announced options."), false, false, 0);
        }
        for (const auto& option : options) {
            if (option.key == "melonds_screen_layout1" || option.key == "citra_layout_option" || option.values.empty()) continue;
            gtk_box_pack_start(GTK_BOX(box), make_label(option.label.empty() ? option.key : option.label), false, false, 0);
            GtkWidget* chooser = gtk_combo_box_text_new();
            int selected = 0;
            for (size_t index = 0; index < option.values.size(); ++index) {
                const auto& value = option.values[index];
                gtk_combo_box_text_append_text(GTK_COMBO_BOX_TEXT(chooser), (value.label.empty() ? value.value : value.label).c_str());
                if (value.value == option.current_value) selected = static_cast<int>(index);
            }
            gtk_combo_box_set_active(GTK_COMBO_BOX(chooser), selected);
            const auto key = option.key;
            std::vector<std::string> values;
            values.reserve(option.values.size());
            for (const auto& value : option.values) values.push_back(value.value);
            combos_.push_back(std::make_unique<ComboSignal>(ComboSignal{[this, key, values = std::move(values)](int index) {
                if (index < 0 || static_cast<size_t>(index) >= values.size()) return;
                std::string error;
                status(user_facing_error("Core option", host_.set_core_option(key, values[static_cast<size_t>(index)], error), error));
            }}));
            g_signal_connect(chooser, "changed", G_CALLBACK(combo_changed), combos_.back().get());
            gtk_box_pack_start(GTK_BOX(box), chooser, false, false, 0);
        }
        return box;
    }

    GtkWidget* build_saves() {
        GtkWidget* box = make_box();
        const auto current = snapshot();
        gtk_box_pack_start(GTK_BOX(box), make_label(std::string(player_ui::auto_save_label)), false, false, 0);
        GtkWidget* mode = gtk_combo_box_text_new();
        int selected = 0;
        for (size_t index = 0; index < player_ui::auto_save_tokens.size(); ++index) {
            gtk_combo_box_text_append_text(GTK_COMBO_BOX_TEXT(mode), std::string(player_ui::auto_save_titles[index]).c_str());
            if (player_ui::auto_save_tokens[index] == current.auto_save_mode) selected = static_cast<int>(index);
        }
        gtk_combo_box_set_active(GTK_COMBO_BOX(mode), selected);
        combos_.push_back(std::make_unique<ComboSignal>(ComboSignal{[this](int index) {
            if (index < 0 || static_cast<size_t>(index) >= player_ui::auto_save_tokens.size()) return;
            const std::string token(player_ui::auto_save_tokens[static_cast<size_t>(index)]);
            callbacks_.set_auto_save_mode(token);
            if (token == "off") status("Auto Save disabled.");
            else if (token == "exit") status("Auto Save runs when you exit the game.");
            else status("Auto Save will run every configured interval.");
        }}));
        g_signal_connect(mode, "changed", G_CALLBACK(combo_changed), combos_.back().get());
        gtk_box_pack_start(GTK_BOX(box), mode, false, false, 0);
        gtk_box_pack_start(GTK_BOX(box), button("Load Auto Save", [this] {
            std::string error; status(user_facing_error("Load Auto Save", host_.load_auto(error), error));
        }), false, false, 0);
        gtk_box_pack_start(GTK_BOX(box), make_label("Quick saves use raw native core state bytes and remain distinct from Auto Save."), false, false, 0);
        GtkWidget* slots = gtk_grid_new();
        gtk_grid_set_row_spacing(GTK_GRID(slots), 4);
        gtk_grid_set_column_spacing(GTK_GRID(slots), 4);
        for (unsigned slot = 1; slot <= 10; ++slot) {
            gtk_grid_attach(GTK_GRID(slots), button("Save " + std::to_string(slot), [this, slot] {
                std::string error; status(user_facing_error("Quick save " + std::to_string(slot), host_.save_state(slot, error), error));
            }), 0, static_cast<int>(slot - 1), 1, 1);
            gtk_grid_attach(GTK_GRID(slots), button("Load " + std::to_string(slot), [this, slot] {
                std::string error; status(user_facing_error("Quick load " + std::to_string(slot), host_.load_state(slot, error), error));
            }), 1, static_cast<int>(slot - 1), 1, 1);
        }
        gtk_box_pack_start(GTK_BOX(box), slots, false, false, 0);
        GtkWidget* transfer = make_box(GTK_ORIENTATION_HORIZONTAL, 6);
        gtk_box_pack_start(GTK_BOX(transfer), button("Export Save State…", [this] { transfer_state(true); }), true, true, 0);
        gtk_box_pack_start(GTK_BOX(transfer), button("Import Save State…", [this] { transfer_state(false); }), true, true, 0);
        gtk_box_pack_start(GTK_BOX(box), transfer, false, false, 0);
        return box;
    }

    GtkWidget* build_diagnostics() {
        GtkWidget* box = make_box();
        diagnostics_label_ = make_label("Waiting for native runtime metrics…");
        gtk_box_pack_start(GTK_BOX(box), diagnostics_label_, false, false, 0);
        return box;
    }

    GtkWidget* build_about() {
        GtkWidget* box = make_box();
        gtk_box_pack_start(GTK_BOX(box), make_label("VibeCodedEmulator 0.4.5 · Linux staging\nNative GBA / NDS libretro cores · SDL input/audio/window · Vulkan-first with desktop OpenGL fallback for software cores."), false, false, 0);
        gtk_box_pack_start(GTK_BOX(box), make_label("This control window reuses the native host's state, core-option, layout, input, and save interfaces. It does not embed a browser renderer or copy GPU frames through the CPU."), false, false, 0);
        return box;
    }

    LinuxControlSnapshot snapshot() const {
        return callbacks_.snapshot ? callbacks_.snapshot() : LinuxControlSnapshot{};
    }

    void status(const std::string& value) {
        last_feedback_ = value;
        if (feedback_) gtk_label_set_text(GTK_LABEL(feedback_), value.c_str());
    }

    void apply_layout(const std::string& layout) {
        std::string error;
        status(user_facing_error("Screen layout", callbacks_.set_layout && callbacks_.set_layout(layout, error), error));
    }

    std::optional<std::string> state_path(bool export_state) const {
        if (!window_) return std::nullopt;
        GtkWidget* dialog = gtk_file_chooser_dialog_new(export_state ? "Export native save state" : "Import native save state",
            GTK_WINDOW(window_), export_state ? GTK_FILE_CHOOSER_ACTION_SAVE : GTK_FILE_CHOOSER_ACTION_OPEN,
            "_Cancel", GTK_RESPONSE_CANCEL, export_state ? "_Save" : "_Open", GTK_RESPONSE_ACCEPT, nullptr);
        GtkFileFilter* filter = gtk_file_filter_new();
        gtk_file_filter_set_name(filter, "Native save states");
        gtk_file_filter_add_pattern(filter, "*.state");
        gtk_file_chooser_add_filter(GTK_FILE_CHOOSER(dialog), filter);
        if (export_state) {
            gtk_file_chooser_set_current_name(GTK_FILE_CHOOSER(dialog), "vibecodedemulator.state");
            gtk_file_chooser_set_do_overwrite_confirmation(GTK_FILE_CHOOSER(dialog), true);
        }
        std::optional<std::string> result;
        if (gtk_dialog_run(GTK_DIALOG(dialog)) == GTK_RESPONSE_ACCEPT) {
            gchar* selected = gtk_file_chooser_get_filename(GTK_FILE_CHOOSER(dialog));
            if (selected) { result = selected; g_free(selected); }
        }
        gtk_widget_destroy(dialog);
        return result;
    }

    void show_layout_menu() {
        if (system_ != "nds" && system_ != "3ds") return;
        const std::string current = snapshot().layout;
        GtkWidget* menu = gtk_menu_new();
        menu_actions_.clear();
        auto add = [&](const auto& layouts) {
            for (const auto& layout : layouts) {
                const std::string id(layout.id);
                GtkWidget* item = gtk_menu_item_new_with_label(std::string(layout.label).c_str());
                if (id == current) gtk_widget_set_sensitive(item, false);
                menu_actions_.push_back(std::make_unique<ActionSignal>(ActionSignal{[this, id] {
                    std::string error;
                    if (callbacks_.set_layout && callbacks_.set_layout(id, error)) {
                        status("Screen layout changed to " + id + ".");
                    } else {
                        status("Screen layout failed: " + (error.empty() ? std::string("native core rejected the request") : error));
                    }
                }}));
                g_signal_connect(item, "activate", G_CALLBACK(action_clicked), menu_actions_.back().get());
                gtk_menu_shell_append(GTK_MENU_SHELL(menu), item);
            }
        };
        if (system_ == "nds") add(native_layouts::nds);
        else add(native_layouts::three_ds);
        g_signal_connect(menu, "deactivate", G_CALLBACK(gtk_widget_destroy), nullptr);
        gtk_widget_show_all(menu);
        gtk_menu_popup_at_pointer(GTK_MENU(menu), nullptr);
    }

    // The toolbar Save control mirrors the Save States tab's quick actions.
    void show_save_menu() {
        GtkWidget* menu = gtk_menu_new();
        menu_actions_.clear();
        auto add_item = [&](const std::string& title, std::function<void()> run) {
            GtkWidget* item = gtk_menu_item_new_with_label(title.c_str());
            menu_actions_.push_back(std::make_unique<ActionSignal>(ActionSignal{std::move(run)}));
            g_signal_connect(item, "activate", G_CALLBACK(action_clicked), menu_actions_.back().get());
            gtk_menu_shell_append(GTK_MENU_SHELL(menu), item);
        };
        // Quick Save / Quick Load expose all ten quick slots, matching the Save
        // States tab, so a save or load never needs the full menu.
        auto add_slots = [&](const std::string& title, bool save) {
            GtkWidget* root = gtk_menu_item_new_with_label(title.c_str());
            GtkWidget* submenu = gtk_menu_new();
            for (unsigned slot = 1; slot <= 10; ++slot) {
                GtkWidget* item = gtk_menu_item_new_with_label(("Slot " + std::to_string(slot)).c_str());
                menu_actions_.push_back(std::make_unique<ActionSignal>(ActionSignal{[this, save, slot] {
                    std::string error;
                    const bool ok = save ? host_.save_state(slot, error) : host_.load_state(slot, error);
                    status(user_facing_error((save ? "Quick Save " : "Quick Load ") + std::to_string(slot), ok, error));
                }}));
                g_signal_connect(item, "activate", G_CALLBACK(action_clicked), menu_actions_.back().get());
                gtk_menu_shell_append(GTK_MENU_SHELL(submenu), item);
            }
            gtk_menu_item_set_submenu(GTK_MENU_ITEM(root), submenu);
            gtk_menu_shell_append(GTK_MENU_SHELL(menu), root);
        };
        add_slots(std::string(player_ui::toolbar_quick_save), true);
        add_slots(std::string(player_ui::toolbar_quick_load), false);
        gtk_menu_shell_append(GTK_MENU_SHELL(menu), gtk_separator_menu_item_new());
        add_item("Auto Save now", [this] {
            std::string error;
            status(user_facing_error("Auto Save", host_.save_auto(error), error));
        });
        add_item("Load Auto Save", [this] {
            std::string error;
            status(user_facing_error("Load Auto Save", host_.load_auto(error), error));
        });
        g_signal_connect(menu, "deactivate", G_CALLBACK(gtk_widget_destroy), nullptr);
        gtk_widget_show_all(menu);
        gtk_menu_popup_at_pointer(GTK_MENU(menu), nullptr);
    }

    void transfer_state(bool export_state) {
        const auto path = state_path(export_state);
        if (!path) return;
        std::string error;
        const bool ok = export_state ? host_.export_state(*path, error) : host_.import_state(*path, error);
        status(user_facing_error(export_state ? "Export Save State" : "Import Save State", ok, error));
    }

    void refresh() {
        if (!window_) return;
        const auto current = snapshot();
        if (general_label_) {
            std::ostringstream text;
            text << (current.core.core_name.empty() ? "Native core" : current.core.core_name);
            if (!current.core.core_version.empty()) text << " " << current.core.core_version;
            text << " · " << (current.paused ? "paused" : "running") << " · " << std::fixed << std::setprecision(1) << current.speed << "×";
            gtk_label_set_text(GTK_LABEL(general_label_), text.str().c_str());
        }
        if (pause_button_) gtk_button_set_label(GTK_BUTTON(pause_button_), current.paused ? "Resume" : "Pause");
        if (graphics_label_) {
            std::ostringstream text;
            text << "Renderer: requested " << current.video.requested << " · effective " << current.video.effective
                 << " · frames " << current.video.frames.presented_frames << " · drops " << current.video.frames.dropped_frames;
            if (!current.layout.empty()) text << " · layout " << current.layout;
            gtk_label_set_text(GTK_LABEL(graphics_label_), text.str().c_str());
        }
        if (audio_label_) {
            std::ostringstream text;
            text << "Audio: " << current.audio.sample_rate << " Hz · queued " << current.audio.queued_frames
                 << " frames · volume " << static_cast<int>(std::lround(current.audio.volume * 100.0f)) << "%";
            if (current.audio.muted) text << " · muted";
            gtk_label_set_text(GTK_LABEL(audio_label_), text.str().c_str());
        }
        if (diagnostics_label_) {
            std::ostringstream text;
            text << "Core frames: " << current.core.core_frames << "\n"
                 << "Core FPS: " << std::fixed << std::setprecision(2) << current.core.core_fps << "\n"
                 << "Renderer: " << current.video.effective << " · ring " << current.video.frames_in_flight << "\n"
                 << "Uploads direct/copied/converted: " << current.video.frames.direct_software_uploads << "/"
                 << current.video.frames.copied_software_uploads << "/" << current.video.frames.converted_software_uploads << "\n"
                 << "Audio queue: " << current.audio.queued_frames << " frames\n"
                 << "Last runtime message: " << (current.last_message.empty() ? "—" : current.last_message);
            gtk_label_set_text(GTK_LABEL(diagnostics_label_), text.str().c_str());
        }
    }

    NativeCoreHost& host_;
    LinuxSdlAudioBackend& audio_;
    std::string system_;
    LinuxControlCallbacks callbacks_;
    GtkWidget* window_ = nullptr;
    GtkWidget* notebook_ = nullptr;
    GtkWidget* feedback_ = nullptr;
    GtkWidget* general_label_ = nullptr;
    GtkWidget* graphics_label_ = nullptr;
    GtkWidget* audio_label_ = nullptr;
    GtkWidget* diagnostics_label_ = nullptr;
    GtkWidget* pause_button_ = nullptr;
    int controller_page_ = -1;
    std::string last_feedback_;
    std::chrono::steady_clock::time_point last_refresh_{};
    std::vector<std::unique_ptr<ActionSignal>> actions_;
    std::vector<std::unique_ptr<ActionSignal>> menu_actions_;
    std::vector<std::unique_ptr<ToggleSignal>> toggles_;
    std::vector<std::unique_ptr<RangeSignal>> ranges_;
    std::vector<std::unique_ptr<ComboSignal>> combos_;
    std::vector<std::unique_ptr<InputSignal>> input_actions_;
    std::unique_ptr<AnalogSignal> analog_;
};

LinuxControlPanel::LinuxControlPanel(NativeCoreHost& host, LinuxSdlAudioBackend& audio,
                                     std::string system, LinuxControlCallbacks callbacks)
    : impl_(std::make_unique<Impl>(host, audio, std::move(system), std::move(callbacks))) {}

LinuxControlPanel::~LinuxControlPanel() = default;
bool LinuxControlPanel::initialize(std::string& error) { return impl_->initialize(error); }
void LinuxControlPanel::pump() { impl_->pump(); }
void LinuxControlPanel::show() { impl_->show(); }
void LinuxControlPanel::hide() { impl_->hide(); }
void LinuxControlPanel::toggle() { impl_->toggle(); }
void LinuxControlPanel::show_pad() { impl_->show_pad(); }
bool LinuxControlPanel::visible() const { return impl_->visible(); }

} // namespace an3
