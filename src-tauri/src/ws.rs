use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        State,
    },
    response::Response,
    routing::{get, post},
    Json, Router,
};
use std::sync::Arc;
use tokio::sync::broadcast;

use claude_hq_core::event::{to_json, wrap_payload, EventPayload};

pub type EventTx = broadcast::Sender<String>;

#[derive(Clone)]
pub struct AppState {
    pub tx: Arc<EventTx>,
}

pub async fn start_ws_server(tx: EventTx) {
    let state = AppState { tx: Arc::new(tx) };

    let app = Router::new()
        .route("/", get(ws_handler))
        .route("/subscribe", get(ws_handler))
        .route("/event", post(post_event))
        .with_state(state);

    let mut listener = None;
    for port in claude_hq_core::DEFAULT_PORT_START..=claude_hq_core::DEFAULT_PORT_END {
        match tokio::net::TcpListener::bind(("127.0.0.1", port)).await {
            Ok(l) => {
                eprintln!("[claude-hq] WS+HTTP listening on 127.0.0.1:{}", port);
                listener = Some(l);
                break;
            }
            Err(e) => {
                eprintln!("[claude-hq] port {} busy ({}), trying next", port, e);
            }
        }
    }
    let listener = listener.expect("[claude-hq] no free port available");
    if let Err(e) = axum::serve(listener, app).await {
        eprintln!("[claude-hq] server exited: {}", e);
    }
}

async fn ws_handler(ws: WebSocketUpgrade, State(state): State<AppState>) -> Response {
    let rx = state.tx.subscribe();
    ws.on_upgrade(move |socket| handle_socket(socket, rx))
}

async fn handle_socket(mut socket: WebSocket, mut rx: broadcast::Receiver<String>) {
    loop {
        tokio::select! {
            msg = rx.recv() => {
                match msg {
                    Ok(text) => {
                        if socket.send(Message::Text(text)).await.is_err() {
                            break;
                        }
                    }
                    Err(broadcast::error::RecvError::Lagged(_)) => continue,
                    Err(_) => break,
                }
            }
            _ = tokio::time::sleep(tokio::time::Duration::from_secs(5)) => {
                if socket.send(Message::Ping(vec![])).await.is_err() { break; }
            }
        }
    }
}

async fn post_event(
    State(state): State<AppState>,
    Json(payload): Json<EventPayload>,
) -> &'static str {
    let env = wrap_payload(payload);
    let _ = state.tx.send(to_json(&env));
    "ok"
}
