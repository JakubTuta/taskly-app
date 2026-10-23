import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { SuccessNotice } from '../../components/SuccessNotice'
import { useNotice } from '../../hooks/useNotice'
import { todoFixture } from '../../test/todoFixture'
import { ClearCompletedButton } from './components/ClearCompletedButton'
import { DeleteTodoDialog } from './components/DeleteTodoDialog'
import { TodoEditor } from './components/TodoEditor'
import { TodoFilters } from './components/TodoFilters'
import { TodoList } from './components/TodoList'
import { TodosHeader } from './components/TodosHeader'
import { useClearCompletedMutation } from './hooks/useClearCompletedMutation'
import { useTodoFilters } from './hooks/useTodoFilters'
import { useTodosBusy } from './hooks/useTodosBusy'
import { useTodosQuery } from './hooks/useTodosQuery'
import { useUpdateTodoMutation } from './hooks/useUpdateTodoMutation'
import { TodosPage } from './TodosPage'
import type { Todo } from './types'

vi.mock('../../design-system', () => import('../../design-system/mocks'))
vi.mock('../../hooks/useNotice', () => ({ useNotice: vi.fn() }))
vi.mock('./hooks/useClearCompletedMutation', () => ({
  useClearCompletedMutation: vi.fn(),
}))
vi.mock('./components/ClearCompletedButton', () => ({
  ClearCompletedButton: vi.fn(() => null),
}))
vi.mock('./hooks/useTodoFilters', () => ({ useTodoFilters: vi.fn() }))
vi.mock('./hooks/useTodosBusy', () => ({ useTodosBusy: vi.fn() }))
vi.mock('./hooks/useTodosQuery', () => ({ useTodosQuery: vi.fn() }))
vi.mock('./hooks/useUpdateTodoMutation', () => ({
  useUpdateTodoMutation: vi.fn(),
}))
vi.mock('./components/TodosHeader', () => ({
  TodosHeader: vi.fn(() => <h1>Tasks</h1>),
}))
vi.mock('./components/TodoFilters', () => ({ TodoFilters: vi.fn(() => null) }))
vi.mock('./components/TodoList', () => ({
  TodoList: vi.fn(() => <p>Task list</p>),
}))
vi.mock('./components/TodoEditor', () => ({
  TodoEditor: vi.fn(() => <p>Task editor</p>),
}))
vi.mock('./components/DeleteTodoDialog', () => ({
  DeleteTodoDialog: vi.fn(() => <p>Delete dialog</p>),
}))
vi.mock('../../components/SuccessNotice', () => ({
  SuccessNotice: vi.fn(() => null),
}))
beforeEach(() => vi.clearAllMocks())

const completed: Todo = {
  ...todoFixture,
  id: 8,
  title: 'Ship it',
  completed: true,
}

function mockPage({
  query = {},
  toggle = {},
  clear = {},
  busy = false,
  message = '',
}: {
  query?: Record<string, unknown>
  toggle?: Record<string, unknown>
  clear?: Record<string, unknown>
  busy?: boolean
  message?: string
} = {}) {
  const page = {
    query: {
      data: [todoFixture, completed],
      isPending: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: vi.fn().mockResolvedValue(undefined),
      ...query,
    },
    toggle: {
      error: null,
      reset: vi.fn(),
      mutateAsync: vi.fn(),
      ...toggle,
    },
    clear: {
      error: null,
      reset: vi.fn(),
      mutateAsync: vi.fn(),
      ...clear,
    },
    notify: vi.fn(),
    filters: {
      filter: 'active' as const,
      search: 'demo',
      sort: 'due' as const,
      visible: [todoFixture],
      setFilter: vi.fn(),
      setSearch: vi.fn(),
      setSort: vi.fn(),
    },
  }
  vi.mocked(useTodosQuery).mockReturnValue(
    page.query as unknown as ReturnType<typeof useTodosQuery>,
  )
  vi.mocked(useUpdateTodoMutation).mockReturnValue(
    page.toggle as unknown as ReturnType<typeof useUpdateTodoMutation>,
  )
  vi.mocked(useClearCompletedMutation).mockReturnValue(
    page.clear as unknown as ReturnType<typeof useClearCompletedMutation>,
  )
  vi.mocked(useTodosBusy).mockReturnValue(busy)
  vi.mocked(useNotice).mockReturnValue({ message, notify: page.notify })
  vi.mocked(useTodoFilters).mockReturnValue(page.filters)
  return page
}

const listProps = () => vi.mocked(TodoList).mock.lastCall![0]
const headerProps = () => vi.mocked(TodosHeader).mock.lastCall![0]
const editorProps = () => vi.mocked(TodoEditor).mock.lastCall![0]
const deleteProps = () => vi.mocked(DeleteTodoDialog).mock.lastCall![0]

