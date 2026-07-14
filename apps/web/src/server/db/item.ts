import {
  DeleteCommand,
  GetCommand,
  PutCommand,
  QueryCommand,
  UpdateCommand,
} from "@aws-sdk/lib-dynamodb";
import type { JsonValue } from "@adele/shared";

import { documentClient, getDynamoConfig, type DynamoSender } from "./client";
import type { AdeleDbItem, EntityType } from "./keys";
import { entityVersion } from "./keys";

export type DbClient = DynamoSender;

export interface ListOptions {
  limit?: number;
}

export function nowIso() {
  return new Date().toISOString();
}

export function createItem<TData extends JsonValue | Record<string, unknown>>(
  input: Omit<AdeleDbItem<TData>, "version"> & { version?: number },
): AdeleDbItem<TData> {
  return {
    ...input,
    version: input.version ?? entityVersion,
  };
}

export async function putItem<TData extends JsonValue | Record<string, unknown>>(
  item: AdeleDbItem<TData>,
  client: DbClient = documentClient,
) {
  const { tableName } = getDynamoConfig();
  await client.send(
    new PutCommand({
      TableName: tableName,
      Item: item,
    }),
  );
  return item;
}

export async function getItem<TData extends JsonValue | Record<string, unknown>>(
  key: { pk: string; sk: string },
  entityType: EntityType,
  client: DbClient = documentClient,
) {
  const { tableName } = getDynamoConfig();
  const result = (await client.send(
    new GetCommand({
      TableName: tableName,
      Key: key,
    }),
  )) as { Item?: AdeleDbItem<TData> };

  if (!result.Item || result.Item.entityType !== entityType) {
    return null;
  }

  return result.Item;
}

export async function deleteItem(
  key: { pk: string; sk: string },
  client: DbClient = documentClient,
) {
  const { tableName } = getDynamoConfig();
  await client.send(
    new DeleteCommand({
      TableName: tableName,
      Key: key,
    }),
  );
}

export async function queryItems<TData extends JsonValue | Record<string, unknown>>(
  input: {
    keyConditionExpression: string;
    expressionAttributeNames?: Record<string, string>;
    expressionAttributeValues: Record<string, unknown>;
    indexName?: string;
    limit?: number;
    scanIndexForward?: boolean;
  },
  client: DbClient = documentClient,
) {
  const { tableName } = getDynamoConfig();
  const result = (await client.send(
    new QueryCommand({
      TableName: tableName,
      IndexName: input.indexName,
      KeyConditionExpression: input.keyConditionExpression,
      ExpressionAttributeNames: input.expressionAttributeNames,
      ExpressionAttributeValues: input.expressionAttributeValues,
      Limit: input.limit,
      ScanIndexForward: input.scanIndexForward,
    }),
  )) as { Items?: AdeleDbItem<TData>[] };

  return result.Items ?? [];
}

export async function updateItem(
  input: {
    key: { pk: string; sk: string };
    updateExpression: string;
    expressionAttributeNames?: Record<string, string>;
    expressionAttributeValues: Record<string, unknown>;
  },
  client: DbClient = documentClient,
) {
  const { tableName } = getDynamoConfig();
  const result = (await client.send(
    new UpdateCommand({
      TableName: tableName,
      Key: input.key,
      UpdateExpression: input.updateExpression,
      ExpressionAttributeNames: input.expressionAttributeNames,
      ExpressionAttributeValues: input.expressionAttributeValues,
      ReturnValues: "ALL_NEW",
    }),
  )) as { Attributes?: AdeleDbItem<Record<string, unknown>> };

  return result.Attributes ?? null;
}
