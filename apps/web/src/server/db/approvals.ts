import {
  approvalRequestSchema,
  type ApprovalRequest,
} from "@adele/shared";
import type { z } from "zod";

import type { DbClient, ListOptions } from "./item";
import {
  createItem,
  getItem,
  putItem,
  queryItems,
  updateItem,
} from "./item";
import {
  approvalSk,
  approvalStatusGsi,
  userPk,
  type AdeleDbItem,
} from "./keys";

type ApprovalItem = AdeleDbItem<ApprovalRequest>;

function toItem(approval: ApprovalRequest): ApprovalItem {
  return createItem({
    pk: userPk(approval.userId),
    sk: approvalSk(approval.approvalId),
    gsi1pk: approvalStatusGsi(approval.userId, approval.status),
    gsi1sk: approval.createdAt,
    entityType: "approval",
    data: approval,
    createdAt: approval.createdAt,
    updatedAt: approval.resolvedAt ?? approval.createdAt,
  });
}

export async function putApprovalRequest(
  approval: z.input<typeof approvalRequestSchema>,
  client?: DbClient,
) {
  const parsed = approvalRequestSchema.parse(approval);
  await putItem(toItem(parsed), client);
  return parsed;
}

export async function getApprovalRequest(
  userId: string,
  approvalId: string,
  client?: DbClient,
) {
  const item = await getItem<ApprovalRequest>(
    { pk: userPk(userId), sk: approvalSk(approvalId) },
    "approval",
    client,
  );
  return item ? approvalRequestSchema.parse(item.data) : null;
}

export async function listApprovalRequests(
  userId: string,
  options: ListOptions & { status?: ApprovalRequest["status"] } = {
    status: "pending",
  },
  client?: DbClient,
) {
  const status = options.status ?? "pending";
  const items = await queryItems<ApprovalRequest>(
    {
      indexName: "GSI1",
      keyConditionExpression: "gsi1pk = :gsi1pk",
      expressionAttributeValues: {
        ":gsi1pk": approvalStatusGsi(userId, status),
      },
      limit: options.limit,
      scanIndexForward: true,
    },
    client,
  );

  return items.map((item) => approvalRequestSchema.parse(item.data));
}

export async function updateApprovalStatus(
  userId: string,
  approvalId: string,
  status: ApprovalRequest["status"],
  client?: DbClient,
) {
  const resolvedAt = new Date().toISOString();
  const updated = await updateItem(
    {
      key: { pk: userPk(userId), sk: approvalSk(approvalId) },
      updateExpression:
        "SET #data.#status = :status, #data.#resolvedAt = :resolvedAt, #gsi1pk = :gsi1pk, #updatedAt = :resolvedAt",
      expressionAttributeNames: {
        "#data": "data",
        "#status": "status",
        "#resolvedAt": "resolvedAt",
        "#gsi1pk": "gsi1pk",
        "#updatedAt": "updatedAt",
      },
      expressionAttributeValues: {
        ":status": status,
        ":resolvedAt": resolvedAt,
        ":gsi1pk": approvalStatusGsi(userId, status),
      },
    },
    client,
  );

  return updated ? approvalRequestSchema.parse(updated.data) : null;
}
