import { describe, expect, it } from "vitest";

import { SseParser } from "./sse";

describe("SseParser", () => {
  it("parses events split across chunks and skips pings", () => {
    const parser = new SseParser();
    expect(parser.push(": ping\n\nevent: run\nda")).toEqual([]);
    expect(parser.push('ta: {"run_id":"al-1"}\n\nevent: step\ndata: {"step":1}\n\n')).toEqual([
      { event: "run", data: '{"run_id":"al-1"}' },
      { event: "step", data: '{"step":1}' },
    ]);
  });

  it("joins multi-line data and handles CRLF", () => {
    const parser = new SseParser();
    expect(parser.push("event: result\r\ndata: a\r\ndata: b\r\n\r\n")).toEqual([
      { event: "result", data: "a\nb" },
    ]);
  });
});
