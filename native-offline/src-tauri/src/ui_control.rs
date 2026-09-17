// SPDX-FileCopyrightText: 2026 Vibe Coded Emulator contributors
// SPDX-License-Identifier: GPL-3.0-or-later
//
//! Test-only structured UI control bridge.
//!
//! The result receiver command is always compiled (it is inert), while the
//! loopback HTTP bridge itself is compiled **only** with the `ui-control`
//! cargo feature, enabled by the automation E2E build and never by a
//! distribution build. The bridge drives the real WebView by dispatching real
//! DOM events on real elements (identified by `data-testid`), so a click
//! exercises the same frontend handler a user would.
//!
//! Security properties:
//! - bound to `127.0.0.1` on an ephemeral port only;
//! - requires a random bearer token generated per run;
//! - accepts only a validated `data-testid` (no arbitrary JavaScript);
//! - the port + token are written to the file named by `AN3_UI_CONTROL_FILE`.

use std::collections::HashMap;
use std::sync::mpsc::Sender;
use std::sync::Mutex;

static PENDING: Mutex<Option<HashMap<String, Sender<String>>>> = Mutex::new(None);
static COUNTER: Mutex<u64> = Mutex::new(0);

/// Receives the result of a generated DOM expression from the WebView. Inert
/// unless a bridge request is waiting.
#[tauri::command]
pub fn ui_control_result(request_id: String, payload: String) {
    if let Ok(mut guard) = PENDING.lock() {
        if let Some(map) = guard.as_mut() {
            if let Some(sender) = map.remove(&request_id) {
                let _ = sender.send(payload);
            }
        }
    }
}

fn next_id() -> u64 {
    let mut counter = COUNTER.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    *counter += 1;
    *counter
}

fn valid_testid(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || character == '-' || character == '_')
}

#[cfg(feature = "ui-control")]
mod runtime {
    use serde::Serialize;
    use std::io::{BufRead, BufReader, Read, Write};
    use std::net::{TcpListener, TcpStream};
    use std::sync::mpsc::channel;
    use std::time::Duration;
    use tauri::{AppHandle, Manager};

    use super::{next_id, valid_testid, PENDING};

    const EVAL_TIMEOUT: Duration = Duration::from_secs(10);

    /// Evaluates an expression in the WebView and returns its JSON value. The
    /// expression is generated here from a validated test id, never from caller
    /// JavaScript.
    fn evaluate(app: &AppHandle, expression: &str) -> Result<String, String> {
        let request_id = format!("ui{}", next_id());
        let (sender, receiver) = channel();
        {
            let mut guard = PENDING.lock().map_err(|_| "ui control state is poisoned")?;
            guard
                .get_or_insert_with(std::collections::HashMap::new)
                .insert(request_id.clone(), sender);
        }
        let window = app
            .get_webview_window("main")
            .ok_or_else(|| "the main window is unavailable".to_string())?;
        let id = serde_json::to_string(&request_id).unwrap_or_else(|_| "\"\"".into());
        let js = format!(
            "(function(){{var v;try{{v={expression};}}catch(e){{v={{error:String(e)}};}}\
             window.__TAURI__.core.invoke('ui_control_result',{{requestId:{id},payload:JSON.stringify(v===undefined?null:v)}});}})();"
        );
        window.eval(&js).map_err(|error| error.to_string())?;
        receiver
            .recv_timeout(EVAL_TIMEOUT)
            .map_err(|_| "the web UI did not answer in time".to_string())
    }

    fn node_expression(testid: &str) -> String {
        format!(
            "(function(){{var el=document.querySelector('[data-testid=\"{testid}\"]');if(!el)return null;\
             return {{testid:el.getAttribute('data-testid'),tag:el.tagName.toLowerCase(),\
             role:el.getAttribute('role'),text:((el.innerText||el.textContent)||'').trim().slice(0,160),\
             visible:!!(el.offsetWidth||el.offsetHeight||el.getClientRects().length),disabled:el.disabled===true,state:el.getAttribute('data-state')}};}})()"
        )
    }

