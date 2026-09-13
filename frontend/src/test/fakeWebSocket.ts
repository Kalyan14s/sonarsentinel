/** Minimal WebSocket stand-in for job subscription tests. */
export class FakeWebSocket {
  static instances: FakeWebSocket[] = [];

  readyState = 0;
  sent: Record<string, unknown>[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((message: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  static last(): FakeWebSocket {
    return FakeWebSocket.instances[FakeWebSocket.instances.length - 1] as FakeWebSocket;
  }

  static reset(): void {
    FakeWebSocket.instances = [];
  }

  send(data: string): void {
    this.sent.push(JSON.parse(data) as Record<string, unknown>);
  }

  close(): void {
    this.readyState = 3;
  }

  /** Server accepts the connection. */
  open(): void {
    this.readyState = 1;
    this.onopen?.();
  }

  /** Server sends a message. */
  emit(event: object): void {
    this.onmessage?.({ data: JSON.stringify(event) });
  }

  /** Connection closes (1006 = dropped). */
  drop(code = 1006): void {
    this.readyState = 3;
    this.onclose?.({ code });
  }
}
