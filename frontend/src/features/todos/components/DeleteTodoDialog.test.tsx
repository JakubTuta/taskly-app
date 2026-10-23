import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { Button } from '../../../design-system'
import { todoFixture } from '../../../test/todoFixture'
import { useDeleteTodoMutation } from '../hooks/useDeleteTodoMutation'
import { DeleteTodoDialog } from './DeleteTodoDialog'

vi.mock('../../../design-system', () => import('../../../design-system/mocks'))
vi.mock('../hooks/useDeleteTodoMutation', () => ({
  useDeleteTodoMutation: vi.fn(),
}))
beforeEach(() => vi.clearAllMocks())

function mockDelete(overrides: Record<string, unknown> = {}) {
  const mutation = {
    isPending: false,
    error: null,
    mutateAsync: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
  vi.mocked(useDeleteTodoMutation).mockReturnValue(
    mutation as unknown as ReturnType<typeof useDeleteTodoMutation>,
  )
  return mutation
}

function renderDialog(busy = false) {
  const callbacks = { onClose: vi.fn(), onDeleted: vi.fn() }
  render(<DeleteTodoDialog todo={todoFixture} busy={busy} {...callbacks} />)
  return callbacks
}

it('shows a deletion error and allows cancelling without deleting', async () => {
  const user = userEvent.setup()
  const mutateAsync = vi.fn()
  vi.mocked(useDeleteTodoMutation).mockReturnValue({
    isPending: false,
    error: new Error('Could not delete.'),
    mutateAsync,
  } as unknown as ReturnType<typeof useDeleteTodoMutation>)
  const onClose = vi.fn()
  const onDeleted = vi.fn()
  render(
    <DeleteTodoDialog
      todo={todoFixture}
      busy={false}
      onClose={onClose}
      onDeleted={onDeleted}
    />,
  )
  expect(screen.getByRole('dialog', { name: 'Delete task?' })).toBeVisible()
  expect(
    screen.getByText(
      `The task “${todoFixture.title}” will be permanently deleted.`,
    ),
  ).toBeVisible()
  expect(screen.getByTestId('alert')).toHaveTextContent('Could not delete.')
  await user.click(screen.getByRole('button', { name: 'Cancel' }))
  expect(onClose).toHaveBeenCalledTimes(1)
  expect(mutateAsync).not.toHaveBeenCalled()
  expect(onDeleted).not.toHaveBeenCalled()
})

it('deletes the task and reports success', async () => {
  const user = userEvent.setup()
  const { mutateAsync } = mockDelete()
  const { onDeleted, onClose } = renderDialog()
  expect(screen.queryByTestId('alert')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Delete task' }))
  await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1))
  expect(mutateAsync).toHaveBeenCalledWith(todoFixture.id)
  expect(onClose).not.toHaveBeenCalled()
})

it('stays open for a retry when deletion fails', async () => {
  const user = userEvent.setup()
  const { mutateAsync } = mockDelete({
    mutateAsync: vi.fn().mockRejectedValue(new Error('Could not delete.')),
  })
  const { onDeleted } = renderDialog()
  await user.click(screen.getByRole('button', { name: 'Delete task' }))
  await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1))
  expect(onDeleted).not.toHaveBeenCalled()
  expect(screen.getByRole('dialog', { name: 'Delete task?' })).toBeVisible()
})

it.each([
  ['the page is busy', true, false],
  ['the deletion is pending', false, true],
])('locks the dialog while %s', async (_, busy, isPending) => {
  const { mutateAsync } = mockDelete({ isPending })
  const { onDeleted } = renderDialog(busy)
  expect(screen.getByRole('button', { name: 'Deleting…' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Close' })).toBeDisabled()
  const deleteButton = vi
    .mocked(Button)
    .mock.calls.map(([props]) => props)
    .find((props) => props.variant === 'danger')!
  await act(async () => deleteButton.onClick!({} as never))
  expect(mutateAsync).not.toHaveBeenCalled()
  expect(onDeleted).not.toHaveBeenCalled()
})