    #[derive(Serialize)]
    #[serde(rename_all = "camelCase")]
    struct Node {
        testid: Option<String>,
        tag: Option<String>,
        role: Option<String>,
        text: Option<String>,
        visible: bool,
        disabled: bool,
        state: Option<String>,
    }

    fn parse_node(payload: &str) -> Option<Node> {
        let value: serde_json::Value = serde_json::from_str(payload).ok()?;
        if value.is_null() {
            return None;
        }
        Some(Node {
            testid: value.get("testid").and_then(|v| v.as_str()).map(str::to_owned),
            tag: value.get("tag").and_then(|v| v.as_str()).map(str::to_owned),
            role: value.get("role").and_then(|v| v.as_str()).map(str::to_owned),
            text: value.get("text").and_then(|v| v.as_str()).map(str::to_owned),
            visible: value.get("visible").and_then(|v| v.as_bool()).unwrap_or(false),
            disabled: value.get("disabled").and_then(|v| v.as_bool()).unwrap_or(false),
            state: value.get("state").and_then(|v| v.as_str()).map(str::to_owned),
        })
    }

    fn handle(app: &AppHandle, action: &str, testid: Option<&str>) -> Result<serde_json::Value, String> {
        match action {
            "diag" => {
                let expression = "({href:location.href,title:document.title,ready:document.readyState,\
                    testids:document.querySelectorAll('[data-testid]').length,\
                    systems:(window.AN3NativeIntegratedSystems||[]).join(','),\
                    hasSwitchApi:!!window.AN3NativeSwitch,hasRerender:typeof window.AN3RerenderLibrary,detect:JSON.stringify(window.AN3SwitchDetect||null),\
                    body:document.body?document.body.innerHTML.length:0})";
                let payload = evaluate(app, expression)?;
                Ok(serde_json::from_str(&payload).unwrap_or(serde_json::Value::Null))
            }
            "tree" => {
                let expression = "Array.from(document.querySelectorAll('[data-testid]')).map(function(el){\
                    return {testid:el.getAttribute('data-testid'),tag:el.tagName.toLowerCase(),\
                    role:el.getAttribute('role'),text:((el.innerText||el.textContent)||'').trim().slice(0,160),\
                    visible:!!(el.offsetWidth||el.offsetHeight||el.getClientRects().length),disabled:el.disabled===true,state:el.getAttribute('data-state')};})";
                let payload = evaluate(app, expression)?;
                let nodes: serde_json::Value =
                    serde_json::from_str(&payload).map_err(|error| error.to_string())?;
                Ok(serde_json::json!({ "nodes": nodes }))
            }
            "query" => {
                let testid = testid.ok_or("query requires a testid")?;
                let payload = evaluate(app, &node_expression(testid))?;
                Ok(serde_json::json!({ "node": parse_node(&payload) }))
            }
            "text" => {
                let testid = testid.ok_or("text requires a testid")?;
                let payload = evaluate(app, &node_expression(testid))?;
                let node = parse_node(&payload);
                let text = node.as_ref().and_then(|value| value.text.clone());
                Ok(serde_json::json!({ "text": text, "present": node.is_some() }))
            }
            "click" => {
                let testid = testid.ok_or("click requires a testid")?;
                let expression = format!(
                    "(function(){{var el=document.querySelector('[data-testid=\"{testid}\"]');\
                     if(!el)return {{clicked:false,reason:'missing'}};el.scrollIntoView({{block:'center'}});\
                     el.click();return {{clicked:true}};}})()"
                );
                let payload = evaluate(app, &expression)?;
                Ok(serde_json::from_str(&payload).unwrap_or(serde_json::Value::Null))
            }
            other => Err(format!("unknown ui action: {other}")),
        }
    }

