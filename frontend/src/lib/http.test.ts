import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { todoFixture } from '../test/todoFixture'
import { request } from './http'

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status })
}

it('prefixes the API path, sends JSON headers and returns the parsed body', async () => {
  fetchMock.mockResolvedValue(jsonResponse(200, [todoFixture]))
  await expect(
    request('/todos', {
      method: 'POST',
      body: '{}',
      headers: { 'X-Request-Id': 'abc' },
    }),
  ).resolves.toEqual([todoFixture])
  expect(fetchMock).toHaveBeenCalledWith('/api/todos', {
    method: 'POST',
    body: '{}',
    headers: { 'Content-Type': 'application/json', 'X-Request-Id': 'abc' },
  })
})

it('sends JSON headers when no options are given', async () => {
  fetchMock.mockResolvedValue(jsonResponse(200, []))
  await request('/todos')
  expect(fetchMock).toHaveBeenCalledWith('/api/todos', {
    headers: { 'Content-Type': 'application/json' },
  })
})

it('resolves to undefined for 204 responses', async () => {
  fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
  await expect(
    request<void>('/todos/7', { method: 'DELETE' }),
  ).resolves.toBeUndefined()
})

it('reports a connection problem when the request cannot be sent', async () => {
  fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
  await expect(request('/todos')).rejects.toThrow(
    'Cannot connect to the server. Please try again.',
  )
})

it('rethrows the original error when the request was aborted', async () => {
  const controller = new AbortController()
  controller.abort()
  const abortError = new DOMException('Aborted', 'AbortError')
  fetchMock.mockRejectedValue(abortError)
  await expect(request('/todos', { signal: controller.signal })).rejects.toBe(
    abortError,
  )
})

it('explains validation failures without exposing raw server details', async () => {
  fetchMock.mockResolvedValue(
    jsonResponse(422, {
      detail: [{ loc: ['body', 'title'], msg: 'too long' }],
    }),
  )
  await expect(request('/todos')).rejects.toThrow(
    'Check the task details: title up to 120 characters, description up to 2000 characters, and a valid due date.',
  )
})

it('uses the server message when the error detail is text', async () => {
  fetchMock.mockResolvedValue(jsonResponse(404, { detail: 'Task not found.' }))
  await expect(request('/todos/404')).rejects.toThrow('Task not found.')
})

it.each([
  ['a structured detail', () => jsonResponse(500, { detail: [{ msg: 'x' }] })],
  [
    'a non-JSON body',
    () => new Response('<html>Bad gateway</html>', { status: 502 }),
  ],
])('falls back to a generic message for %s', async (_, makeResponse) => {
  fetchMock.mockResolvedValue(makeResponse())
  await expect(request('/todos')).rejects.toThrow(
    'The operation failed. Please try again.',
  )
})
