type ChatRequest = {
  message: string;
  transcript_context?: any;
  session_id?: string;
  topic_id?: string;  // Selected advising topic: 'general' or 'course'
};

// Use empty string for Docker (nginx proxy), or localhost for local dev
// VITE_BACKEND_URL="" means use relative paths (nginx will proxy /api to backend)
const API_BASE_URL = (import.meta.env.VITE_BACKEND_URL !== undefined 
  ? import.meta.env.VITE_BACKEND_URL 
  : 'http://localhost:8000').replace(/\/$/, '');

// Stream chat responses from `/api/chat` (text/event-stream). The backend returns SSE-style
// chunks prefixed with `data:`. We use fetch+ReadableStream to consume and parse them.
export async function streamChat(
  req: ChatRequest,
  onEvent: (evt: { type: string; data?: any }) => void
) {
  const res = await fetch(`${API_BASE_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });

  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => '');
    throw new Error(`Chat request failed: ${res.status} ${text}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE messages are delimited by double newlines
      const parts = buffer.split('\n\n');
      buffer = parts.pop() || '';

      for (const part of parts) {
        const line = part.trim();
        if (!line) continue;
        // lines are like: data: {"type":"progress","content":"..."}
        const dataLine = line.split('\n').find((l) => l.startsWith('data:')) || '';
        const payload = dataLine.replace(/^data:\s*/i, '');
        try {
          const obj = JSON.parse(payload);
          onEvent({ type: obj.type || 'message', data: obj });
        } catch (e) {
          // If parse fails, forward raw payload
          onEvent({ type: 'message', data: payload });
        }
      }
    }

    // Process any remaining buffer
    if (buffer.includes('data:')) {
      const payload = buffer.replace(/^data:\s*/i, '').trim();
      try {
        const obj = JSON.parse(payload);
        onEvent({ type: obj.type || 'message', data: obj });
      } catch (e) {
        onEvent({ type: 'message', data: payload });
      }
    }

    onEvent({ type: 'end' });
  } finally {
    reader.releaseLock?.();
  }
}

// Upload a transcript PDF as base64 to `/api/extract-transcript` and return the JSON response.
export async function extractTranscript(file: File, sessionId: string) {
  // Helper to read file as base64
  const toBase64 = (f: File) =>
    new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error('File read error'));
      reader.onload = () => {
        const result = reader.result as string;
        // result is like data:application/pdf;base64,AAAA...
        const commaIdx = result.indexOf(',');
        resolve(commaIdx >= 0 ? result.slice(commaIdx + 1) : result);
      };
      reader.readAsDataURL(f);
    });

  const b64 = await toBase64(file);

  const res = await fetch(`${API_BASE_URL}/api/extract-transcript`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pdf_base64: b64, session_id: sessionId }),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Transcript extraction failed: ${res.status} ${text}`);
  }

  return res.json();
}

export default {
  streamChat,
  extractTranscript,
};