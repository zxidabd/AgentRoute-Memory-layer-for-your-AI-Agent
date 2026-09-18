/**
 * Typed errors for the MemoryBrain TypeScript / JavaScript SDK.
 */

export class MemoryBrainError extends Error {
  public statusCode?: number;
  public code: string;
  public responseBody?: Record<string, any>;
  public requestId?: string;

  constructor(
    message: string,
    options?: {
      statusCode?: number;
      code?: string;
      responseBody?: Record<string, any>;
      requestId?: string;
    }
  ) {
    super(`[${options?.code || "UNKNOWN_ERROR"}] ${message}`);
    this.name = "MemoryBrainError";
    this.statusCode = options?.statusCode;
    this.code = options?.code || "UNKNOWN_ERROR";
    this.responseBody = options?.responseBody;
    this.requestId = options?.requestId;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class AuthError extends MemoryBrainError {
  constructor(message = "Invalid, expired, or revoked API key. Please check your MEMORYBRAIN_API_KEY.", options?: Record<string, any>) {
    super(message, { ...options, statusCode: 401, code: "AUTH_ERROR" });
    this.name = "AuthError";
  }
}

export class PermissionDeniedError extends MemoryBrainError {
  constructor(message = "Permission denied for this operation.", options?: Record<string, any>) {
    super(message, { ...options, statusCode: 403, code: "PERMISSION_DENIED" });
    this.name = "PermissionDeniedError";
  }
}

export class NotFoundError extends MemoryBrainError {
  constructor(message = "Resource not found.", options?: Record<string, any>) {
    super(message, { ...options, statusCode: 404, code: "NOT_FOUND" });
    this.name = "NotFoundError";
  }
}

export class QuotaExceededError extends MemoryBrainError {
  constructor(message = "Plan limit reached. Upgrade your subscription or enable overages in the dashboard.", options?: Record<string, any>) {
    super(message, { ...options, statusCode: 429, code: "QUOTA_EXCEEDED" });
    this.name = "QuotaExceededError";
  }
}

export class RateLimitError extends MemoryBrainError {
  constructor(message = "Rate limit exceeded. Please back off and retry.", options?: Record<string, any>) {
    super(message, { ...options, statusCode: 429, code: "RATE_LIMIT_EXCEEDED" });
    this.name = "RateLimitError";
  }
}

export class ServerError extends MemoryBrainError {
  constructor(message = "Internal server error. Our engineering team has been alerted.", options?: Record<string, any>) {
    super(message, { ...options, statusCode: options?.statusCode || 500, code: "SERVER_ERROR" });
    this.name = "ServerError";
  }
}
