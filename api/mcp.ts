import type { IncomingMessage, ServerResponse } from "node:http";
import { handleMcpRequest } from "../src/server.js";

export default async function handler(
  req: IncomingMessage & { body?: unknown },
  res: ServerResponse
): Promise<void> {
  await handleMcpRequest(req, res);
}
