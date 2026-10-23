import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { SuccessNotice } from '../../components/SuccessNotice'
import { useNotice } from '../../hooks/useNotice'
import { todoFixture } from '../../test/todoFixture'
import { DeleteTodoDialog } from './components/DeleteTodoDialog'
import { TodoEditor } from './components/TodoEditor'
import { TodoFilters } from './components/TodoFilters'
import { TodoList } from './components/TodoList'
import { TodosHeader } from './components/TodosHeader'
import { useTodoFilters } from './hooks/useTodoFilters'
import { useTodosBusy } from './hooks/useTodosBusy'
import { useTodosQuery } from './hooks/useTodosQuery'
import { useUpdateTodoMutation } from './hooks/useUpdateTodoMutation'
import { TodosPage } from './TodosPage'
import type { Todo } from './types'

vi.mock('../../design-system', () => import('../../design-system/mocks'))
vi.mock('../../hooks/useNotice', () => ({ useNotice: vi.fn() }))
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
  busy = false,
  message = '',
}: {
  query?: Record<string, unknown>
  toggle?: Record<string, unknown>
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
