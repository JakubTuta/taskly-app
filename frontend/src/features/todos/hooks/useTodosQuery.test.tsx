import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { createQueryWrapper } from '../../../test/queryClientWrapper'
import { todoFixture } from '../../../test/todoFixture'
import { todoKeys } from '../api/queryKeys'
import { todosApi } from '../api/todos'
import { useTodosQuery } from './useTodosQuery'

vi.mock('../api/todos', () => ({ todosApi: { list: vi.fn() } }))
beforeEach(() => vi.clearAllMocks())

it('loads tasks into the shared list cache with a cancellable request', async () => {
  vi.mocked(todosApi.list).mockResolvedValue([todoFixture])
  const { client, wrapper } = createQueryWrapper()
  const { result } = renderHook(() => useTodosQuery(), { wrapper })
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(result.current.data).toEqual([todoFixture])
  expect(client.getQueryData(todoKeys.list)).toEqual([todoFixture])
  expect(todosApi.list).toHaveBeenCalledTimes(1)
  expect(vi.mocked(todosApi.list).mock.calls[0][0]).toBeInstanceOf(AbortSignal)
})

it('exposes request failures', async () => {
  vi.mocked(todosApi.list).mockRejectedValue(new Error('Server down'))
  const { wrapper } = createQueryWrapper()
  const { result } = renderHook(() => useTodosQuery(), { wrapper })
  await waitFor(() => expect(result.current.isError).toBe(true))
  expect(result.current.error).toEqual(new Error('Server down'))
})
