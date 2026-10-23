// EscapeBase44: the `base44:runtime/actors` module your actors import, as it
// runs on your own server. The host's `deno.json` import map resolves the
// specifier here, so an actor written on Base44 loads unchanged.
//
// The contract is Base44's (`@base44/sdk` `dist/actor.d.ts` + the actors
// pages of its docs, measured live on 2026-09-18): the handlers you write
// (`handleConnect`, `handleMessage`, `handleClose`, `handleStart`,
// `handleWake`, `handleTick`, `shouldTick`, `tickIntervalMs`) and the members
// you call (`broadcast`, `getConnections`, `storage`, `schedule`,
// `cancelSchedule`, `instanceId`, `client`). Everything the platform keeps
// for an instance lives in a private slot — never on `this` — so nothing you
// name on your class can collide with it.

export interface ConnIdentity {
  readonly type: "authenticated" | "anonymous";
  readonly userId?: string;
  readonly anonymousId?: string;
}

export interface Conn<Send = unknown> {
  /** Per-connection id (one per socket/tab), chosen by the client and reused across reconnects. */
  readonly id: string;
  /** The platform-verified principal behind the socket. */
  readonly identity?: ConnIdentity;
  send(data: Send): void;
  /** Refuse the connection — closes the socket with `code` + `reason`. Return right after. */
  reject(code: number, reason: string): void;
}

export interface Storage {
  get<T = unknown>(key: string): Promise<T | undefined>;
  put(key: string, value: unknown): Promise<void>;
  delete(key: string): Promise<boolean>;
  /** Wipe the room's entire persisted storage. */
  deleteAll(): Promise<void>;
}

// What the host wires into every instance. Defined here so the worker and
// the base class agree on one shape; user code never sees it.
export interface ActorContext {
  instanceId: string;
  storage: Storage;
  connections(): Conn[];
  broadcast(data: unknown): void;
  schedule(key: string, atMs: number): Promise<void>;
  cancelSchedule(key: string): Promise<void>;
  client(): unknown;
  /** Re-evaluate `shouldTick()` — the platform owns the ticker's loop. */
  tickerChanged(): void;
}

const CONTEXT = new WeakMap<Actor, ActorContext>();

/** The worker binds an instance to its room; not part of the public contract. */
export function bindActorContext(actor: Actor, ctx: ActorContext): void {
  CONTEXT.set(actor, ctx);
}

function ctxOf(actor: Actor): ActorContext {
  const ctx = CONTEXT.get(actor);
  if (!ctx) throw new Error("This Actor instance is not bound to a room — actor members are only available inside a deployed actor");
  return ctx;
}

export abstract class Actor<Incoming = unknown, Outgoing = unknown> {
  abstract handleConnect(conn: Conn<Outgoing>): void | Promise<void>;
  abstract handleMessage(conn: Conn<Outgoing>, msg: Incoming): void | Promise<void>;
  abstract handleClose(conn: Conn<Outgoing>): void | Promise<void>;
  /** The managed ticker's callback — runs only while `shouldTick()` returns true. */
  handleTick(): void | Promise<void> {}
  /** Runs once when the instance starts, before any connection is handled. */
  handleStart(): void | Promise<void> {}
  /** A timer armed with `schedule(key, at)` came due. One-shot. */
  handleWake(_key: string): void | Promise<void> {}
  /** Override to opt into the managed ticker; must be cheap and side-effect free. */
  shouldTick?(): boolean;
  /** Ticker period in ms. Default 100. */
  tickIntervalMs = 100;

  protected async schedule(key: string, at: number | Date): Promise<void> {
    await ctxOf(this).schedule(key, at instanceof Date ? at.getTime() : at);
  }

  protected async cancelSchedule(key: string): Promise<void> {
    await ctxOf(this).cancelSchedule(key);
  }

  protected broadcast(data: Outgoing): void {
    ctxOf(this).broadcast(data);
  }

  protected getConnections(): Conn<Outgoing>[] {
    return ctxOf(this).connections() as Conn<Outgoing>[];
  }

  protected get instanceId(): string {
    return ctxOf(this).instanceId;
  }

  protected get storage(): Storage {
    return ctxOf(this).storage;
  }

  /**
   * A Base44 client scoped to this instance — anonymous by default, with
   * `asServiceRole` for validated, room-owned work. Talks to this app's own
   * backend.
   */
  // deno-lint-ignore no-explicit-any
  protected get client(): any {
    return ctxOf(this).client();
  }
}
