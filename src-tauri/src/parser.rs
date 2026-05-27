use once_cell::sync::Lazy;
use regex::Regex;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ActivityEvent {
    Start,
    Thinking,
    ToolCall { tool: String },
    Output { chars: usize },
    Done,
    Error { message: String },
    /// Claude is blocked on a y/n permission prompt — user needs to act.
    AwaitingPermission,
    /// Context is being compacted/summarized.
    Compacting,
    /// Claude asked a clarifying question and is waiting on the user.
    Asking,
    PlanModeEnter,
    PlanModeExit,
    /// Reports the model in use (e.g., "sonnet 4.6", "opus 4.7").
    Model { name: String },
    /// Working directory the session was launched in (shown in the UI roster).
    Cwd { path: String },
}

/// What `Parser::parse` returns. `agent_id == None` means the parent session;
/// `Some(id)` means the event belongs to a detected sub-agent.
#[derive(Debug, Clone)]
pub struct ParseOutput {
    pub agent_id: Option<String>,
    pub event: ActivityEvent,
}

// Claude Code emits tool calls on bullet lines like:
//   ● Bash(ls -la)
//   ● Read(src/foo.rs)
//   ⏺ Edit(file.rs)
//   > Grep(pattern)
// Catch these first — they're the strongest signal.
static RE_BULLET_TOOL: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"^[\s●⏺▶➤*•·>]+\s*([A-Z][A-Za-z]+)\s*\(").unwrap()
});
// Tool result lines start with `⎿` in Claude Code's output.
static RE_TOOL_RESULT: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"^\s*⎿").unwrap()
});
// Status lines like `⠋ Thinking…` or `✻ Researching…`.
static RE_THINKING: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?i)(^|\s)(thinking|pondering|reasoning|analy[sz]ing|researching|compacting|planning)\b|\.{3}|…|[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏✻✶✷✸✹*]").unwrap()
});
static RE_TOOL: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?i)(tool:|running|executing|calling|^bash|^read|^write|^search|^grep)[:\s]+(\w[\w\s-]*)")
        .unwrap()
});
static RE_ERROR: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?i)\b(error|failed|exception|panic|abort)\b").unwrap()
});

// Heuristic sub-agent detection — Claude Code's Task() tool output varies; these
// patterns catch the common shapes. Best-effort.
static RE_TASK_SPAWN: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?i)(Task\s*\(|spawning\s+sub.?agent|starting\s+sub.?agent|launch(?:ing)?\s+(?:agent|task))").unwrap()
});
static RE_TASK_COMPLETE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?i)(task\s+complete|sub.?agent\s+(?:done|finished|complete)|agent\s+returned)").unwrap()
});

// Permission prompts: y/n style approval requests. Tight matches only — the
// general `❯ N.` menu marker is handled by RE_INTERACTIVE_MENU below.
static RE_PERMISSION: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?i)(allow this (?:command|tool|action)|do you want to (?:proceed|continue|run|allow)|\(y/n\)|\[y/N\]|\[Y/n\]|press y to (?:accept|continue|approve|proceed)|approve\?|❯ Yes|^[12]\.\s+(?:Yes|No)\b)").unwrap()
});
// Context compaction.
static RE_COMPACTING: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?i)(compact(?:ing)?\s+(?:conversation|context|history)|summari[sz]ing\s+(?:conversation|context)|auto.?compact|/compact)").unwrap()
});
// Clarifying questions — claude asking the user for input rather than acting.
// Matches lines that START with a common question word and END with `?`.
static RE_ASKING: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?i)^(how|what|where|when|why|which|who|should|would|could|do|does|did|is|are|will|can|may|shall|let me know|please (?:confirm|clarify|specify)).{5,400}\?\s*$").unwrap()
});
// Claude Code interactive menu marker — `❯ 1.` is unique to its prompt UI and
// is the strongest possible "awaiting user input" signal.
static RE_INTERACTIVE_MENU: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"❯\s*\d+\.").unwrap()
});
// Plan-mode boundaries.
static RE_PLAN_ENTER: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?i)(entering plan mode|plan mode (?:active|enabled)|^plan mode:|^plan:\s)").unwrap()
});
static RE_PLAN_EXIT: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?i)(exiting plan mode|plan (?:approved|accepted)|ExitPlanMode|plan mode (?:off|disabled))").unwrap()
});
// Heuristic model detection from Claude Code's startup / status output.
// Catches: "using model: claude-sonnet-4-6", "Model: opus 4.7", "✦ Sonnet 4.6", etc.
static RE_MODEL: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"(?i)(?:(?:using\s+model|model)[:\s]+|\bclaude[\s\-]|^[✦◇✶◆⭑*]\s+)((?:claude[\s\-])?(?:opus|sonnet|haiku)(?:[\s\-]\d(?:[\.\-]\d)?)?)").unwrap()
});

