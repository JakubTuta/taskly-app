import { act, renderHook } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { createQueryWrapper } from '../../../test/queryClientWrapper'
import { todoFixture } from '../../../test/todoFixture'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'
import type { TodoInput } from '../types'
import { useCreateTodoMutation } from './useCreateTodoMutation'

vi.mock('../api/todos', () => ({ todosApi: { create: vi.fn() } }))
beforeEach(() => vi.clearAllMocks())

const input: TodoInput = {
  title: 'Write release notes',
  description: '',
  priority: 'high',
  due_date: null,
  completed: false,
}
const saved = { ...todoFixture, ...input, id: 8 }

it('creates the task and puts it first in the cached list', async () => {
  vi.mocked(todosApi.create).mockResolvedValue(saved)
  const { client, wrapper } = createQueryWrapper()
  client.setQueryData(todoKeys.list, [todoFixture])
  const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })
  await act(() => result.current.mutateAsync(input))
  expect(todosApi.create).toHaveBeenCalledWith(input)
  expect(client.getQueryData(todoKeys.list)).toEqual([saved, todoFixture])
})

it('does not duplicate a task that a refetch already added', async () => {
  vi.mocked(todosApi.create).mockResolvedValue(saved)
  const { client, wrapper } = createQueryWrapper()
  client.setQueryData(todoKeys.list, [
    todoFixture,
    { ...saved, title: 'Stale' },
  ])
  const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })
  await act(() => result.current.mutateAsync(input))
  expect(client.getQueryData(todoKeys.list)).toEqual([saved, todoFixture])
})

it('starts the list cache when nothing was loaded yet', async () => {
  vi.mocked(todosApi.create).mockResolvedValue(saved)
  const { client, wrapper } = createQueryWrapper()
  const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })
  await act(() => result.current.mutateAsync(input))
  expect(client.getQueryData(todoKeys.list)).toEqual([saved])
})

it('cancels in-flight list requests before writing the confirmed task', async () => {
  vi.mocked(todosApi.create).mockResolvedValue(saved)
  const { client, wrapper } = createQueryWrapper()
  const cancel = vi.spyOn(client, 'cancelQueries')
  const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })
  await act(() => result.current.mutateAsync(input))
  expect(cancel).toHaveBeenCalledWith({ queryKey: todoKeys.list })
})

it('leaves the cache untouched when creation fails', async () => {
  vi.mocked(todosApi.create).mockRejectedValue(new Error('Invalid task'))
  const { client, wrapper } = createQueryWrapper()
  client.setQueryData(todoKeys.list, [todoFixture])
  const { result } = renderHook(() => useCreateTodoMutation(), { wrapper })
  await act(() =>
    expect(result.current.mutateAsync(input)).rejects.toThrow('Invalid task'),
  )
  expect(client.getQueryData(todoKeys.list)).toEqual([todoFixture])
})
