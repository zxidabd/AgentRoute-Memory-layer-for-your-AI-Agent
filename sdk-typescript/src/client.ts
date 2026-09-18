/**
 * Main client entry point for the MemoryBrain TypeScript SDK.
 */

import { HTTPClient, HTTPClientConfig } from "./http";
import { MemoryResource, StoreMemoryParams, RecallMemoryParams, DeleteMemoryParams } from "./memory";

export interface MemoryBrainConfig {
  apiKey?: string;
  baseUrl?: string;
  timeout?: number;
  maxRetries?: number;
}

export class MemoryBrain {
  public memories: MemoryResource;
  private http: HTTPClient;

  constructor(config?: MemoryBrainConfig | string) {
    let resolvedConfig: HTTPClientConfig;

    if (typeof config === "string") {
      resolvedConfig = { apiKey: config };
    } else {
      const key = config?.apiKey || (typeof process !== "undefined" ? process.env?.MEMORYBRAIN_API_KEY : "");
      if (!key) {
        throw new Error("MemoryBrain API key required. Pass { apiKey: 'mb_...' } or set process.env.MEMORYBRAIN_API_KEY.");
      }
      resolvedConfig = {
        apiKey: key,
        baseUrl: config?.baseUrl,
        timeout: config?.timeout,
        maxRetries: config?.maxRetries
      };
    }

    this.http = new HTTPClient(resolvedConfig);
    this.memories = new MemoryResource(this.http);
  }

  // -------------------------------------------------------------
  // Top-Level 2-Line Ergonomic Convenience Shortcuts
  // -------------------------------------------------------------

  async store(params: StoreMemoryParams): Promise<Record<string, any>> {
    return this.memories.store(params);
  }

  async recall(params: RecallMemoryParams): Promise<{
    userId: string;
    context: string;
    tokenCount: number;
    memoryCount: number;
    latencyMs?: number;
  }> {
    return this.memories.recall(params);
  }

  async delete(params: DeleteMemoryParams): Promise<Record<string, any>> {
    return this.memories.delete(params);
  }
}