    fn request_head(stream: &TcpStream) -> Option<(String, String, String)> {
        let mut reader = BufReader::new(stream.try_clone().ok()?);
        let mut request = String::new();
        reader.read_line(&mut request).ok()?;
        let mut parts = request.split_whitespace();
        let method = parts.next()?.to_string();
        let path = parts.next()?.to_string();
        let mut token = String::new();
        let mut length = 0usize;
        loop {
            let mut line = String::new();
            if reader.read_line(&mut line).ok()? == 0 || line == "\r\n" || line.is_empty() {
                break;
            }
            if let Some((name, value)) = line.split_once(':') {
                if name.eq_ignore_ascii_case("x-an3-token") {
                    token = value.trim().to_string();
                } else if name.eq_ignore_ascii_case("content-length") {
                    length = value.trim().parse().unwrap_or(0);
                }
            }
        }
        if length > 0 {
            let mut body = vec![0u8; length];
            let _ = reader.read_exact(&mut body);
        }
        Some((method, path, token))
    }

    fn respond(stream: &mut TcpStream, status: &str, body: &str) {
        let payload = body.as_bytes();
        let _ = stream.write_all(
            format!(
                "HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                payload.len()
            )
            .as_bytes(),
        );
        let _ = stream.write_all(payload);
    }

    fn serve(app: AppHandle, token: String, listener: TcpListener) {
        for mut stream in listener.incoming().flatten() {
            let Some((method, path, supplied)) = request_head(&stream) else {
                continue;
            };
            if supplied != token {
                respond(&mut stream, "401 Unauthorized", "{\"error\":\"invalid token\"}");
                continue;
            }
            if method != "GET" && method != "POST" {
                respond(&mut stream, "405 Method Not Allowed", "{\"error\":\"method\"}");
                continue;
            }
            let (route, query) = path.split_once('?').unwrap_or((path.as_str(), ""));
            let testid = query
                .split('&')
                .find_map(|pair| pair.strip_prefix("testid="))
                .map(|value| value.replace("%2D", "-").replace("%5F", "_"));
            let action = match route {
                "/diag" => "diag",
                "/tree" => "tree",
                "/query" => "query",
                "/text" => "text",
                "/click" => "click",
                _ => {
                    respond(&mut stream, "404 Not Found", "{\"error\":\"route\"}");
                    continue;
                }
            };
            if let Some(value) = testid.as_deref() {
                if !valid_testid(value) {
                    respond(&mut stream, "400 Bad Request", "{\"error\":\"invalid testid\"}");
                    continue;
                }
            }
            match handle(&app, action, testid.as_deref()) {
                Ok(value) => respond(&mut stream, "200 OK", &value.to_string()),
                Err(error) => respond(
                    &mut stream,
                    "422 Unprocessable Entity",
                    &serde_json::json!({ "error": error }).to_string(),
                ),
            }
        }
    }

    /// Starts the test bridge when `AN3_UI_CONTROL_FILE` names a writable path.
    /// Returns the bound port.
    pub fn start(app: &AppHandle) -> Result<u16, String> {
        let control_file = std::env::var("AN3_UI_CONTROL_FILE")
            .map_err(|_| "AN3_UI_CONTROL_FILE is not set".to_string())?;
        let token = format!(
            "{:016x}{:016x}",
            next_id().wrapping_mul(0x9E37_79B9_7F4A_7C15),
            std::process::id()
        );
        let listener = TcpListener::bind(("127.0.0.1", 0)).map_err(|error| error.to_string())?;
        let port = listener.local_addr().map_err(|error| error.to_string())?.port();
        std::fs::write(
            &control_file,
            serde_json::json!({ "port": port, "token": token }).to_string(),
        )
        .map_err(|error| format!("cannot write the control file: {error}"))?;
        let app = app.clone();
        std::thread::Builder::new()
            .name("an3-ui-control".into())
            .spawn(move || serve(app, token, listener))
            .map_err(|error| error.to_string())?;
        Ok(port)
    }
}

#[cfg(feature = "ui-control")]
pub use runtime::start;