/// Turn things like "claude-sonnet-4-6", "Sonnet 4.6", "sonnet" into a short
/// consistent label suitable for display ("Sonnet 4.6").
pub fn normalize_model_name(raw: &str) -> String {
    let s = raw.to_lowercase();
    let s = s.trim_start_matches("claude-").trim_start_matches("claude ");
    let s = s.replace('-', " ").replace('_', " ");
    let s = s.trim();
    // Capitalize the first word.
    let mut chars = s.chars();
    let cap = chars
        .next()
        .map(|c| c.to_uppercase().to_string())
        .unwrap_or_default()
        + chars.as_str();
    cap
}

fn strip_ansi(s: &str) -> String {
    let out = strip_ansi_escapes::strip_str(s);
    if out.is_empty() {
        s.to_string()
    } else {
        out
    }
}

/// Stateless single-line parser. Returns an `ActivityEvent` for the line, or
/// `None` if the line has nothing worth reporting. Doesn't know about sub-agents.
pub fn parse_line(line: &str) -> Option<ActivityEvent> {
    let cleaned = strip_ansi(line);
    let trimmed = cleaned.trim();
    if trimmed.is_empty() {
        return None;
    }

    // 0a. Permission prompts — highest priority; the user needs to act.
    if RE_PERMISSION.is_match(trimmed) {
        return Some(ActivityEvent::AwaitingPermission);
    }
    // 0a.2. Interactive menu (❯ 1.) — claude is showing a numbered prompt.
    if RE_INTERACTIVE_MENU.is_match(trimmed) {
        return Some(ActivityEvent::Asking);
    }
    // 0b. Plan-mode boundaries (transient).
    if RE_PLAN_EXIT.is_match(trimmed) {
        return Some(ActivityEvent::PlanModeExit);
    }
    if RE_PLAN_ENTER.is_match(trimmed) {
        return Some(ActivityEvent::PlanModeEnter);
    }
    // 0c. Context compaction.
    if RE_COMPACTING.is_match(trimmed) {
        return Some(ActivityEvent::Compacting);
    }
    // 0d. Model identification.
    if let Some(caps) = RE_MODEL.captures(trimmed) {
        if let Some(name) = caps.get(1).map(|m| m.as_str().trim().to_string()) {
            return Some(ActivityEvent::Model {
                name: normalize_model_name(&name),
            });
        }
    }
    // 1. Bullet-style tool invocations from Claude Code.
    if let Some(caps) = RE_BULLET_TOOL.captures(trimmed) {
        let tool = caps
            .get(1)
            .map(|m| m.as_str().trim().to_string())
            .unwrap_or_else(|| "unknown".to_string());
        return Some(ActivityEvent::ToolCall { tool });
    }
    // 2. Tool result lines — claude is processing the output.
    if RE_TOOL_RESULT.is_match(trimmed) {
        return Some(ActivityEvent::Thinking);
    }
    // 3. Generic verb-tool patterns.
    if RE_TOOL.is_match(trimmed) {
        let caps = RE_TOOL.captures(trimmed).unwrap();
        let tool = caps
            .get(2)
            .map(|m| m.as_str().trim().to_string())
            .unwrap_or_else(|| "unknown".to_string());
        return Some(ActivityEvent::ToolCall { tool });
    }
    // 4. Errors.
    if RE_ERROR.is_match(trimmed) {
        return Some(ActivityEvent::Error {
            message: trimmed.to_string(),
        });
    }
    // 5. Asking — must come BEFORE thinking/output (otherwise the line is just "output").
    if RE_ASKING.is_match(trimmed) {
        return Some(ActivityEvent::Asking);
    }
    // 6. Status / spinner lines.
    if RE_THINKING.is_match(trimmed) {
        return Some(ActivityEvent::Thinking);
    }
    // 7. Anything else with content.
    if trimmed.len() > 3 {
        return Some(ActivityEvent::Output {
            chars: trimmed.len(),
        });
    }
    None
}

/// Stateful parser that tracks the current sub-agent. Emits ParseOutput tagged
/// with `agent_id` when inside a detected Task(...) block.
pub struct Parser {
    current_subagent: Option<String>,
    counter: u32,
}

impl Default for Parser {
    fn default() -> Self {
        Self::new()
    }
}

impl Parser {
    pub fn new() -> Self {
        Self {
            current_subagent: None,
            counter: 0,
        }
    }

