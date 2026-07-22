import assert from "node:assert/strict";
import test from "node:test";

import {
    isTerminalStreamEvent,
    shouldReportStreamError,
} from "./stream-lifecycle.ts";

test("plain DONE payload is terminal", () => {
    assert.equal(isTerminalStreamEvent("[DONE]"), true);
});

test("named done event is terminal", () => {
    assert.equal(isTerminalStreamEvent(undefined, "done"), true);
});

test("STREAM_END event is terminal", () => {
    assert.equal(isTerminalStreamEvent(undefined, "STREAM_END"), true);
});

test("ordinary message is not terminal", () => {
    assert.equal(isTerminalStreamEvent('{"type":"PROGRESS"}'), false);
});

test("stopped stream does not report a transport error", () => {
    assert.equal(shouldReportStreamError(false), false);
});

test("active stream reports a transport error", () => {
    assert.equal(shouldReportStreamError(true), true);
});
