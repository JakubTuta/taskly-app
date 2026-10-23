---
name: frontend-unit-tests
description: Conventions and patterns for Vitest + React Testing Library unit tests in the Taskly React/TypeScript frontend (components, TanStack Query hooks, API client, utilities). Use before creating or editing any *.test.ts(x) file under frontend/src.
when_to_use: Writing or updating frontend tests, testing React components, hooks, TanStack Query mutations, fetch wrappers or pure utilities.
---

# Frontend unit tests (Vitest + React Testing Library)

## Layout and style

- Co-located: `src/x/Thing.tsx` → `src/x/Thing.test.tsx`; `src/x/util.ts` → `src/x/util.test.ts`
  (use `.test.tsx` when the test needs JSX, e.g. a provider wrapper).
- Import test APIs explicitly: `import { beforeEach, describe, expect, it, vi } from 'vitest'`.
- Top-level `it(...)` blocks; `describe` only to group one function's cases. Names describe behaviour.
- Prettier style: no semicolons, single quotes, trailing commas. Format every file you touch:
  `node frontend/node_modules/prettier/bin/prettier.cjs --write <files>`.
- No comments. Strict TypeScript must pass (`run_tests.py --typecheck`); cast partial mocks with
  `as unknown as ReturnType<typeof useThing>` rather than `any`.
- Shared fixture: `src/test/todoFixture.ts` (`todoFixture`). Spread and override it per test.

## Isolation patterns used in this codebase

**Design system** — always replace it with the Vitest mocks (plain HTML elements, `vi.fn` components):

```tsx
vi.mock('../../../design-system', () => import('../../../design-system/mocks'))
beforeEach(() => vi.clearAllMocks())
```

The mocks render `Alert` as `data-testid="alert"`, `Drawer` as `role="dialog"` named by `title`,
`Input`/`Select` as a `<label>` wrapping the control (query with `getByLabelText`).

**Child components and hooks** — mock the module and read props from the mock to trigger callbacks:

```tsx
vi.mock('./components/TodoList', () => ({ TodoList: vi.fn(() => null) }))
const props = () => vi.mocked(TodoList).mock.lastCall![0]
act(() => props().onToggle(todoFixture))
```

```tsx
vi.mocked(useDeleteTodoMutation).mockReturnValue({
  isPending: false,
  error: null,
  mutateAsync,
} as unknown as ReturnType<typeof useDeleteTodoMutation>)
```

**TanStack Query hooks** — use a real `QueryClient` per test (`createQueryWrapper` from
`src/test/queryClientWrapper.tsx`, retries disabled) and mock only the API module:

```tsx
vi.mock('../api/todos', () => ({ todosApi: { create: vi.fn() } }))

it('puts the created task first in the cached list', async () => {
  vi.mocked(todosApi.create).mockResolvedValue(saved)
  const { client, wrapper } = createQueryWrapper()
  client.setQueryData(todoKeys.list, [todoFixture])
  const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })
  await act(() => result.current.mutateAsync(input))
  expect(client.getQueryData(todoKeys.list)).toEqual([saved, todoFixture])
})
```

For rejected mutations wrap the assertion: `await act(() => expect(result.current.mutateAsync(x)).rejects.toThrow('…'))`.

**`it.each` tables** — each row array is spread into arguments, so a row that *is* an array
(e.g. a query key) must be wrapped: `[['create', todoKeys.create], …]`.

**fetch** — `vi.stubGlobal('fetch', vi.fn())` with `new Response(JSON.stringify(body), { status })`;
`afterEach(() => vi.unstubAllGlobals())`.

**Time** — `vi.useFakeTimers()` / `vi.setSystemTime(new Date('2026-10-15T09:00:00'))`, advance with
`act(() => vi.advanceTimersByTime(ms))`, restore with `vi.useRealTimers()` in `afterEach`.
Never depend on the real current date.

**Interaction** — `const user = userEvent.setup()`; query by role, label or visible text
(`getByRole('button', { name: 'Save task' })`), assert with jest-dom (`toBeVisible`,
`toBeDisabled`, `toHaveValue`, `toHaveTextContent`). Use `waitFor` only for async effects.

## Checklist before running

- Each changed branch (ternaries, `&&` rendering, early returns, `catch` blocks) has a test.
- Assert what the user sees or what the callback/API receives — not implementation details.
- Busy/disabled and error states are covered alongside the happy path.
- Run with the `run-tests` skill: the file first, then `--suite frontend --coverage --typecheck --repeat 2`.
