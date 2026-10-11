// Minimal Server-Sent Events parser for fetch() streams (EventSource cannot POST).

export interface SseMessage {
  event: string;
  data: string;
}

/** Feed decoded text chunks; returns complete messages and keeps the remainder buffered.
 *  Comment lines (": ping") are ignored. */
export class SseParser {
  private buffer = "";

  push(chunk: string): SseMessage[] {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const messages: SseMessage[] = [];
    let boundary = this.buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      const message = parseBlock(block);
      if (message) messages.push(message);
      boundary = this.buffer.indexOf("\n\n");
    }
    return messages;
  }
}

function parseBlock(block: string): SseMessage | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  if (data.length === 0) return null;
  return { event, data: data.join("\n") };
}

/** Read a streaming Response body as SSE messages. */
export async function* readSse(response: Response): AsyncGenerator<SseMessage> {
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    for (const message of parser.push(decoder.decode(value, { stream: true }))) yield message;
  }
  for (const message of parser.push(decoder.decode() + "\n\n")) yield message;
}
