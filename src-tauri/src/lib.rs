pub mod event;
pub mod parser;

pub use event::{
    make_session_id, now_ms, to_json, wrap_payload, EventPayload, SessionEvent,
};
pub use parser::{parse_line, ActivityEvent, ParseOutput};

pub const DEFAULT_PORT_START: u16 = 7823;
pub const DEFAULT_PORT_END: u16 = 7833;
