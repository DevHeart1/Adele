import {
  memoryEntrySchema,
  type MemoryEntry,
} from "@adele/shared";
import type { z } from "zod";

import type { DbClient, ListOptions } from "./item";
import { createItem, deleteItem, getItem, putItem, queryItems } from "./item";
import {
  memoryCategoryGsi,
  memorySk,
  userPk,
  type AdeleDbItem,
} from "./keys";

type MemoryItem = AdeleDbItem<MemoryEntry>;

function toItem(memory: MemoryEntry): MemoryItem {
  return createItem({
    pk: userPk(memory.userId),
    sk: memorySk(memory.memoryId),
    gsi1pk: memoryCategoryGsi(memory.userId, memory.category),
    gsi1sk: memory.updatedAt,
    entityType: "memory",
    data: memory,
    createdAt: memory.createdAt,
    updatedAt: memory.updatedAt,
  });
}

export async function putMemoryEntry(
  memory: z.input<typeof memoryEntrySchema>,
  client?: DbClient,
) {
  const parsed = memoryEntrySchema.parse(memory);
  await putItem(toItem(parsed), client);
  return parsed;
}

export async function getMemoryEntry(
  userId: string,
  memoryId: string,
  client?: DbClient,
) {
  const item = await getItem<MemoryEntry>(
    { pk: userPk(userId), sk: memorySk(memoryId) },
    "memory",
    client,
  );
  return item ? memoryEntrySchema.parse(item.data) : null;
}

export async function listMemoryEntries(
  userId: string,
  options: ListOptions & { category?: MemoryEntry["category"] } = {},
  client?: DbClient,
) {
  const items = await queryItems<MemoryEntry>(
    options.category
      ? {
          indexName: "GSI1",
          keyConditionExpression: "gsi1pk = :gsi1pk",
          expressionAttributeValues: {
            ":gsi1pk": memoryCategoryGsi(userId, options.category),
          },
          limit: options.limit,
          scanIndexForward: false,
        }
      : {
          keyConditionExpression: "pk = :pk AND begins_with(sk, :prefix)",
          expressionAttributeValues: {
            ":pk": userPk(userId),
            ":prefix": "MEMORY#",
          },
          limit: options.limit,
          scanIndexForward: false,
        },
    client,
  );

  return items.map((item) => memoryEntrySchema.parse(item.data));
}

export async function deleteMemoryEntry(
  userId: string,
  memoryId: string,
  client?: DbClient,
) {
  await deleteItem({ pk: userPk(userId), sk: memorySk(memoryId) }, client);
}
