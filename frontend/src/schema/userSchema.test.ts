import { userSchema } from './userSchema';
import type { User } from './userSchema';
import { FIXED_USER_CREATED_AT, makeUser } from '../test-utils/factories';

const REQUIRED_FIELDS: ReadonlyArray<{ field: keyof User; expected: string }> = [
  { field: 'user_id', expected: 'string' },
  { field: 'username', expected: 'string' },
  { field: 'display_name', expected: 'string' },
  { field: 'followers_count', expected: 'number' },
  { field: 'created_at', expected: 'date' },
];

/**
 * Every key `userSchema` declares, in declaration order.
 *
 * Stated as a literal rather than derived from the schema or from `REQUIRED_FIELDS`: a list computed from
 * either would agree with any change made to the schema, which is the drift this assertion exists to report.
 */
const DECLARED_KEYS = [
  'user_id',
  'username',
  'display_name',
  'followers_count',
  'created_at',
] as const;

/** A key no version of this schema has ever declared, used to probe unknown-key handling. */
const UNKNOWN_KEY = 'email';

/**
 * A shallow copy of `user` with one key removed. `user` itself is left intact.
 *
 * @param user - The builder result to copy; never modified.
 * @param field - The single key to drop from the copy.
 * @returns The copy, typed loosely because it no longer satisfies `User`.
 */
function withoutField(user: User, field: keyof User): Record<string, unknown> {
  const candidate: Record<string, unknown> = { ...user };
  delete candidate[field];
  return candidate;
}

describe('src/schema/userSchema.ts — userSchema', () => {
  it('declares exactly the five documented keys, and no others', () => {
    expect(Object.keys(userSchema.shape)).toEqual([...DECLARED_KEYS]);
    expect(Object.keys(userSchema.shape)).toHaveLength(DECLARED_KEYS.length);
  });

  it('strips an unknown key rather than rejecting it, because the object is not .strict()', () => {
    const withUnknownKey = { ...makeUser(), [UNKNOWN_KEY]: 'skeptic@example.invalid' };

    const result = userSchema.safeParse(withUnknownKey);

    // Accepted: a plain `z.object(...)` reports no issue for a key it does not declare.
    expect(result.success).toBe(true);

    // Narrows the parse result; unreachable, because the assertion above throws when it does not hold.
    if (!result.success) {
      return;
    }

    // And the key is absent from the output, so the parsed value carries the five declared keys only.
    expect(Object.keys(result.data)).toEqual([...DECLARED_KEYS]);
    expect(result.data).not.toHaveProperty(UNKNOWN_KEY);
  });

  it('accepts the user makeUser() builds, returning all five fields unchanged', () => {
    const parsed = userSchema.parse(makeUser());

    expect(parsed).toEqual({
      user_id: 'user-1',
      username: 'skeptic_dev',
      display_name: 'Skeptic Dev',
      followers_count: 1234,
      created_at: new Date(FIXED_USER_CREATED_AT),
    });

    expect(parsed.created_at).toBeInstanceOf(Date);
    expect(parsed.created_at.toISOString()).toBe(FIXED_USER_CREATED_AT);
  });

  it.each(REQUIRED_FIELDS)(
    'rejects a user with no $field, reporting one invalid_type issue on that path',
    ({ field, expected }) => {
      const result = userSchema.safeParse(withoutField(makeUser(), field));

      expect(result.success).toBe(false);

      if (result.success) {
        return;
      }

      expect(result.error.issues).toHaveLength(1);
      expect(result.error.issues[0]).toMatchObject({
        code: 'invalid_type',
        path: [field],
        expected,
        received: 'undefined',
      });
    },
  );

  it('rejects a user whose created_at is an ISO string rather than a Date', () => {
    const result = userSchema.safeParse({ ...makeUser(), created_at: FIXED_USER_CREATED_AT });

    expect(result.success).toBe(false);

    if (result.success) {
      return;
    }

    expect(result.error.issues).toHaveLength(1);
    expect(result.error.issues[0]).toMatchObject({
      code: 'invalid_type',
      path: ['created_at'],
      expected: 'date',
      received: 'string',
    });
  });
});
