import type { JsonValue } from "@adele/shared";

export type EntityType =
  | "memory"
  | "task"
  | "taskStep"
  | "approval"
  | "connector";

export interface AdeleDbItem<TData extends JsonValue | Record<string, unknown>> {
  pk: string;
  sk: string;
  gsi1pk?: string;
  gsi1sk?: string;
  entityType: EntityType;
  version: number;
  data: TData;
  createdAt: string;
  updatedAt: string;
}

export const entityVersion = 1;

export function userPk(userId: string) {
  return `USER#${userId}`;
}

export function memorySk(memoryId: string) {
  return `MEMORY#${memoryId}`;
}

export function memoryCategoryGsi(userId: string, category: string) {
  return `USER#${userId}#MEMORY#${category}`;
}

export function taskSk(taskId: string) {
  return `TASK#${taskId}`;
}

export function taskStepSk(taskId: string, stepId: string) {
  return `TASK#${taskId}#STEP#${stepId}`;
}

export function taskStatusGsi(userId: string, status: string) {
  return `USER#${userId}#TASK#${status}`;
}

export function approvalSk(approvalId: string) {
  return `APPROVAL#${approvalId}`;
}

export function approvalStatusGsi(userId: string, status: string) {
  return `USER#${userId}#APPROVAL#${status}`;
}

export function connectorSk(connectorId: string) {
  return `CONNECTOR#${connectorId}`;
}

export function connectorProviderGsi(userId: string, provider: string) {
  return `USER#${userId}#CONNECTOR#${provider}`;
}
