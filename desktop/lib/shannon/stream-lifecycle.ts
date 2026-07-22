const TERMINAL_EVENT_TYPES = new Set(["done", "STREAM_END"]);

export function isTerminalStreamEvent(data?: string, eventType?: string): boolean {
    return TERMINAL_EVENT_TYPES.has(eventType ?? "") || data?.trim() === "[DONE]";
}

export function shouldReportStreamError(shouldReconnect: boolean): boolean {
    return shouldReconnect;
}
