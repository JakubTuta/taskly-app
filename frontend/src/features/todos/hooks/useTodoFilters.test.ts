import { act, renderHook } from '@testing-library/react'
import { expect, it } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import type { Todo } from '../types'
import { useTodoFilters } from './useTodoFilters'

const active: Todo = { ...todoFixture, id: 1, title: 'Plan the demo' }
const done: Todo = {
  ...todoFixture,
  id: 2,
  title: 'Book a room',
  priority: 'high',
  completed: true,
}
const urgent: Todo = {
  ...todoFixture,
  id: 3,
  title: 'Fix demo bug',
  priority: 'high',
}

it('shows every task newest first by default', () => {
  const { result } = renderHook(() => useTodoFilters([active, done, urgent]))
  expect(result.current).toMatchObject({
    filter: 'all',
    search: '',
    sort: 'newest',
  })
  expect(result.current.visible.map((todo) => todo.id)).toEqual([3, 2, 1])
})

it('applies status, search and sort changes to the visible tasks', () => {
  const { result } = renderHook(() => useTodoFilters([active, done, urgent]))
  act(() => result.current.setFilter('active'))
  expect(result.current.visible.map((todo) => todo.id)).toEqual([3, 1])
  act(() => result.current.setSearch('demo'))
  act(() => result.current.setSort('priority'))
  expect(result.current).toMatchObject({
    filter: 'active',
    search: 'demo',
    sort: 'priority',
  })
  expect(result.current.visible).toEqual([urgent, active])
})

it('recomputes the visible tasks when the source list changes', () => {
  const { result, rerender } = renderHook(
    ({ todos }) => useTodoFilters(todos),
    { initialProps: { todos: [active] } },
  )
  act(() => result.current.setFilter('completed'))
  expect(result.current.visible).toEqual([])
  rerender({ todos: [active, done] })
  expect(result.current.visible).toEqual([done])
})
