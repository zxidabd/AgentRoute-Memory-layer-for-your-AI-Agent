/**
 * Memory resource implementation for TypeScript SDK.
 */

import { HTTPClient } from "./http";

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface StoreMemoryParams {
  userId: string;
  content?: string;
  messages?: ChatMessage[];
  category?: "FACT" | "PREFERENCE" | "DECISION" | "INSTRUCTION";
  metadata?: Record<string, any>;
  sync?: boolean;
}

export interface RecallMemoryParams {
  userId: string;
  query: string;
  limit?: number;
  tokenLimit?: number;
}

export interface DeleteMemoryParams {
  userId: string;
  memoryId?: string;
  purge?: boolean;
}

export interface ListMemoriesParams {
  userId: string;
  limit?: number;
  category?: string;
  status?: string;
  cursor?: string;
}

export class MemoryResource {
  constructor(private http: HTTPClient) {}

  async store(params: StoreMemoryParams): Promise<Record<string, any>> {
    const payload: Record<string, any> = { user_id: params.userId };

    if (params.messages && params.messages.length > 0) {
      payload.messages = params.messages;
    } else if (params.content) {
      payload.statement = params.content;
      payload.category = params.category || "FACT";
      payload.messages = [
        { role: "user", content: params.content },
        { role: "assistant", content: "Acknowledged and stored in memory." }
      ];
    } else {
      throw new Error("Either 'content' or 'messages' must be provided to store().");
    }

    if (params.metadata) {
      payload.metadata = params.metadata;
    }

    return this.http.request("POST", "/v1/memories", {
      params: params.sync ? { sync: "true" } : undefined,
      body: payload
    });
  }

  async recall(params: RecallMemoryParams): Promise<{
    userId: string;
    context: string;
    tokenCount: number;
    memoryCount: number;
    latencyMs?: number;
  }> {
    const payload = {
      user_id: params.userId,
      query: params.query,
      limit: params.limit ?? 5,
      token_limit: params.tokenLimit ?? 300
    };

    const res = await this.http.request("POST", "/v1/context", { body: payload });
    return {
      userId: res.user_id,
      context: res.context || "",
      tokenCount: res.token_count || 0,
      memoryCount: res.memory_count || 0,
      latencyMs: res.latency_ms
    };
  }

  async delete(params: DeleteMemoryParams): Promise<Record<string, any>> {
    if (params.memoryId) {
      return this.http.request("DELETE", `/v1/memories/${params.memoryId}`, {
        params: params.purge ? { purge: "true" } : undefined
      });
    } else {
      return this.http.request("DELETE", `/v1/users/${params.userId}/memories`);
    }
  }

  async list(params: ListMemoriesParams): Promise<Record<string, any>> {
    return this.http.request("GET", "/v1/memories", {
      params: {
        user_id: params.userId,
        limit: params.limit ?? 20,
        status: params.status || "ACTIVE",
        category: params.category,
        cursor: params.cursor
      }
    });
  }
}
