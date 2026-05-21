declare module "node:sqlite" {
  interface StatementResultingChanges {
    changes: number;
    lastInsertRowid: number | bigint;
  }

  interface StatementSync {
    all(...params: unknown[]): unknown[];
    get(...params: unknown[]): unknown;
    run(...params: unknown[]): StatementResultingChanges;
  }

  interface DatabaseSyncOptions {
    open?: boolean;
    readOnly?: boolean;
  }

  class DatabaseSync {
    constructor(location: string, options?: DatabaseSyncOptions);
    close(): void;
    prepare(sql: string): StatementSync;
    exec(sql: string): void;
  }

  export { DatabaseSync, StatementSync, DatabaseSyncOptions, StatementResultingChanges };
}
