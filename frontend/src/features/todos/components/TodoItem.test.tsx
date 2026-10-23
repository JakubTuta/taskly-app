import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Badge } from '../../../design-system'
import { todoFixture } from '../../../test/todoFixture'
import type { Todo } from '../types'
import { TodoItem } from './TodoItem'

vi.mock('../../../design-system', () => import('../../../design-system/mocks'))
beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(2026, 9, 15, 9, 0, 0))
})
afterEach(() => vi.useRealTimers())

function renderItem(overrides: Partial<Todo> = {}, busy = false) {
  const callbacks = { onEdit: vi.fn(), onToggle: vi.fn(), onDelete: vi.fn() }
  render(
    <TodoItem
      todo={{ ...todoFixture, ...overrides }}
      busy={busy}
      {...callbacks}
    />,
  )
  return callbacks
}

function badgeVariants() {
  return vi.mocked(Badge).mock.calls.map(([props]) => props.variant)
}

it('shows an active task and forwards edit requests', async () => {
  const user = userEvent.setup()
  const onEdit = vi.fn()
  const onToggle = vi.fn()
  const onDelete = vi.fn()
  render(
    <TodoItem
      todo={todoFixture}
      busy={false}
      onEdit={onEdit}
      onToggle={onToggle}
      onDelete={onDelete}
    />,
  )
  expect(screen.getByRole('heading', { name: todoFixture.title })).toBeVisible()
  expect(screen.getByText('To do')).toBeVisible()
  expect(screen.getByText('Medium')).toBeVisible()
  expect(screen.getByRole('checkbox')).not.toBeChecked()
  await user.click(
    screen.getByRole('button', { name: `Edit: ${todoFixture.title}` }),
  )
  expect(onEdit).toHaveBeenCalledTimes(1)
  expect(onToggle).not.toHaveBeenCalled()
  expect(onDelete).not.toHaveBeenCalled()
})

it('shows the id, description and priority of a task', () => {
  renderItem({ description: 'Line one\nLine two', priority: 'high' })
  expect(screen.getByText('#7')).toBeVisible()
  expect(screen.getByText(/Line one/)).toBeVisible()
  expect(screen.getByText('High')).toBeVisible()
  expect(badgeVariants()).toEqual(['info'])
})

it('shows a completed task with a toggle back to active', async () => {
  const user = userEvent.setup()
  const { onToggle } = renderItem({ completed: true })
  expect(screen.getByText('Completed')).toBeVisible()
  const checkbox = screen.getByRole('checkbox', {
    name: `Mark as active: ${todoFixture.title}`,
  })
  expect(checkbox).toBeChecked()
  await user.click(checkbox)
  expect(onToggle).toHaveBeenCalledTimes(1)
  expect(badgeVariants()).toContain('success')
})

it('completes an active task from its checkbox', async () => {
  const user = userEvent.setup()
  const { onToggle } = renderItem()
  await user.click(
    screen.getByRole('checkbox', { name: `Complete: ${todoFixture.title}` }),
  )
  expect(onToggle).toHaveBeenCalledTimes(1)
})

it('asks to delete the task from its delete button', async () => {
  const user = userEvent.setup()
  const { onDelete, onEdit } = renderItem()
  await user.click(
    screen.getByRole('button', { name: `Delete: ${todoFixture.title}` }),
  )
  expect(onDelete).toHaveBeenCalledTimes(1)
  expect(onEdit).not.toHaveBeenCalled()
})

it('shows an upcoming due date as a neutral badge', () => {
  renderItem({ due_date: '2026-10-20' })
  expect(screen.getByText('20 Oct 2026')).toBeVisible()
  expect(screen.queryByText(/overdue/)).not.toBeInTheDocument()
  expect(badgeVariants()).toEqual(['info', 'neutral'])
})

it('highlights an overdue active task', () => {
  renderItem({ due_date: '2026-10-10' })
  expect(screen.getByText(/10 Oct 2026/)).toHaveTextContent(
    '10 Oct 2026 · overdue',
  )
  expect(badgeVariants()).toEqual(['info', 'warning'])
})

it('does not mark a completed task as overdue', () => {
  renderItem({ due_date: '2026-10-10', completed: true })
  expect(screen.queryByText(/overdue/)).not.toBeInTheDocument()
  expect(badgeVariants()).toEqual(['success', 'neutral'])
})

it('disables every action while busy', () => {
  renderItem({}, true)
  expect(screen.getByRole('checkbox')).toBeDisabled()
  expect(
    screen.getByRole('button', { name: `Edit: ${todoFixture.title}` }),
  ).toBeDisabled()
  expect(
    screen.getByRole('button', { name: `Delete: ${todoFixture.title}` }),
  ).toBeDisabled()
})
