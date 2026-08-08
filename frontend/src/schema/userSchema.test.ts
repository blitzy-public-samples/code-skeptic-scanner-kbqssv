/**
 * The suite that holds `./userSchema` to the five-field contract it declares, and holds the shared user
 * builder to that same contract.
 *
 * `makeUser()` in `../test-utils/factories` is the single definition point for user fixture data across the
 * frontend suite, and no other suite parses its output. This file is therefore the fixture-honesty gate for
 * that builder: the first test pushes the builder's output through the real `userSchema`, so a builder that
 * drifts from the schema fails here rather than silently weakening every suite that consumes it.
 *
 * The three groups below, and the behaviour each one pins:
 *
 * | Group                    | Behaviour pinned                                                          |
 * |--------------------------|---------------------------------------------------------------------------|
 * | builder round trip       | `makeUser()` satisfies `userSchema`, and parsing returns all five values  |
 * | one omission per field   | all five keys are required, so omitting any single one of them fails      |
 * | a wire-form `created_at` | `created_at` is `z.date()`, so an ISO string can never satisfy it         |
 *
 * Every test builds its own fixture from its own `makeUser()` call and mutates nothing outside itself, so the
 * tests are order-independent and the parametrised cases cannot corrupt one another. Nothing here issues a
 * request, reads a clock, or mocks a module: `created_at` comes from the builder's fixed ISO literal, so the
 * suite is wall-clock independent.
 *
 * Deliberately absent: an unknown-key case. `userSchema` is a plain `z.object(...)` with no `.strict()`, so
 * zod strips an unrecognised key and parsing succeeds - a test asserting rejection would assert a falsehood.
 * The `toEqual` in the first test pins that stripping behaviour, by requiring the parsed output to carry
 * exactly the five declared keys.
 *
 * @see frontend/src/schema/userSchema.ts - the module under test.
 * @see frontend/src/test-utils/factories.ts - `makeUser()` and the `FIXED_USER_CREATED_AT` literal.
 * @see frontend/TESTING.md - the factory contract this suite gates.
 * @see docs/testing/DECISION-LOG.md - the single source of truth for why this suite is shaped as it is.
 */

import { userSchema } from './userSchema';
import type { User } from './userSchema';
import { FIXED_USER_CREATED_AT, makeUser } from '../test-utils/factories';

/**
 * Every key `userSchema` declares, paired with the primitive zod names as `expected` when that key is absent.
 *
 * The list is exhaustive: no field in `userSchema` declares `.optional()`, `.nullable()` or a `.default()`,
 * so all five keys are required. `field` is typed `keyof User`, so this table cannot name a key the `User`
 * interface does not declare.
 */
const REQUIRED_FIELDS: ReadonlyArray<{ field: keyof User; expected: string }> = [
  { field: 'user_id', expected: 'string' },
  { field: 'username', expected: 'string' },
  { field: 'display_name', expected: 'string' },
  { field: 'followers_count', expected: 'number' },
  { field: 'created_at', expected: 'date' },
];

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
  it('accepts the user makeUser() builds, returning all five fields unchanged', () => {
    const parsed = userSchema.parse(makeUser());

    expect(parsed).toEqual({
      user_id: 'user-1',
      username: 'skeptic_dev',
      display_name: 'Skeptic Dev',
      followers_count: 1234,
      created_at: new Date(FIXED_USER_CREATED_AT),
    });

    // `created_at` survives parsing as a `Date` instance, at the instant the builder's literal names.
    expect(parsed.created_at).toBeInstanceOf(Date);
    expect(parsed.created_at.toISOString()).toBe(FIXED_USER_CREATED_AT);
  });

  it.each(REQUIRED_FIELDS)(
    'rejects a user with no $field, reporting one invalid_type issue on that path',
    ({ field, expected }) => {
      const result = userSchema.safeParse(withoutField(makeUser(), field));

      expect(result.success).toBe(false);

      // Narrows the parse result; unreachable, because the assertion above throws when it does not hold.
      if (result.success) {
        return;
      }

      // Exactly one issue: the omitted key is the only thing zod objects to, so the builder's other four
      // values are schema-valid.
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
    // The builder's own instant in wire form - the shape a raw JSON response carries. `z.date()` rejects it,
    // so no unparsed API payload can satisfy this schema.
    const result = userSchema.safeParse({ ...makeUser(), created_at: FIXED_USER_CREATED_AT });

    expect(result.success).toBe(false);

    // Narrows the parse result; unreachable, because the assertion above throws when it does not hold.
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
