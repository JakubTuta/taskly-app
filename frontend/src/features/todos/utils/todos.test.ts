import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { formatDate, isOverdue, selectTodos, validateTodo } from './todos'
import type { Todo, TodoInput } from '../types'

const base: Todo = {
  id: 1,
  title: 'Sprint plan',
  description: '',
  priority: 'medium',
  completed: false,
  due_date: null,
  created_at: '2026-10-01T12:00:00Z',
  updated_at: '2026-10-01T12:00:00Z',
}

const input: TodoInput = {
  title: 'Sprint plan',
  description: '',
  priority: 'medium',
  due_date: null,
  completed: false,
}

describe('selectTodos', () => {
  it('combines status with a case-insensitive search in the description', () => {
    const matching = { ...base, description: 'Discuss the API' }
    const todos = [
      matching,
      { ...matching, id: 2, completed: true },
      { ...base, id: 3 },
    ]
    expect(selectTodos(todos, 'active', ' api ', 'newest')).toEqual([matching])
  })

  it('sorts by priority without changing the source array', () => {
    const high: Todo = { ...base, id: 2, priority: 'high' }
    const todos = [base, high]
    expect(selectTodos(todos, 'all', '', 'priority')).toEqual([high, base])
    expect(todos).toEqual([base, high])
  })

  it('keeps only completed tasks and matches the title', () => {
    const done = { ...base, id: 2, title: 'Release NOTES', completed: true }
    const todos = [base, done, { ...done, id: 3, title: 'Retro' }]
    expect(selectTodos(todos, 'completed', 'notes', 'newest')).toEqual([done])
  })

  it('breaks priority ties by showing the newer id first', () => {
    const low: Todo = { ...base, id: 5, priority: 'low' }
    const first = { ...base, id: 2 }
    const second = { ...base, id: 4 }
    expect(
      selectTodos([low, first, second], 'all', '', 'priority').map((t) => t.id),
    ).toEqual([4, 2, 5])
  })

  it('sorts by due date with undated tasks last and ties by newer id', () => {
    const later = { ...base, id: 2, due_date: '2026-11-01' }
    const sooner = { ...base, id: 3, due_date: '2026-10-20' }
    const soonerNewer = { ...base, id: 4, due_date: '2026-10-20' }
    const undated = { ...base, id: 5 }
    const undatedNewer = { ...base, id: 6 }
    expect(
      selectTodos(
        [undated, later, undatedNewer, sooner, soonerNewer],
        'all',
        '',
        'due',
      ).map((t) => t.id),
    ).toEqual([4, 3, 2, 6, 5])
  })

  it('sorts newest first by creation time and ties by newer id', () => {
    const older = { ...base, id: 9, created_at: '2026-09-01T08:00:00Z' }
    const newer = { ...base, id: 2, created_at: '2026-10-02T08:00:00Z' }
    const sameTime = { ...base, id: 3 }
    expect(
      selectTodos([older, base, newer, sameTime], 'all', '', 'newest').map(
        (t) => t.id,
      ),
    ).toEqual([2, 3, 1, 9])
  })
})

describe('validateTodo', () => {
  it('accepts a valid task', () => {
    expect(
      validateTodo({
        ...input,
        title: `  ${'x'.repeat(120)}  `,
        due_date: '2028-02-29',
      }),
    ).toEqual({})
  })

  it.each(['', '   '])('requires a title (%j)', (title) => {
    expect(validateTodo({ ...input, title })).toEqual({
      title: 'Enter a task title.',
    })
  })

  it('limits the title to 120 characters', () => {
    expect(validateTodo({ ...input, title: 'x'.repeat(121) })).toEqual({
      title: 'The title must be at most 120 characters.',
    })
  })

  it('limits the trimmed description to 2000 characters', () => {
    expect(
      validateTodo({ ...input, description: ` ${'x'.repeat(2000)} ` }),
    ).toEqual({})
    expect(validateTodo({ ...input, description: 'x'.repeat(2001) })).toEqual({
      description: 'The description must be at most 2000 characters.',
    })
  })

  it.each(['15/10/2026', '2026-1-5', '2026-13-01', '2026-02-30'])(
    'rejects the invalid due date %s',
    (due_date) => {
      expect(validateTodo({ ...input, due_date })).toEqual({
        due_date: 'Enter a valid date.',
      })
    },
  )

  it('reports every invalid field at once', () => {
    expect(
      Object.keys(
        validateTodo({
          ...input,
          title: ' ',
          description: 'x'.repeat(2001),
          due_date: 'soon',
        }),
      ),
    ).toEqual(['title', 'description', 'due_date'])
  })
})

describe('isOverdue', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 9, 15, 9, 0, 0))
  })
  afterEach(() => vi.useRealTimers())

  it.each([
    ['an active task due yesterday', { due_date: '2026-10-14' }, true],
    ['an active task due today', { due_date: '2026-10-15' }, false],
    ['an active task due tomorrow', { due_date: '2026-10-16' }, false],
    [
      'a completed task due yesterday',
      { due_date: '2026-10-14', completed: true },
      false,
    ],
    ['a task without a due date', {}, false],
  ])('treats %s accordingly', (_, overrides, expected) => {
    expect(isOverdue({ ...base, ...overrides })).toBe(expected)
  })

  it('compares against the local calendar day', () => {
    vi.setSystemTime(new Date(2026, 0, 1, 0, 30, 0))
    expect(isOverdue({ ...base, due_date: '2025-12-31' })).toBe(true)
    expect(isOverdue({ ...base, due_date: '2026-01-01' })).toBe(false)
  })
})

describe('formatDate', () => {
  it('formats an ISO date as a British short date', () => {
    expect(formatDate('2026-10-05')).toBe('5 Oct 2026')
    expect(formatDate('2026-12-31')).toBe('31 Dec 2026')
  })
})
