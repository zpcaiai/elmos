// Ambient declarations to ensure standalone compilation without external npm install

declare var process: {
  env: Record<string, string | undefined>;
};

declare var require: {
  main: unknown;
};

declare var module: unknown;

declare namespace NodeJS {
  type Timeout = any;
}

declare module 'crypto' {
  export interface Hmac {
    update(data: string): Hmac;
    digest(encoding: string): string;
  }
  export function createHmac(algorithm: string, key: string): Hmac;
}

declare module '@nestjs/common' {
  export function Controller(prefix?: string): ClassDecorator;
  export function Get(path?: string): MethodDecorator;
  export function Post(path?: string): MethodDecorator;
  export function Put(path?: string): MethodDecorator;
  export function Patch(path?: string): MethodDecorator;
  export function Delete(path?: string): MethodDecorator;
  export function Body(): ParameterDecorator;
  export function Param(param?: string): ParameterDecorator;
  export function Query(param?: string): ParameterDecorator;
  export function Headers(header?: string): ParameterDecorator;
  export function UseGuards(...guards: any[]): MethodDecorator & ClassDecorator;
  export function Injectable(): ClassDecorator;
  export function Module(metadata: {
    controllers?: any[];
    providers?: any[];
    imports?: any[];
    exports?: any[];
  }): ClassDecorator;

  export interface CanActivate {
    canActivate(context: ExecutionContext): boolean | Promise<boolean>;
  }

  export interface ExecutionContext {
    switchToHttp(): {
      getRequest<T = any>(): T;
      getResponse<T = any>(): T;
    };
  }

  export class UnauthorizedException extends Error {
    constructor(message?: string);
  }

  export class NotFoundException extends Error {
    constructor(message?: string);
  }

  export class BadRequestException extends Error {
    constructor(message?: string);
  }
}

declare module '@nestjs/core' {
  export class NestFactory {
    static create(module: any): Promise<{
      enableCors(): void;
      listen(port: number | string): Promise<void>;
    }>;
  }
}

// Test runner ambient definitions (Jest)
declare function describe(name: string, fn: () => void): void;
declare function it(name: string, fn: () => void | Promise<void>): void;
declare function beforeEach(fn: () => void | Promise<void>): void;
declare function expect(actual: any): {
  toBe(expected: any): void;
  toEqual(expected: any): void;
  toHaveLength(expected: number): void;
  toBeGreaterThan(expected: number): void;
  toBeGreaterThanOrEqual(expected: number): void;
  toBeLessThan(expected: number): void;
  toBeUndefined(): void;
  toBeDefined(): void;
  toBeNull(): void;
  toBeTruthy(): void;
  toBeFalsy(): void;
  not: {
    toBe(expected: any): void;
    toEqual(expected: any): void;
    toBeNull(): void;
    toBeUndefined(): void;
  };
};

