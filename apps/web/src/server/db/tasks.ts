import {
  taskRunSchema,
  taskStepSchema,
  type TaskRun,
  type TaskStep,
} from "@adele/shared";
import type { z } from "zod";

import type { DbClient, ListOptions } from "./item";
import { createItem, getItem, putItem, queryItems } from "./item";
import {
  taskSk,
  taskStatusGsi,
  taskStepSk,
  userPk,
  type AdeleDbItem,
} from "./keys";

type TaskItem = AdeleDbItem<TaskRun>;
type TaskStepItem = AdeleDbItem<TaskStep>;

function toTaskItem(task: TaskRun): TaskItem {
  return createItem({
    pk: userPk(task.userId),
    sk: taskSk(task.taskId),
    gsi1pk: taskStatusGsi(task.userId, task.status),
    gsi1sk: task.updatedAt,
    entityType: "task",
    data: task,
    createdAt: task.createdAt,
    updatedAt: task.updatedAt,
  });
}

function toTaskStepItem(userId: string, step: TaskStep): TaskStepItem {
  const timestamp = step.completedAt ?? step.startedAt ?? new Date().toISOString();
  return createItem({
    pk: userPk(userId),
    sk: taskStepSk(step.taskId, step.stepId),
    gsi1pk: `USER#${userId}#TASK#${step.taskId}`,
    gsi1sk: `${step.index.toString().padStart(6, "0")}#${timestamp}`,
    entityType: "taskStep",
    data: step,
    createdAt: timestamp,
    updatedAt: timestamp,
  });
}

export async function putTaskRun(
  task: z.input<typeof taskRunSchema>,
  client?: DbClient,
) {
  const parsed = taskRunSchema.parse(task);
  await putItem(toTaskItem(parsed), client);
  return parsed;
}

export async function getTaskRun(
  userId: string,
  taskId: string,
  client?: DbClient,
) {
  const item = await getItem<TaskRun>(
    { pk: userPk(userId), sk: taskSk(taskId) },
    "task",
    client,
  );
  return item ? taskRunSchema.parse(item.data) : null;
}

export async function listTaskRuns(
  userId: string,
  options: ListOptions & { status?: TaskRun["status"] } = {},
  client?: DbClient,
) {
  const items = await queryItems<TaskRun>(
    options.status
      ? {
          indexName: "GSI1",
          keyConditionExpression: "gsi1pk = :gsi1pk",
          expressionAttributeValues: {
            ":gsi1pk": taskStatusGsi(userId, options.status),
          },
          limit: options.limit,
          scanIndexForward: false,
        }
      : {
          keyConditionExpression: "pk = :pk AND begins_with(sk, :prefix)",
          expressionAttributeValues: {
            ":pk": userPk(userId),
            ":prefix": "TASK#",
          },
          limit: options.limit,
          scanIndexForward: false,
        },
    client,
  );

  return items
    .filter((item) => item.entityType === "task")
    .map((item) => taskRunSchema.parse(item.data));
}

export async function putTaskStep(
  userId: string,
  step: z.input<typeof taskStepSchema>,
  client?: DbClient,
) {
  const parsed = taskStepSchema.parse(step);
  await putItem(toTaskStepItem(userId, parsed), client);
  return parsed;
}

export async function listTaskSteps(
  userId: string,
  taskId: string,
  options: ListOptions = {},
  client?: DbClient,
) {
  const items = await queryItems<TaskStep>(
    {
      keyConditionExpression: "pk = :pk AND begins_with(sk, :prefix)",
      expressionAttributeValues: {
        ":pk": userPk(userId),
        ":prefix": `TASK#${taskId}#STEP#`,
      },
      limit: options.limit,
      scanIndexForward: true,
    },
    client,
  );

  return items.map((item) => taskStepSchema.parse(item.data));
}
