import {
  DescribeTableCommand,
  DynamoDBClient,
  type DynamoDBClientConfig,
} from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";

export interface DynamoSender {
  send(command: unknown): Promise<unknown>;
}

export interface DynamoConfig {
  region: string;
  tableName: string;
}

const DEFAULT_REGION = "us-east-1";
const DEFAULT_TABLE_NAME = "AdeleWeb";

export function getDynamoConfig(): DynamoConfig {
  return {
    region: process.env.AWS_REGION ?? DEFAULT_REGION,
    tableName: process.env.ADELE_DYNAMODB_TABLE ?? DEFAULT_TABLE_NAME,
  };
}

export function createDynamoClient(config: DynamoDBClientConfig = {}) {
  const { region } = getDynamoConfig();
  return new DynamoDBClient({
    region,
    ...config,
  });
}

export function createDocumentClient(client = createDynamoClient()) {
  return DynamoDBDocumentClient.from(client, {
    marshallOptions: {
      convertClassInstanceToMap: true,
      removeUndefinedValues: true,
    },
  });
}

export const dynamoClient = createDynamoClient();
export const documentClient = createDocumentClient(dynamoClient);

export async function checkDynamoHealth(client: DynamoSender = dynamoClient) {
  const config = getDynamoConfig();
  const result = (await client.send(
    new DescribeTableCommand({ TableName: config.tableName }),
  )) as {
    Table?: {
      TableName?: string;
      TableStatus?: string;
      BillingModeSummary?: { BillingMode?: string };
      ItemCount?: number;
    };
  };

  return {
    ok: result.Table?.TableStatus === "ACTIVE",
    region: config.region,
    tableName: config.tableName,
    tableStatus: result.Table?.TableStatus ?? "UNKNOWN",
    billingMode: result.Table?.BillingModeSummary?.BillingMode ?? "UNKNOWN",
    itemCount: result.Table?.ItemCount ?? null,
  };
}
