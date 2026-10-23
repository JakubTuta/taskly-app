import { act, renderHook } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { createQueryWrapper } from '../../../test/queryClientWrapper'
import { todoFixture } from '../../../test/todoFixture'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'
import { useUpdateTodoMutation } from './useUpdateTodoMutation'

vi.mock('../api/todos', () => ({ todosApi: { update: vi.fn() } }))
beforeEach(() => vi.clearAllMocks())

const other = { ...todoFixture, id: 8, title: 'Other task' }
const saved = { ...todoFixture, completed: true }

it('updates the task and replaces it in the cached list in place', async () => {
  vi.mocked(todosApi.update).mockResolvedValue(saved)
  const { client, wrapper } = createQueryWrapper()
  client.setQueryData(todoKeys.list, [other, todoFixture])
  const { result } = renderHook(() => useUpdateTodoMutation(), { wrapper })
  await act(() =>
    result.current.mutateAsync({ id: 7, input: { completed: true } }),
  )
  expect(todosApi.update).toHaveBeenCalledWith(7, { completed: true })
  expect(client.getQueryData(todoKeys.list)).toEqual([other, saved])
})

it('does not create a list cache that was never loaded', async () => {
  vi.mocked(todosApi.update).mockResolvedValue(saved)
  const { client, wrapper } = createQueryWrapper()
  const { result } = renderHook(() => useUpdateTodoMutation(), { wrapper })
  await act(() =>
    result.current.mutateAsync({ id: 7, input: { completed: true } }),
  )
  expect(client.getQueryData(todoKeys.list)).toBeUndefined()
})

it('cancels in-flight list requests before writing the confirmed task', async () => {
  vi.mocked(todosApi.update).mockResolvedValue(saved)
  const { client, wrapper } = createQueryWrapper()
  const cancel = vi.spyOn(client, 'cancelQueries')
  const { result } = renderHook(() => useUpdateTodoMutation(), { wrapper })
  await act(() =>
    result.current.mutateAsync({ id: 7, input: { completed: true } }),
  )
  expect(cancel).toHaveBeenCalledWith({ queryKey: todoKeys.list })
})

it('keeps the cached task when the update fails', async () => {
  vi.mocked(todosApi.update).mockRejectedValue(new Error('Task not found.'))
  const { client, wrapper } = createQueryWrapper()
  client.setQueryData(todoKeys.list, [todoFixture])
  const { result } = renderHook(() => useUpdateTodoMutation(), { wrapper })
  await act(() =>
    expect(
      result.current.mutateAsync({ id: 7, input: { completed: true } }),
    ).rejects.toThrow('Task not found.'),
  )
  expect(client.getQueryData(todoKeys.list)).toEqual([todoFixture])
})
