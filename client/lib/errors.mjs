export class KairosError extends Error {
  constructor(code) {
    super(/^[a-z0-9_]{1,80}$/.test(code) ? code : 'operation_failed');
    this.name = 'KairosError';
    this.code = this.message;
  }
}

export function fail(code) { throw new KairosError(code); }
export function diagnostic(error) {
  return error instanceof KairosError ? error.code : 'operation_failed';
}
