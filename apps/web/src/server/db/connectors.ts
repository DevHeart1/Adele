import {
  connectorConfigSchema,
  type ConnectorConfig,
} from "@adele/shared";
import type { z } from "zod";

import type { DbClient, ListOptions } from "./item";
import { createItem, deleteItem, getItem, putItem, queryItems } from "./item";
import {
  connectorProviderGsi,
  connectorSk,
  userPk,
  type AdeleDbItem,
} from "./keys";

type ConnectorItem = AdeleDbItem<ConnectorConfig>;

function toItem(connector: ConnectorConfig): ConnectorItem {
  return createItem({
    pk: userPk(connector.userId),
    sk: connectorSk(connector.connectorId),
    gsi1pk: connectorProviderGsi(connector.userId, connector.provider),
    gsi1sk: connector.updatedAt,
    entityType: "connector",
    data: connector,
    createdAt: connector.createdAt,
    updatedAt: connector.updatedAt,
  });
}

export async function putConnectorConfig(
  connector: z.input<typeof connectorConfigSchema>,
  client?: DbClient,
) {
  const parsed = connectorConfigSchema.parse(connector);
  await putItem(toItem(parsed), client);
  return parsed;
}

export async function getConnectorConfig(
  userId: string,
  connectorId: string,
  client?: DbClient,
) {
  const item = await getItem<ConnectorConfig>(
    { pk: userPk(userId), sk: connectorSk(connectorId) },
    "connector",
    client,
  );
  return item ? connectorConfigSchema.parse(item.data) : null;
}

export async function listConnectorConfigs(
  userId: string,
  options: ListOptions & { provider?: ConnectorConfig["provider"] } = {},
  client?: DbClient,
) {
  const items = await queryItems<ConnectorConfig>(
    options.provider
      ? {
          indexName: "GSI1",
          keyConditionExpression: "gsi1pk = :gsi1pk",
          expressionAttributeValues: {
            ":gsi1pk": connectorProviderGsi(userId, options.provider),
          },
          limit: options.limit,
          scanIndexForward: false,
        }
      : {
          keyConditionExpression: "pk = :pk AND begins_with(sk, :prefix)",
          expressionAttributeValues: {
            ":pk": userPk(userId),
            ":prefix": "CONNECTOR#",
          },
          limit: options.limit,
          scanIndexForward: false,
        },
    client,
  );

  return items.map((item) => connectorConfigSchema.parse(item.data));
}

export async function deleteConnectorConfig(
  userId: string,
  connectorId: string,
  client?: DbClient,
) {
  await deleteItem({ pk: userPk(userId), sk: connectorSk(connectorId) }, client);
}
