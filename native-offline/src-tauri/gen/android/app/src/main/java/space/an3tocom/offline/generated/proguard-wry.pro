# THIS FILE IS AUTO-GENERATED. DO NOT MODIFY!!

# Copyright 2020-2023 Tauri Programme within The Commons Conservancy
# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: MIT

-keep class space.an3tocom.offline.* {
  native <methods>;
}

-keep class space.an3tocom.offline.WryActivity {
  public <init>(...);

  void setWebView(space.an3tocom.offline.RustWebView);
  java.lang.Class getAppClass(...);
  int getId();
  java.lang.String getVersion();
  int startActivity(...);
}

-keep class space.an3tocom.offline.Ipc {
  public <init>(...);

  @android.webkit.JavascriptInterface public <methods>;
}

-keep class space.an3tocom.offline.RustWebView {
  public <init>(...);

  void loadUrlMainThread(...);
  void loadHTMLMainThread(...);
  void evalScript(...);
}

-keep class space.an3tocom.offline.RustWebChromeClient,space.an3tocom.offline.RustWebViewClient {
  public <init>(...);
}
