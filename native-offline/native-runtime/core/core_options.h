// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <string>
#include <sstream>
#include <vector>

namespace an3 {

constexpr unsigned kRetroNumCoreOptionValues = 128;

struct RetroCoreOptionValue {
    const char* value;
    const char* label;
};

struct RetroCoreOptionDefinition {
    const char* key;
    const char* desc;
    const char* info;
    RetroCoreOptionValue values[kRetroNumCoreOptionValues];
    const char* default_value;
};

struct RetroCoreOptionCategory {
    const char* key;
    const char* desc;
    const char* info;
};

struct RetroCoreOptionV2Definition {
    const char* key;
    const char* desc;
    // This must remain ABI-identical to libretro's v2 declaration.  The
    // categorized text fields are before the values array; omitting them
    // makes values point into text and crashes any UI that reads the option.
    const char* desc_categorized;
    const char* info;
    const char* info_categorized;
    const char* category_key;
    RetroCoreOptionValue values[kRetroNumCoreOptionValues];
    const char* default_value;
};

struct RetroCoreOptionsV2 {
    const RetroCoreOptionCategory* categories;
    const RetroCoreOptionV2Definition* definitions;
};

struct RetroCoreOptionsIntl {
    // SET_CORE_OPTIONS_V2_INTL carries v2 containers, not v1 definitions.
    const RetroCoreOptionsV2* us;
    const RetroCoreOptionsV2* local;
};

struct CoreOptionValue {
    std::string value;
    std::string label;
};

struct CoreOption {
    std::string key;
    std::string category;
    std::string display_label;
    std::string description;
    std::vector<CoreOptionValue> values;
    std::string default_value;
    std::string current_value;
    bool restart_required = true;
};

class CoreOptionsRegistry {
  public:
    explicit CoreOptionsRegistry(std::string core_namespace = {})
        : core_namespace_(std::move(core_namespace)) {}

    void reset(std::string core_namespace) {
        core_namespace_ = std::move(core_namespace);
        options_.clear();
        variable_update_ = false;
    }

    void capture_legacy(const RetroCoreOptionDefinition* definitions) {
        if (!definitions) return;
        for (const auto* definition = definitions; definition->key && *definition->key; ++definition) {
            CoreOption option;
            option.key = definition->key;
            option.display_label = definition->desc ? definition->desc : definition->key;
            option.description = definition->info ? definition->info : "";
            option.default_value = definition->default_value ? definition->default_value : "";
            for (unsigned index = 0; index < kRetroNumCoreOptionValues; ++index) {
                const auto& value = definition->values[index];
                if (!value.value || !*value.value) break;
                option.values.push_back({value.value, value.label && *value.label ? value.label : value.value});
            }
            add_or_replace(std::move(option));
        }
    }

    void capture_legacy_variables(const char* const* variables) {
        if (!variables) return;
        for (const auto* entry = variables; *entry; entry += 2) {
            const char* key = entry[0];
            const char* values = entry[1];
            if (!key || !*key || !values) break;
            CoreOption option;
            option.key = key;
            option.display_label = key;
            std::stringstream stream(values);
            std::string value;
            bool first = true;
            while (std::getline(stream, value, '|')) {
                if (value.empty()) continue;
                if (first) {
                    option.default_value = value;
                    first = false;
                }
                option.values.push_back({value, value});
            }
            add_or_replace(std::move(option));
        }
    }

    void capture_v2(const RetroCoreOptionsV2* options) {
        if (!options) return;
        for (const auto* definition = options->definitions;
             definition && definition->key && *definition->key;
             ++definition) {
            CoreOption option;
            option.key = definition->key;
            option.category = definition->category_key ? definition->category_key : "";
            option.display_label = definition->desc ? definition->desc : definition->key;
            option.description = definition->info ? definition->info : "";
            option.default_value = definition->default_value ? definition->default_value : "";
            for (unsigned index = 0; index < kRetroNumCoreOptionValues; ++index) {
                const auto& value = definition->values[index];
                if (!value.value || !*value.value) break;
                option.values.push_back({value.value, value.label && *value.label ? value.label : value.value});
            }
            add_or_replace(std::move(option));
        }
    }

    const CoreOption* find(const char* key) const {
        if (!key) return nullptr;
        for (const auto& option : options_) {
            if (option.key == key) return &option;
        }
        return nullptr;
    }

    CoreOption* find_mutable(const std::string& key) {
        for (auto& option : options_) {
            if (option.key == key) return &option;
        }
        return nullptr;
    }

    const std::vector<CoreOption>& options() const { return options_; }
    const std::string& core_namespace() const { return core_namespace_; }

    bool get(const char* key, const char*& value) const {
        const auto* option = find(key);
        if (!option) return false;
        value = option->current_value.c_str();
        return true;
    }

    bool set(const std::string& key, const std::string& value) {
        auto* option = find_mutable(key);
        if (!option) return false;
        if (std::none_of(option->values.begin(), option->values.end(), [&](const auto& allowed) {
                return allowed.value == value;
            })) {
            return false;
        }
        if (option->current_value == value) return true;
        option->current_value = value;
        variable_update_ = true;
        return true;
    }

    bool set_initial(const std::string& key, const std::string& value) {
        auto* option = find_mutable(key);
        if (!option) return false;
        if (std::none_of(option->values.begin(), option->values.end(), [&](const auto& allowed) {
                return allowed.value == value;
            })) {
            return false;
        }
        option->current_value = value;
        return true;
    }

    bool consume_update() {
        const bool value = variable_update_;
        variable_update_ = false;
        return value;
    }

    void mark_updated() { variable_update_ = true; }

  private:
    void add_or_replace(CoreOption option) {
        if (option.values.empty()) return;
        if (option.default_value.empty()) option.default_value = option.values.front().value;
        option.current_value = option.default_value;
        for (auto& existing : options_) {
            if (existing.key == option.key) {
                option.current_value = existing.current_value;
                existing = std::move(option);
                return;
            }
        }
        options_.push_back(std::move(option));
    }

    std::string core_namespace_;
    std::vector<CoreOption> options_;
    bool variable_update_ = false;
};

} // namespace an3
