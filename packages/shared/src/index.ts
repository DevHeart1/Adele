import { z } from "zod";

const jsonPrimitiveSchema = z.union([z.string(), z.number(), z.boolean(), z.null()]);

export type JsonPrimitive = z.infer<typeof jsonPrimitiveSchema>;
export type JsonValue =
  | JsonPrimitive
  | { [key: string]: JsonValue }
  | JsonValue[];

export const jsonValueSchema: z.ZodType<JsonValue> = z.lazy(() =>
  z.union([
    jsonPrimitiveSchema,
    z.array(jsonValueSchema),
    z.record(z.string(), jsonValueSchema),
  ]),
);

export const idSchema = z.string().min(1);
export const isoDateTimeSchema = z.string().datetime({ offset: true });

export const taskStatusSchema = z.enum([
  "queued",
  "planning",
  "running",
  "waiting_for_approval",
  "waiting_for_user",
  "blocked",
  "completed",
  "failed",
  "cancelled",
]);

export const taskStepStatusSchema = z.enum([
  "pending",
  "running",
  "waiting_for_approval",
  "completed",
  "failed",
  "skipped",
]);

export const memoryCategorySchema = z.enum([
  "profile",
  "preference",
  "credential_hint",
  "document",
  "job",
  "task",
  "browser",
  "connector",
  "note",
]);

export const memoryReviewStatusSchema = z.enum([
  "pending",
  "approved",
  "rejected",
  "archived",
]);

export const approvalStatusSchema = z.enum([
  "pending",
  "approved",
  "rejected",
  "edited",
  "expired",
  "cancelled",
]);

export const approvalRiskSchema = z.enum(["low", "medium", "high", "critical"]);

export const browserActionTypeSchema = z.enum([
  "read_page",
  "find_element",
  "click",
  "type",
  "select",
  "scroll",
  "extract_data",
  "extract_readability",
  "refresh_snapshot",
]);

export const connectorProviderSchema = z.enum([
  "mcp",
  "composio",
  "google",
  "github",
  "custom",
]);

export const userSchema = z.object({
  userId: idSchema,
  displayName: z.string().optional(),
  email: z.string().email().optional(),
  createdAt: isoDateTimeSchema,
  updatedAt: isoDateTimeSchema,
});

export const memoryEntrySchema = z.object({
  memoryId: idSchema,
  userId: idSchema,
  category: memoryCategorySchema,
  title: z.string().min(1),
  content: z.string(),
  tags: z.array(z.string()).default([]),
  source: z
    .object({
      type: z.enum(["user", "task", "browser", "connector", "import"]),
      taskId: idSchema.optional(),
      url: z.string().url().optional(),
      connectorId: idSchema.optional(),
    })
    .optional(),
  reviewStatus: memoryReviewStatusSchema.default("pending"),
  createdAt: isoDateTimeSchema,
  updatedAt: isoDateTimeSchema,
});

export const milestoneSchema = z.object({
  milestoneId: idSchema,
  taskId: idSchema,
  title: z.string().min(1),
  goal: z.string().min(1),
  successSignal: z.string().min(1),
  status: taskStepStatusSchema,
  dependsOn: z.array(idSchema).default([]),
  hintTools: z.array(z.string()).default([]),
  resultSummary: z.string().optional(),
  createdAt: isoDateTimeSchema,
  updatedAt: isoDateTimeSchema,
});

export const toolCallSchema = z.object({
  toolCallId: idSchema,
  taskId: idSchema,
  stepId: idSchema.optional(),
  toolName: z.string().min(1),
  args: jsonValueSchema,
  result: jsonValueSchema.optional(),
  ok: z.boolean(),
  errorCode: z.string().optional(),
  startedAt: isoDateTimeSchema,
  completedAt: isoDateTimeSchema.optional(),
});

export const taskStepSchema = z.object({
  stepId: idSchema,
  taskId: idSchema,
  index: z.number().int().nonnegative(),
  title: z.string().min(1),
  status: taskStepStatusSchema,
  toolName: z.string().optional(),
  inputSummary: z.string().optional(),
  outputSummary: z.string().optional(),
  error: z.string().optional(),
  approvalId: idSchema.optional(),
  startedAt: isoDateTimeSchema.optional(),
  completedAt: isoDateTimeSchema.optional(),
});

export const planSchema = z.object({
  planId: idSchema,
  taskId: idSchema,
  summary: z.string().min(1),
  milestones: z.array(milestoneSchema).default([]),
  createdAt: isoDateTimeSchema,
  updatedAt: isoDateTimeSchema,
});

export const taskRunSchema = z.object({
  taskId: idSchema,
  userId: idSchema,
  title: z.string().min(1),
  goal: z.string().min(1),
  status: taskStatusSchema,
  plan: planSchema.optional(),
  currentStepId: idSchema.optional(),
  finalResult: z.string().optional(),
  createdAt: isoDateTimeSchema,
  updatedAt: isoDateTimeSchema,
});

