import { z } from "zod";

export const demoUserIdSchema = z.string().min(1).default("demo-user");

export const routeStatusSchema = z.object({
  area: z.enum(["dashboard", "memory", "tasks", "connectors", "browser", "settings"]),
  ready: z.boolean(),
});

export type RouteStatus = z.infer<typeof routeStatusSchema>;