    pub fn parse(&mut self, line: &str) -> Option<ParseOutput> {
        let cleaned = strip_ansi(line);
        let trimmed = cleaned.trim();
        if trimmed.is_empty() {
            return None;
        }

        // Sub-agent boundaries take priority.
        if RE_TASK_SPAWN.is_match(trimmed) {
            self.counter = self.counter.wrapping_add(1);
            let id = format!("sa-{}", self.counter);
            self.current_subagent = Some(id.clone());
            return Some(ParseOutput {
                agent_id: Some(id),
                event: ActivityEvent::Start,
            });
        }
        if RE_TASK_COMPLETE.is_match(trimmed) {
            let id = self.current_subagent.take();
            return Some(ParseOutput {
                agent_id: id,
                event: ActivityEvent::Done,
            });
        }

        // Regular event, tagged with current sub-agent if any.
        let event = parse_line(trimmed)?;
        Some(ParseOutput {
            agent_id: self.current_subagent.clone(),
            event,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn detects_thinking() {
        assert!(matches!(parse_line("Thinking..."), Some(ActivityEvent::Thinking)));
        assert!(matches!(parse_line("⠋"), Some(ActivityEvent::Thinking)));
    }

    #[test]
    fn detects_tool_call() {
        let ev = parse_line("Running bash: ls -la");
        assert!(matches!(ev, Some(ActivityEvent::ToolCall { .. })));
    }

    #[test]
    fn detects_error() {
        assert!(matches!(
            parse_line("Error: command not found"),
            Some(ActivityEvent::Error { .. })
        ));
    }

    #[test]
    fn detects_output() {
        assert!(matches!(
            parse_line("Here is the result of your query"),
            Some(ActivityEvent::Output { .. })
        ));
    }

    #[test]
    fn ignores_empty() {
        assert!(parse_line("").is_none());
        assert!(parse_line("   ").is_none());
    }

    #[test]
    fn strips_ansi_before_parsing() {
        let ansi = "\x1b[31mError: boom\x1b[0m";
        assert!(matches!(parse_line(ansi), Some(ActivityEvent::Error { .. })));
    }

    #[test]
    fn detects_permission_prompt() {
        assert!(matches!(
            parse_line("Do you want to proceed? (y/n)"),
            Some(ActivityEvent::AwaitingPermission)
        ));
        assert!(matches!(
            parse_line("Allow this command to run? [y/N]"),
            Some(ActivityEvent::AwaitingPermission)
        ));
    }

    #[test]
    fn detects_compacting() {
        assert!(matches!(
            parse_line("Compacting conversation history..."),
            Some(ActivityEvent::Compacting)
        ));
        assert!(matches!(
            parse_line("/compact"),
            Some(ActivityEvent::Compacting)
        ));
    }

    #[test]
    fn detects_asking_question() {
        assert!(matches!(
            parse_line("Should I include tests in this implementation?"),
            Some(ActivityEvent::Asking)
        ));
        assert!(matches!(
            parse_line("Would you like me to refactor the helper too?"),
            Some(ActivityEvent::Asking)
        ));
        // Other question-starters
        assert!(matches!(
            parse_line("How should pricing items be structured from an uploaded doc?"),
            Some(ActivityEvent::Asking)
        ));
        assert!(matches!(
            parse_line("What format do you want me to use?"),
            Some(ActivityEvent::Asking)
        ));
    }

    #[test]
    fn detects_interactive_menu() {
        // Claude Code's `❯ 1.` selector marker
        assert!(matches!(
            parse_line("❯ 1. Auto-extract on upload"),
            Some(ActivityEvent::Asking)
        ));
        assert!(matches!(
            parse_line("  ❯ 2. Dynamic at query time"),
            Some(ActivityEvent::Asking)
        ));
    }

    #[test]
    fn detects_plan_mode_transitions() {
        assert!(matches!(
            parse_line("Entering plan mode"),
            Some(ActivityEvent::PlanModeEnter)
        ));
        assert!(matches!(
            parse_line("Exiting plan mode"),
            Some(ActivityEvent::PlanModeExit)
        ));
    }

    #[test]
    fn detects_model_lines() {
        let cases = [
            ("Using model: claude-sonnet-4-6", "Sonnet 4 6"),
            ("Model: opus 4.7", "Opus 4.7"),
            ("✦ Sonnet 4.6", "Sonnet 4.6"),
        ];
        for (input, expected) in cases {
            match parse_line(input) {
                Some(ActivityEvent::Model { name }) => assert_eq!(name, expected, "input was {:?}", input),
                other => panic!("expected Model for {:?}, got {:?}", input, other),
            }
        }
    }

    #[test]
    fn parser_detects_sub_agent_lifecycle() {
        let mut p = Parser::new();

        let out = p.parse("● Task(general-purpose, \"search for X\")").unwrap();
        assert!(out.agent_id.is_some());
        assert!(matches!(out.event, ActivityEvent::Start));
        let sa_id = out.agent_id.clone().unwrap();

        let out = p.parse("Thinking about the problem").unwrap();
        assert_eq!(out.agent_id.as_deref(), Some(sa_id.as_str()));
        assert!(matches!(out.event, ActivityEvent::Thinking));

        let out = p.parse("Task complete").unwrap();
        assert_eq!(out.agent_id.as_deref(), Some(sa_id.as_str()));
        assert!(matches!(out.event, ActivityEvent::Done));

        // After completion, events go back to the parent.
        let out = p.parse("Final answer here").unwrap();
        assert!(out.agent_id.is_none());
    }
}
