import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useNotice } from './useNotice'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

it('starts without a notice and exposes a notification callback', () => {
  const { result } = renderHook(() => useNotice())
  expect(result.current.message).toBe('')
  expect(result.current.notify).toEqual(expect.any(Function))
})

it('shows a notice for four seconds', () => {
  const { result } = renderHook(() => useNotice())
  act(() => result.current.notify('Task created.'))
  expect(result.current.message).toBe('Task created.')
  act(() => vi.advanceTimersByTime(3999))
  expect(result.current.message).toBe('Task created.')
  act(() => vi.advanceTimersByTime(1))
  expect(result.current.message).toBe('')
})

it('restarts the timer for every notification, even with the same text', () => {
  const { result } = renderHook(() => useNotice())
  act(() => result.current.notify('Saved.'))
  act(() => vi.advanceTimersByTime(3000))
  act(() => result.current.notify('Saved.'))
  act(() => vi.advanceTimersByTime(3000))
  expect(result.current.message).toBe('Saved.')
  act(() => vi.advanceTimersByTime(1000))
  expect(result.current.message).toBe('')
})

it('replaces the current notice with a newer one', () => {
  const { result } = renderHook(() => useNotice())
  act(() => result.current.notify('Task created.'))
  act(() => result.current.notify('Task deleted.'))
  expect(result.current.message).toBe('Task deleted.')
})

it('keeps the notify callback stable between renders', () => {
  const { result, rerender } = renderHook(() => useNotice())
  const { notify } = result.current
  act(() => notify('Saved.'))
  rerender()
  expect(result.current.notify).toBe(notify)
})

it('cancels the pending timeout when unmounted', () => {
  const { result, unmount } = renderHook(() => useNotice())
  act(() => result.current.notify('Saved.'))
  expect(vi.getTimerCount()).toBe(1)
  unmount()
  expect(vi.getTimerCount()).toBe(0)
})
