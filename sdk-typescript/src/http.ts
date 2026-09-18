/**
 * Zero-dependency HTTP client with exponential backoff retries and error parsing.
 */

import {
  MemoryBrainError,
  AuthError,
  PermissionDeniedError,
  NotFoundError,
  QuotaExceededError,
  RateLimitError,
  ServerError
} from "./errors";

export interface HTTPClientConfig {
  apiKey: string;
  baseUrl?: string;
  timeout?: number;
  maxRetries?: number;
  backoffFactor?: number;
}

export class HTTPClient {
  private apiKey: string;
  private baseUrl: string;
  private timeout: number;
  private maxRetries: number;
  private backoffFactor: number;

  constructor(config: HTTPClientConfig) {
    this.apiKey = config.apiKey.trim();
    this.baseUrl = (config.baseUrl || "https://api.memorybrain.ai").replace(/\/$/, "");
    this.timeout = config.timeout || 10000;
    this.maxRetries = config.maxRetries !== undefined ? config.maxRetries : 3;
    this.backoffFactor = config.backoffFactor || 0.5;
  }

  async request<T = any>(
    method: string,
    path: string,
    options?: {
      params?: Record<string, any>;
      body?: Record<string, any>;
      headers?: Record<string, string>;
    }
  ): Promise<T> {
    let url = `${this.baseUrl}${path}`;
    if (options?.params) {
      const searchParams = new URLSearchParams();
      for (const [k, v] of Object.entries(options.params)) {
        if (v !== undefined && v !== null) {
          searchParams.append(k, String(v));
        }
      }
      const qs = searchParams.toString();
      if (qs) url += `?${qs}`;
    }

    const reqHeaders: Record<string, string> = {
      Authorization: `Bearer ${this.apiKey}`,
      "Content-Type": "application/json",
      "User-Agent": "MemoryBrain-TypeScript-SDK/1.0.0",
      Accept: "application/json",
      ...options?.headers
    };

    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), this.timeout);

        const response = await fetch(url, {
          method,
          headers: reqHeaders,
          body: options?.body ? JSON.stringify(options.body) : undefined,
          signal: controller.signal
        });

        clearTimeout(timeoutId);
        const requestId = response.headers.get("x-request-id") || undefined;

        if (response.ok) {
          const text = await response.text();
          if (!text) return { status: "ok" } as unknown as T;
          return JSON.parse(text) as T;
        }

        const errText = await response.text();
        let parsedErr: any = {};
        try {
          parsedErr = JSON.parse(errText);
        } catch {}

        const msg = this.extractErrorMessage(parsedErr, errText, response.status);

        if (response.status === 401) {
          throw new AuthError(msg, { responseBody: parsedErr, requestId });
        }
        if (response.status === 403) {
          throw new PermissionDeniedError(msg, { responseBody: parsedErr, requestId });
        }
        if (response.status === 404) {
          throw new NotFoundError(msg, { responseBody: parsedErr, requestId });
        }
        if (response.status === 429) {
          const lower = msg.toLowerCase();
          if (lower.includes("limit reached") || lower.includes("quota") || lower.includes("upgrade") || lower.includes("frozen")) {
            throw new QuotaExceededError(msg, { responseBody: parsedErr, requestId });
          }
          if (attempt < this.maxRetries) {
            const sleepMs = this.backoffFactor * Math.pow(2, attempt) * 1000;
            await new Promise((r) => setTimeout(r, sleepMs));
            continue;
          }
          throw new RateLimitError(msg, { responseBody: parsedErr, requestId });
        }
        if (response.status >= 500) {
          lastError = new ServerError(msg, { statusCode: response.status, responseBody: parsedErr, requestId });
          if (attempt < this.maxRetries) {
            const sleepMs = this.backoffFactor * Math.pow(2, attempt) * 1000;
            await new Promise((r) => setTimeout(r, sleepMs));
            continue;
          }
          throw lastError;
        }

        throw new MemoryBrainError(msg, {
          statusCode: response.status,
          responseBody: parsedErr,
          requestId
        });
      } catch (err: any) {
        if (err instanceof MemoryBrainError) {
          throw err;
        }
        lastError = err;
        if (attempt < this.maxRetries) {
          const sleepMs = this.backoffFactor * Math.pow(2, attempt) * 1000;
          await new Promise((r) => setTimeout(r, sleepMs));
          continue;
        }
        throw new MemoryBrainError(`Network connection failed: ${err.message || String(err)}`);
      }
    }

    if (lastError) throw lastError;
    throw new MemoryBrainError("Request failed after retries.");
  }

  private extractErrorMessage(parsed: any, raw: string, status: number): string {
    if (parsed && typeof parsed === "object") {
      if (parsed.error?.message) return String(parsed.error.message);
      if (parsed.detail) return String(parsed.detail);
      if (parsed.message) return String(parsed.message);
    }
    return raw || `HTTP ${status} Error`;
  }
}
