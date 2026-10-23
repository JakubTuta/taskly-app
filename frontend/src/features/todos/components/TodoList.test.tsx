import { render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import { TodoEmptyState } from './TodoEmptyState'
import { TodoItem } from './TodoItem'
import { TodoList } from './TodoList'

vi.mock('../../../design-system', () => import('../../../design-system/mocks'))
vi.mock('./TodoEmptyState', () => ({
  TodoEmptyState: vi.fn(() => <p>Empty task list</p>),
}))
vi.mock('./TodoItem', () => ({ TodoItem: vi.fn(() => <li>Task</li>) }))
beforeEach(() => vi.clearAllMocks())

function listProps(overrides = {}) {
  return {
    todos: [],
    hasTodos: false,
    loading: false,
    failed: false,
    busy: false,
    onCreate: vi.fn(),
    onToggle: vi.fn(),
    onEdit: vi.fn(),
    onDelete: vi.fn(),
    ...overrides,
  }
}

it('shows loading feedback before showing an empty list', () => {
  const props = {
    todos: [],
    hasTodos: false,
    failed: false,
    busy: false,
    onCreate: vi.fn(),
    onToggle: vi.fn(),
    onEdit: vi.fn(),
    onDelete: vi.fn(),
  }
  const { rerender } = render(<TodoList {...props} loading />)
  expect(screen.getByRole('status')).toHaveTextContent('Loading your tasks…')
  expect(screen.queryByText('Empty task list')).not.toBeInTheDocument()
  rerender(<TodoList {...props} loading={false} />)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  expect(screen.getByText('Empty task list')).toBeVisible()
})

it('explains that the list is unavailable when the first load failed', () => {
  render(<TodoList {...listProps({ failed: true })} />)
  expect(
    screen.getByRole('heading', {
      name: 'The task list is temporarily unavailable',
    }),
  ).toBeVisible()
  expect(screen.getByText('Try again to load your tasks.')).toBeVisible()
  expect(TodoEmptyState).not.toHaveBeenCalled()
})

it('keeps showing loaded tasks when a refresh fails', () => {
  render(
    <TodoList
      {...listProps({ failed: true, hasTodos: true, todos: [todoFixture] })}
    />,
  )
  expect(screen.getAllByRole('listitem')).toHaveLength(1)
  expect(
    screen.queryByText('The task list is temporarily unavailable'),
  ).not.toBeInTheDocument()
})

it('renders one item per task and binds each callback to its task', () => {
  const second = { ...todoFixture, id: 8, title: 'Second task' }
  const props = listProps({
    todos: [todoFixture, second],
    hasTodos: true,
    busy: true,
  })
  render(<TodoList {...props} />)
  expect(screen.getAllByRole('listitem')).toHaveLength(2)
  const items = vi.mocked(TodoItem).mock.calls.map(([itemProps]) => itemProps)
  expect(items.map((item) => [item.todo, item.busy])).toEqual([
    [todoFixture, true],
    [second, true],
  ])
  items[1].onToggle()
  items[1].onEdit()
  items[0].onDelete()
  expect(props.onToggle).toHaveBeenCalledWith(second)
  expect(props.onEdit).toHaveBeenCalledWith(second)
  expect(props.onDelete).toHaveBeenCalledWith(todoFixture)
})

it('passes filter state and creation to the empty state', () => {
  const props = listProps({ hasTodos: true, busy: true })
  render(<TodoList {...props} />)
  expect(vi.mocked(TodoEmptyState).mock.calls[0][0]).toEqual({
    hasTodos: true,
    disabled: true,
    onCreate: props.onCreate,
  })
})
