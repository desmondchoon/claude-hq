use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};

use crate::parser::ActivityEvent;

/// Payload posted by a shim to the daemon's `/event` endpoint.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EventPayload {
    pub session_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub agent_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub parent_id: Option<String>,
    pub event: ActivityEvent,
}

/// What the daemon broadcasts to WS subscribers. Flattens the event kind so
/// the frontend can read `type`/`tool`/`chars` etc. directly.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionEvent {
    pub session_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub agent_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub parent_id: Option<String>,
    pub ts: u128,
    #[serde(flatten)]
    pub event: ActivityEvent,
}

pub fn now_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0)
}

pub fn wrap_payload(payload: EventPayload) -> SessionEvent {
    SessionEvent {
        session_id: payload.session_id,
        agent_id: payload.agent_id,
        parent_id: payload.parent_id,
        ts: now_ms(),
        event: payload.event,
    }
}

pub fn to_json(env: &SessionEvent) -> String {
    serde_json::to_string(env).unwrap_or_else(|_| "{}".into())
}

/// Stable-ish session id: PID + start time millis. Avoids needing a UUID dep.
pub fn make_session_id() -> String {
    let pid = std::process::id();
    let ts = now_ms();
    format!("s-{}-{}", pid, ts)
}
