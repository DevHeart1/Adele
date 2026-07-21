//! ADELE Island's optional Windows-only native bridge.
//!
//! This is an independent implementation. It has no UI and communicates only
//! via newline-delimited JSON on stdout/stdin. Notification content never goes
//! through this bridge until the user has explicitly granted that capability.

use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    sync::mpsc,
    time,
};
use windows::{
    Media::Control::{
        GlobalSystemMediaTransportControlsSession,
        GlobalSystemMediaTransportControlsSessionManager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus,
    },
    Win32::System::Com::{CoInitializeEx, COINIT_MULTITHREADED},
};

const VERSION: u8 = 1;

#[derive(Debug, Deserialize)]
struct Command {
    version: u8,
    #[serde(rename = "type")]
    kind: String,
    #[serde(default)]
    payload: Value,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
struct MediaPayload {
    #[serde(rename = "appName")]
    app_name: String,
    title: String,
    artist: String,
    album: String,
    playing: bool,
    #[serde(rename = "durationMs")]
    duration_ms: u64,
    #[serde(rename = "positionMs")]
    position_ms: u64,
}

fn timestamp_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

async fn emit(kind: &str, payload: Value) {
    let message = json!({
        "version": VERSION,
        "type": kind,
        "payload": payload,
        "timestamp": timestamp_ms(),
    });
    let mut stdout = tokio::io::stdout();
    if let Ok(line) = serde_json::to_string(&message) {
        let _ = stdout.write_all(line.as_bytes()).await;
        let _ = stdout.write_all(b"\n").await;
        let _ = stdout.flush().await;
    }
}

async fn read_commands(sender: mpsc::Sender<Command>) {
    let stdin = BufReader::new(tokio::io::stdin());
    let mut lines = stdin.lines();
    while let Ok(Some(line)) = lines.next_line().await {
        if line.len() > 64 * 1024 {
            continue;
        }
        if let Ok(command) = serde_json::from_str::<Command>(&line) {
            if command.version == VERSION {
                let _ = sender.send(command).await;
            }
        }
    }
}

async fn describe_media(session: &GlobalSystemMediaTransportControlsSession) -> windows::core::Result<MediaPayload> {
    let properties = session.TryGetMediaPropertiesAsync()?.await?;
    let playback = session.GetPlaybackInfo()?.PlaybackStatus()?;
    let timeline = session.GetTimelineProperties()?;
    let duration_ms = timeline.EndTime()?.Duration.max(0) as u64 / 10_000;
    let position_ms = timeline.Position()?.Duration.max(0) as u64 / 10_000;
    Ok(MediaPayload {
        // An AUMID is an opaque app identifier. Do not resolve it through the
        // network or log it; the island uses it only as an in-memory label.
        app_name: session.SourceAppUserModelId()?.to_string(),
        title: properties.Title()?.to_string(),
        artist: properties.Artist()?.to_string(),
        album: properties.AlbumTitle()?.to_string(),
        playing: playback == GlobalSystemMediaTransportControlsSessionPlaybackStatus::Playing,
        duration_ms,
        position_ms,
    })
}

async fn execute_command(session: &GlobalSystemMediaTransportControlsSession, command: Command) {
    let operation = match command.kind.as_str() {
        "media.toggle" => session.TryTogglePlayPauseAsync(),
        "media.next" => session.TrySkipNextAsync(),
        "media.previous" => session.TrySkipPreviousAsync(),
        "media.seek" => {
            let Some(position) = command.payload.get("positionMs").and_then(Value::as_u64) else { return; };
            session.TryChangePlaybackPositionAsync(position.min(i64::MAX as u64 / 10_000) as i64 * 10_000)
        }
        _ => return,
    };
    if let Ok(operation) = operation {
        let _ = operation.await;
    }
}

#[tokio::main]
async fn main() {
    // Windows media sessions are a WinRT/COM API. Failure leaves Adele intact;
    // the Electron bridge will keep the optional media surface unavailable.
    unsafe {
        let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
    }

    let manager = match GlobalSystemMediaTransportControlsSessionManager::RequestAsync() {
        Ok(operation) => match operation.await {
            Ok(manager) => manager,
            Err(_) => return,
        },
        Err(_) => return,
    };

    let (command_sender, mut commands) = mpsc::channel(16);
    tokio::spawn(read_commands(command_sender));
    let mut poll = time::interval(Duration::from_millis(750));
    let mut last_media: Option<MediaPayload> = None;

    loop {
        tokio::select! {
            _ = poll.tick() => {
                let current = manager.GetCurrentSession().ok();
                let media = match current.as_ref() {
                    Some(session) => describe_media(session).await.ok(),
                    None => None,
                };
                match (&last_media, &media) {
                    (Some(_), None) => emit("media.stopped", json!({})).await,
                    (_, Some(next)) if last_media.as_ref() != Some(next) => {
                        emit("media.updated", serde_json::to_value(next).unwrap_or_else(|_| json!({}))).await;
                    }
                    _ => {}
                }
                last_media = media;
            }
            Some(command) = commands.recv() => {
                if let Ok(session) = manager.GetCurrentSession() {
                    execute_command(&session, command).await;
                }
            }
        }
    }
}
