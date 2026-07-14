import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { checkDynamoHealth } from "../src/server/db/client";
import { putConnectorConfig } from "../src/server/db/connectors";
import { listMemoryEntries, putMemoryEntry } from "../src/server/db/memory";

class FakeDynamo {
  commands: unknown[] = [];

  constructor(private readonly response: unknown = {}) {}

  async send(command: unknown) {
    this.commands.push(command);
    return this.response;
  }

  lastInput() {
    const command = this.commands.at(-1) as { input?: Record<string, unknown> };
    return command.input ?? {};
  }
}

const timestamp = "2026-06-18T12:00:00.000Z";

describe("web DynamoDB persistence helpers", () => {
  it("writes memory entries with Adele Web partition keys", async () => {
    const fake = new FakeDynamo();

    await putMemoryEntry(
      {
        memoryId: "mem-1",
        userId: "user-1",
        category: "preference",
        title: "Preferred tone",
        content: "Use direct concise status updates.",
        tags: ["tone"],
        reviewStatus: "approved",
        createdAt: timestamp,
        updatedAt: timestamp,
      },
      fake,
    );

    const input = fake.lastInput();
    assert.equal(input.TableName, "AdeleWeb");
    assert.deepEqual(
      {
        pk: (input.Item as Record<string, unknown>).pk,
        sk: (input.Item as Record<string, unknown>).sk,
        gsi1pk: (input.Item as Record<string, unknown>).gsi1pk,
        entityType: (input.Item as Record<string, unknown>).entityType,
      },
      {
        pk: "USER#user-1",
        sk: "MEMORY#mem-1",
        gsi1pk: "USER#user-1#MEMORY#preference",
        entityType: "memory",
      },
    );
  });

  it("lists memory entries by category through GSI1", async () => {
    const fake = new FakeDynamo({ Items: [] });

    await listMemoryEntries(
      "user-1",
      { category: "preference", limit: 10 },
      fake,
    );

    const input = fake.lastInput();
    assert.equal(input.IndexName, "GSI1");
    assert.equal(input.KeyConditionExpression, "gsi1pk = :gsi1pk");
    assert.deepEqual(input.ExpressionAttributeValues, {
      ":gsi1pk": "USER#user-1#MEMORY#preference",
    });
    assert.equal(input.Limit, 10);
  });

  it("applies connector defaults before writing configs", async () => {
    const fake = new FakeDynamo();

    const connector = await putConnectorConfig(
      {
        connectorId: "conn-1",
        userId: "user-1",
        provider: "mcp",
        name: "Local MCP",
        config: {},
        createdAt: timestamp,
        updatedAt: timestamp,
      },
      fake,
    );

    assert.equal(connector.enabled, true);
    assert.deepEqual(connector.scopes, []);
  });

  it("reports active DynamoDB table health", async () => {
    const fake = new FakeDynamo({
      Table: {
        TableName: "AdeleWeb",
        TableStatus: "ACTIVE",
        BillingModeSummary: { BillingMode: "PAY_PER_REQUEST" },
        ItemCount: 3,
      },
    });

    const health = await checkDynamoHealth(fake);

    assert.deepEqual(health, {
      ok: true,
      region: "us-east-1",
      tableName: "AdeleWeb",
      tableStatus: "ACTIVE",
      billingMode: "PAY_PER_REQUEST",
      itemCount: 3,
    });
  });
});