export const approvalRequestSchema = z.object({
  approvalId: idSchema,
  userId: idSchema,
  taskId: idSchema,
  stepId: idSchema.optional(),
  actionType: z.string().min(1),
  target: z.string().optional(),
  risk: approvalRiskSchema,
  reason: z.string().min(1),
  proposedPayload: jsonValueSchema,
  status: approvalStatusSchema,
  createdAt: isoDateTimeSchema,
  resolvedAt: isoDateTimeSchema.optional(),
});

export const browserElementRefSchema = z.object({
  refId: idSchema,
  role: z.string().optional(),
  name: z.string().optional(),
  text: z.string().optional(),
  selector: z.string().optional(),
  href: z.string().url().optional(),
  value: z.string().optional(),
  visible: z.boolean().default(true),
  disabled: z.boolean().default(false),
  rect: z
    .object({
      x: z.number(),
      y: z.number(),
      width: z.number().nonnegative(),
      height: z.number().nonnegative(),
    })
    .optional(),
});

export const browserSnapshotSchema = z.object({
  snapshotId: idSchema,
  sessionId: idSchema,
  userId: idSchema,
  tabId: z.string().optional(),
  url: z.string().url(),
  title: z.string().optional(),
  generation: z.number().int().nonnegative(),
  capturedAt: isoDateTimeSchema,
  viewport: z.object({
    width: z.number().int().positive(),
    height: z.number().int().positive(),
  }),
  elements: z.array(browserElementRefSchema).default([]),
});

export const browserActionSchema = z.object({
  actionId: idSchema,
  userId: idSchema,
  taskId: idSchema.optional(),
  sessionId: idSchema,
  type: browserActionTypeSchema,
  refId: idSchema.optional(),
  value: z.string().optional(),
  payload: jsonValueSchema.optional(),
  requiresApproval: z.boolean().default(false),
  createdAt: isoDateTimeSchema,
});

export const browserActionResultSchema = z.object({
  actionId: idSchema,
  sessionId: idSchema,
  ok: z.boolean(),
  message: z.string(),
  result: jsonValueSchema.optional(),
  preGeneration: z.number().int().nonnegative().optional(),
  postGeneration: z.number().int().nonnegative().optional(),
  completedAt: isoDateTimeSchema,
});

export const connectorConfigSchema = z.object({
  connectorId: idSchema,
  userId: idSchema,
  provider: connectorProviderSchema,
  name: z.string().min(1),
  enabled: z.boolean().default(true),
  scopes: z.array(z.string()).default([]),
  config: z.record(z.string(), jsonValueSchema).default({}),
  createdAt: isoDateTimeSchema,
  updatedAt: isoDateTimeSchema,
});

export const userPreferenceSchema = z.object({
  userId: idSchema,
  memoryEnabled: z.boolean().default(true),
  browserAutomationEnabled: z.boolean().default(true),
  connectorAutomationEnabled: z.boolean().default(true),
  approvalRequiredFor: z.array(z.string()).default([
    "submit",
    "send_message",
    "send_email",
    "purchase",
    "delete",
    "payment",
    "credential",
  ]),
  retentionDays: z.number().int().positive().optional(),
  updatedAt: isoDateTimeSchema,
});

export const auditEventSchema = z.object({
  auditEventId: idSchema,
  userId: idSchema,
  taskId: idSchema.optional(),
  stepId: idSchema.optional(),
  actor: z.enum(["user", "agent", "connector", "extension", "system"]),
  eventType: z.string().min(1),
  toolName: z.string().optional(),
  inputSummary: z.string().optional(),
  outputSummary: z.string().optional(),
  approvalId: idSchema.optional(),
  metadata: z.record(z.string(), jsonValueSchema).default({}),
  createdAt: isoDateTimeSchema,
});

export type User = z.infer<typeof userSchema>;
export type MemoryEntry = z.infer<typeof memoryEntrySchema>;
export type TaskRun = z.infer<typeof taskRunSchema>;
export type TaskStep = z.infer<typeof taskStepSchema>;
export type Plan = z.infer<typeof planSchema>;
export type Milestone = z.infer<typeof milestoneSchema>;
export type ApprovalRequest = z.infer<typeof approvalRequestSchema>;
export type BrowserSnapshot = z.infer<typeof browserSnapshotSchema>;
export type BrowserElementRef = z.infer<typeof browserElementRefSchema>;
export type BrowserAction = z.infer<typeof browserActionSchema>;
export type BrowserActionResult = z.infer<typeof browserActionResultSchema>;
export type ConnectorConfig = z.infer<typeof connectorConfigSchema>;
export type ToolCall = z.infer<typeof toolCallSchema>;
export type UserPreference = z.infer<typeof userPreferenceSchema>;
export type AuditEvent = z.infer<typeof auditEventSchema>;