it('displays a query failure and resets mutation errors before retrying', async () => {
  const user = userEvent.setup()
  const refetch = vi.fn().mockResolvedValue(undefined)
  const reset = vi.fn()
  vi.mocked(useTodosQuery).mockReturnValue({
    data: [],
    isPending: false,
    isFetching: false,
    isError: true,
    error: new Error('The server is unavailable.'),
    refetch,
  } as unknown as ReturnType<typeof useTodosQuery>)
  vi.mocked(useUpdateTodoMutation).mockReturnValue({
    error: null,
    reset,
    mutateAsync: vi.fn(),
  } as unknown as ReturnType<typeof useUpdateTodoMutation>)
  const clearReset = vi.fn()
  vi.mocked(useClearCompletedMutation).mockReturnValue({
    error: null,
    reset: clearReset,
    mutateAsync: vi.fn(),
  } as unknown as ReturnType<typeof useClearCompletedMutation>)
  vi.mocked(useTodosBusy).mockReturnValue(false)
  vi.mocked(useNotice).mockReturnValue({ message: '', notify: vi.fn() })
  vi.mocked(useTodoFilters).mockReturnValue({
    filter: 'all',
    search: '',
    sort: 'newest',
    visible: [],
    setFilter: vi.fn(),
    setSearch: vi.fn(),
    setSort: vi.fn(),
  })
  render(<TodosPage />)
  expect(screen.getByTestId('alert')).toHaveTextContent(
    'The server is unavailable.',
  )
  await user.click(screen.getByRole('button', { name: 'Try again' }))
  await waitFor(() => expect(refetch).toHaveBeenCalledTimes(1))
  expect(reset).toHaveBeenCalledTimes(1)
  expect(clearReset).toHaveBeenCalledTimes(1)
  expect(reset.mock.invocationCallOrder[0]).toBeLessThan(
    refetch.mock.invocationCallOrder[0],
  )
})

it('wires filters and the visible tasks into the page sections', () => {
  const { filters, query } = mockPage({ message: 'Saved.' })
  render(<TodosPage />)
  expect(useTodoFilters).toHaveBeenCalledWith(query.data)
  expect(vi.mocked(TodoFilters).mock.lastCall![0]).toEqual({
    filter: 'active',
    search: 'demo',
    sort: 'due',
    onFilterChange: filters.setFilter,
    onSearchChange: filters.setSearch,
    onSortChange: filters.setSort,
  })
  expect(listProps()).toMatchObject({
    todos: [todoFixture],
    hasTodos: true,
    loading: false,
    failed: false,
    busy: false,
  })
  expect(headerProps().disabled).toBe(false)
  expect(vi.mocked(SuccessNotice).mock.lastCall![0]).toEqual({
    message: 'Saved.',
  })
  expect(screen.queryByTestId('alert')).not.toBeInTheDocument()
  expect(TodoEditor).not.toHaveBeenCalled()
  expect(DeleteTodoDialog).not.toHaveBeenCalled()
})

it('treats a pending first load as an empty, loading list', () => {
  mockPage({ query: { data: undefined, isPending: true } })
  render(<TodosPage />)
  expect(useTodoFilters).toHaveBeenCalledWith([])
  expect(listProps()).toMatchObject({ hasTodos: false, loading: true })
  expect(headerProps().disabled).toBe(true)
})

it('blocks creation and list actions while another change is saving', () => {
  mockPage({ busy: true })
  render(<TodosPage />)
  expect(headerProps().disabled).toBe(true)
  expect(listProps().busy).toBe(true)
})

it.each([
  [todoFixture, true, 'Another task complete. Well done!'],
  [completed, false, 'Task marked as active.'],
])(
  'toggles %#: sends the new state and announces the result',
  async (todo, nextCompleted, notice) => {
    const page = mockPage({
      toggle: {
        mutateAsync: vi
          .fn()
          .mockResolvedValue({ ...todo, completed: nextCompleted }),
      },
    })
    render(<TodosPage />)
    await act(async () => listProps().onToggle(todo))
    expect(page.toggle.mutateAsync).toHaveBeenCalledWith({
      id: todo.id,
      input: { completed: nextCompleted },
    })
    expect(page.notify).toHaveBeenCalledWith(notice)
  },
)

it('ignores toggles while another change is saving', async () => {
  const page = mockPage({ busy: true })
  render(<TodosPage />)
  await act(async () => listProps().onToggle(todoFixture))
  expect(page.toggle.mutateAsync).not.toHaveBeenCalled()
})

it('stays silent when a toggle fails so the mutation error can be shown', async () => {
  const page = mockPage({
    toggle: { mutateAsync: vi.fn().mockRejectedValue(new Error('Conflict')) },
  })
  render(<TodosPage />)
  await act(async () => listProps().onToggle(todoFixture))
  expect(page.notify).not.toHaveBeenCalled()
})

