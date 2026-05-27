// Tries 7823..=7833 to match Rust-side port fallback.
const PORTS = Array.from({ length: 11 }, (_, i) => 7823 + i);
let socket;
let retryDelay = 500;
let portIndex = 0;

function connect() {
  const port = PORTS[portIndex % PORTS.length];
  const url = `ws://127.0.0.1:${port}`;
  socket = new WebSocket(url);

  socket.onopen = () => {
    retryDelay = 500;
    window.dispatchEvent(new CustomEvent('claudeConnected'));
  };

  socket.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data);
      window.dispatchEvent(new CustomEvent('claudeEvent', { detail: event }));
    } catch {}
  };

  socket.onclose = () => {
    window.dispatchEvent(new CustomEvent('claudeDisconnected'));
    portIndex++;
    setTimeout(connect, retryDelay);
    retryDelay = Math.min(retryDelay * 2, 10000);
  };

  socket.onerror = () => {
    try { socket.close(); } catch {}
  };
}

connect();
