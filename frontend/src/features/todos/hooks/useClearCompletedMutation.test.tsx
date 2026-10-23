import { act, renderHook } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { createQueryWrapper } from '../../../test/queryClientWrapper'
import { todoFixture } from '../../../test/todoFixture'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'
import { useClearCompletedMutation } from './useClearCompletedMutation'

vi.mock('../api/todos', () => ({ todosApi: { clearCompleted: vi.fn() } }))
beforeEach(() => vi.clearAllMocks())

const done = { ...todoFixture, id: 8, completed: true }

it('clears completed tasks and keeps only active ones cached', async () => {
  vi.mocked(todosApi.clearCompleted).mockResolvedValue({ deleted: 1 })
  const { client, wrapper } = createQueryWrapper()
  client.setQueryData(todoKeys.list, [todoFixture, done])
  const { result } = renderHook(() => useClearCompletedMutation(), { wrapper })
  await act(async () => {
    await expect(result.current.mutateAsync()).resolves.toEqual({ deleted: 1 })
  })
  expect(client.getQueryData(todoKeys.list)).toEqual([todoFixture])
})

it('does not create a list cache that was never loaded', async () => {
  vi.mocked(todosApi.clearCompleted).mockResolvedValue({ deleted: 0 })
  const { client, wrapper } = createQueryWrapper()
  const { result } = renderHook(() => useClearCompletedMutation(), { wrapper })
  await act(() => result.current.mutateAsync())
  expect(client.getQueryData(todoKeys.list)).toBeUndefined()
})

it('cancels in-flight list requests before updating the cache', async () => {
  vi.mocked(todosApi.clearCompleted).mockResolvedValue({ deleted: 1 })
  const { client, wrapper } = createQueryWrapper()
  const cancel = vi.spyOn(client, 'cancelQueries')
  const { result } = renderHook(() => useClearCompletedMutation(), { wrapper })
  await act(() => result.current.mutateAsync())
  expect(cancel).toHaveBeenCalledWith({ queryKey: todoKeys.list })
})

it('keeps completed tasks cached when clearing fails', async () => {
  vi.mocked(todosApi.clearCompleted).mockRejectedValue(
    new Error('Could not clear.'),
  )
  const { client, wrapper } = createQueryWrapper()
  client.setQueryData(todoKeys.list, [todoFixture, done])
  const { result } = renderHook(() => useClearCompletedMutation(), { wrapper })
  await act(() =>
    expect(result.current.mutateAsync()).rejects.toThrow('Could not clear.'),
  )
  expect(client.getQueryData(todoKeys.list)).toEqual([todoFixture, done])
})
