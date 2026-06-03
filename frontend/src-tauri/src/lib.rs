// Jarvis Tauri native shell.
//
// Sets up:
//   * the autostart plugin (launch Jarvis on Windows login),
//   * a system-tray icon with an "Open Jarvis" / "Quit" menu,
//   * showing every window when the tray icon is left-clicked.
//
// The 5 windows themselves are declared statically in tauri.conf.json (labels:
// animation, reasoning, communications, agents, tools) and open on launch.

use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager,
};
use tauri_plugin_autostart::MacosLauncher;

/// Show and focus every Jarvis window.
fn show_all_windows(app: &tauri::AppHandle) {
    for (_label, window) in app.webview_windows() {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            Some(vec![]),
        ))
        .setup(|app| {
            // --- System tray menu: Open Jarvis / Quit ---
            let open_item = MenuItem::with_id(app, "open", "Open Jarvis", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open_item, &quit_item])?;

            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("Jarvis")
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => show_all_windows(app),
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        show_all_windows(tray.app_handle());
                    }
                })
                .build(app)?;

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
