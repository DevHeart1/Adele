import assert from "node:assert/strict";
import test from "node:test";
import {
  approvalRequestSchema,
  browserActionSchema,
  browserSnapshotSchema,
  connectorConfigSchema,
  memoryEntrySchema,
  taskRunSchema,
  userPreferenceSchema,
} from "../dist/index.js";

const now = "2026-06-18T10:00:00.000Z";

test("memory entries are JSON-compatible and reviewable", () => {
  const entry = memoryEntrySchema.parse({
    memoryId: "mem_1",
    userId: "user_1",
    category: "profile",
    title: "Resume highlights",
    content: "Built an AI desktop assistant.",
    createdAt: now,
    updatedAt: now,
  });

  assert.equal(entry.reviewStatus, "pending");
  assert.deepEqual(entry.tags, []);
});

test("task runs can include plans and milestones", () => {
  const task = taskRunSchema.parse({
    taskId: "task_1",
    userId: "user_1",
    title: "Apply to job",
    goal: "Review a job and draft safe answers",
    status: "planning",
    plan: {
      planId: "plan_1",
      taskId: "task_1",
      summary: "Read listing, compare memory, draft answers",
      milestones: [
        {
          milestoneId: "mile_1",
          taskId: "task_1",
          title: "Read listing",
          goal: "Extract job requirements",
          successSignal: "Requirements saved",
          status: "pending",
          createdAt: now,
          updatedAt: now,
        },
      ],
      createdAt: now,
      updatedAt: now,
    },
    createdAt: now,
    updatedAt: now,
  });

  assert.equal(task.plan?.milestones[0]?.hintTools.length, 0);
});

test("browser snapshot and action contracts validate extension data", () => {
  const snapshot = browserSnapshotSchema.parse({
    snapshotId: "snap_1",
    sessionId: "session_1",
    userId: "user_1",
    url: "https://example.com/job",
    generation: 1,
    capturedAt: now,
    viewport: { width: 1440, height: 900 },
    elements: [
      {
        refId: "el_1",
        role: "button",
        name: "Apply",
        visible: true,
        rect: { x: 20, y: 40, width: 100, height: 32 },
      },
    ],
  });

  const action = browserActionSchema.parse({
    actionId: "act_1",
    userId: "user_1",
    sessionId: snapshot.sessionId,
    type: "click",
    refId: "el_1",
    createdAt: now,
  });

  assert.equal(action.requiresApproval, false);
});

test("approval requests require risk, reason, payload, and status", () => {
  const approval = approvalRequestSchema.parse({
    approvalId: "approval_1",
    userId: "user_1",
    taskId: "task_1",
    actionType: "submit_application",
    target: "Example Careers",
    risk: "high",
    reason: "Submitting an external application is irreversible.",
    proposedPayload: { answer: "Draft answer" },
    status: "pending",
    createdAt: now,
  });

  assert.equal(approval.risk, "high");
});

test("connector config and preferences keep safe defaults", () => {
  const connector = connectorConfigSchema.parse({
    connectorId: "conn_1",
    userId: "user_1",
    provider: "mcp",
    name: "Local MCP",
    createdAt: now,
    updatedAt: now,
  });
  const preferences = userPreferenceSchema.parse({
    userId: "user_1",
    updatedAt: now,
  });

  assert.equal(connector.enabled, true);
  assert.equal(preferences.memoryEnabled, true);
  assert.ok(preferences.approvalRequiredFor.includes("send_email"));
});
