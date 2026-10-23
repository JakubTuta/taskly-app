import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { TodoInput } from '../types'
import { TodoForm } from './TodoForm'

vi.mock('../../../design-system', () => import('../../../design-system/mocks'))

const existing: TodoInput = {
  title: 'Prepare a demo',
  description: 'Slides and script',
  priority: 'low',
  due_date: '2026-10-20',
  completed: true,
}

function renderForm(props: Partial<Parameters<typeof TodoForm>[0]> = {}) {
  const handlers = {
    onSubmit: vi.fn().mockResolvedValue(undefined),
    onCancel: vi.fn(),
  }
  render(<TodoForm busy={false} error={null} {...handlers} {...props} />)
  return handlers
}

describe('TodoForm', () => {
  it('rejects a whitespace-only title without submitting', async () => {
    const onSubmit = vi.fn()
    const user = userEvent.setup()
    render(
      <TodoForm
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        busy={false}
        error={null}
      />,
    )
    await user.type(screen.getByLabelText(/Task title/), '   ')
    await user.click(screen.getByRole('button', { name: 'Save task' }))
    expect(screen.getByText('Enter a task title.')).toBeVisible()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('submits trimmed values and the selected priority', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(
      <TodoForm
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        busy={false}
        error={null}
      />,
    )
    await user.type(screen.getByLabelText(/Task title/), '  Prepare a demo  ')
    await user.selectOptions(screen.getByLabelText('Priority'), 'high')
    await user.click(screen.getByRole('button', { name: 'Save task' }))
    expect(onSubmit).toHaveBeenCalledWith({
      title: 'Prepare a demo',
      description: '',
      priority: 'high',
      due_date: null,
      completed: false,
    })
  })

  it('starts from an existing task and submits the edited values', async () => {
    const user = userEvent.setup()
    const { onSubmit } = renderForm({ initial: existing })
    expect(screen.getByLabelText(/Task title/)).toHaveValue('Prepare a demo')
    expect(screen.getByLabelText('Description (optional)')).toHaveValue(
      'Slides and script',
    )
    expect(screen.getByLabelText('Priority')).toHaveValue('low')
    expect(screen.getByLabelText('Due date (optional)')).toHaveValue(
      '2026-10-20',
    )
    const description = screen.getByLabelText('Description (optional)')
    await user.clear(description)
    await user.type(description, '  Only slides  ')
    fireEvent.change(screen.getByLabelText('Due date (optional)'), {
      target: { value: '' },
    })
    await user.click(screen.getByRole('button', { name: 'Save task' }))
    expect(onSubmit).toHaveBeenCalledWith({
      ...existing,
      description: 'Only slides',
      due_date: null,
    })
  })

  it('submits a chosen due date', async () => {
    const user = userEvent.setup()
    const { onSubmit } = renderForm()
    await user.type(screen.getByLabelText(/Task title/), 'Book a room')
    fireEvent.change(screen.getByLabelText('Due date (optional)'), {
      target: { value: '2026-11-03' },
    })
    await user.click(screen.getByRole('button', { name: 'Save task' }))
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Book a room', due_date: '2026-11-03' }),
    )
  })

  it('shows every validation error and clears them after a valid submit', async () => {
    const user = userEvent.setup()
    const { onSubmit } = renderForm({
      initial: {
        ...existing,
        title: 'x'.repeat(121),
        description: 'y'.repeat(2001),
      },
    })
    await user.click(screen.getByRole('button', { name: 'Save task' }))
    expect(
      screen.getByText('The title must be at most 120 characters.'),
    ).toBeVisible()
    expect(
      screen.getByText('The description must be at most 2000 characters.'),
    ).toBeVisible()
    expect(onSubmit).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText(/Task title/), {
      target: { value: 'Short title' },
    })
    fireEvent.change(screen.getByLabelText(/Description/), {
      target: { value: 'Short description' },
    })
    await user.click(screen.getByRole('button', { name: 'Save task' }))
    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(
      screen.queryByText('The title must be at most 120 characters.'),
    ).not.toBeInTheDocument()
  })

  it('shows the server error passed by the editor', () => {
    renderForm({ error: 'Task not found.' })
    expect(screen.getByTestId('alert')).toHaveTextContent('Task not found.')
  })

  it('locks the form while saving', () => {
    renderForm({ busy: true })
    expect(screen.getByLabelText(/Task title/)).toBeDisabled()
    expect(screen.getByLabelText('Priority')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  })

  it('cancels without submitting', async () => {
    const user = userEvent.setup()
    const { onSubmit, onCancel } = renderForm({ initial: existing })
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onSubmit).not.toHaveBeenCalled()
  })
})