it('prefers the mutation error over the query error', () => {
  mockPage({
    query: { error: new Error('Load failed'), isError: true },
    toggle: { error: new Error('Toggle failed') },
  })
  render(<TodosPage />)
  expect(screen.getByTestId('alert')).toHaveTextContent('Toggle failed')
  expect(screen.getByTestId('alert')).not.toHaveTextContent('Load failed')
  expect(listProps().failed).toBe(true)
})

const clearProps = () => vi.mocked(ClearCompletedButton).mock.lastCall![0]

it('passes the completed count and busy state to the clear button', () => {
  mockPage({ busy: true })
  render(<TodosPage />)
  expect(clearProps()).toMatchObject({ count: 1, disabled: true })
})

it.each([
  [1, 'Cleared 1 completed task.'],
  [3, 'Cleared 3 completed tasks.'],
  [0, 'Cleared 0 completed tasks.'],
])(
  'clears completed tasks (%i) and announces the result',
  async (n, notice) => {
    const page = mockPage({
      clear: { mutateAsync: vi.fn().mockResolvedValue({ deleted: n }) },
    })
    render(<TodosPage />)
    await act(async () => clearProps().onClear())
    expect(page.clear.mutateAsync).toHaveBeenCalledTimes(1)
    expect(page.notify).toHaveBeenCalledWith(notice)
  },
)

it('ignores clearing while another change is saving', async () => {
  const page = mockPage({ busy: true })
  render(<TodosPage />)
  await act(async () => clearProps().onClear())
  expect(page.clear.mutateAsync).not.toHaveBeenCalled()
})

it('stays silent when clearing fails', async () => {
  const page = mockPage({
    clear: { mutateAsync: vi.fn().mockRejectedValue(new Error('Nope')) },
  })
  render(<TodosPage />)
  await act(async () => clearProps().onClear())
  expect(page.notify).not.toHaveBeenCalled()
})

it('shows the clear error when no toggle error exists', () => {
  mockPage({
    query: { error: new Error('Load failed') },
    clear: { error: new Error('Clear failed') },
  })
  render(<TodosPage />)
  expect(screen.getByTestId('alert')).toHaveTextContent('Clear failed')
})

it('resets the clear error when retrying', async () => {
  const user = userEvent.setup()
  const page = mockPage({ query: { error: new Error('Load failed') } })
  render(<TodosPage />)
  await user.click(screen.getByRole('button', { name: 'Try again' }))
  expect(page.clear.reset).toHaveBeenCalledTimes(1)
})

it.each([
  ['a refetch is running', true, false],
  ['a change is saving', false, true],
])('disables retry while %s', (_, isFetching, busy) => {
  mockPage({ busy, query: { error: new Error('Load failed'), isFetching } })
  render(<TodosPage />)
  expect(screen.getByRole('button', { name: 'Try again' })).toBeDisabled()
})

it.each([
  ['the header', () => headerProps().onCreate()],
  ['the empty list', () => listProps().onCreate()],
])('opens a new-task editor from %s', (_, create) => {
  mockPage()
  render(<TodosPage />)
  act(() => create())
  expect(screen.getByText('Task editor')).toBeVisible()
  expect(editorProps()).toMatchObject({ todo: 'new', busy: false })
})

it('edits a task, closes the editor after saving and announces it', () => {
  const page = mockPage()
  render(<TodosPage />)
  act(() => listProps().onEdit(todoFixture))
  expect(editorProps().todo).toBe(todoFixture)
  act(() => editorProps().onSaved('Changes saved.'))
  expect(screen.queryByText('Task editor')).not.toBeInTheDocument()
  expect(page.notify).toHaveBeenCalledWith('Changes saved.')
})

it('closes the editor without a notice when cancelled', () => {
  const page = mockPage()
  render(<TodosPage />)
  act(() => listProps().onEdit(todoFixture))
  act(() => editorProps().onClose())
  expect(screen.queryByText('Task editor')).not.toBeInTheDocument()
  expect(page.notify).not.toHaveBeenCalled()
})

it('confirms deletion and announces the deleted task', () => {
  const page = mockPage({ busy: false })
  render(<TodosPage />)
  act(() => listProps().onDelete(completed))
  expect(deleteProps()).toMatchObject({ todo: completed, busy: false })
  act(() => deleteProps().onDeleted())
  expect(screen.queryByText('Delete dialog')).not.toBeInTheDocument()
  expect(page.notify).toHaveBeenCalledWith('Task deleted.')
})

it('closes the delete confirmation without deleting', () => {
  const page = mockPage()
  render(<TodosPage />)
  act(() => listProps().onDelete(completed))
  act(() => deleteProps().onClose())
  expect(screen.queryByText('Delete dialog')).not.toBeInTheDocument()
  expect(page.notify).not.toHaveBeenCalled()
})
