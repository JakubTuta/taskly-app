import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import { useCreateTodoMutation } from '../hooks/useCreateTodoMutation'
import { useUpdateTodoMutation } from '../hooks/useUpdateTodoMutation'
import type { TodoInput } from '../types'
import { TodoEditor } from './TodoEditor'
import { TodoForm } from './TodoForm'

vi.mock('../../../design-system', () => import('../../../design-system/mocks'))
vi.mock('../hooks/useCreateTodoMutation', () => ({
  useCreateTodoMutation: vi.fn(),
}))
vi.mock('../hooks/useUpdateTodoMutation', () => ({
  useUpdateTodoMutation: vi.fn(),
}))
vi.mock('./TodoForm', () => ({
  TodoForm: vi.fn(
    ({ onSubmit }: { onSubmit: (input: TodoInput) => Promise<void> }) => (
      <button onClick={() => void onSubmit(todoFixture)}>Submit form</button>
    ),
  ),
}))
beforeEach(() => vi.clearAllMocks())

function mockMutations({
  create = {},
  update = {},
}: {
  create?: Record<string, unknown>
  update?: Record<string, unknown>
} = {}) {
  const mutations = {
    create: { isPending: false, error: null, mutateAsync: vi.fn(), ...create },
    update: { isPending: false, error: null, mutateAsync: vi.fn(), ...update },
  }
  vi.mocked(useCreateTodoMutation).mockReturnValue(
    mutations.create as unknown as ReturnType<typeof useCreateTodoMutation>,
  )
  vi.mocked(useUpdateTodoMutation).mockReturnValue(
    mutations.update as unknown as ReturnType<typeof useUpdateTodoMutation>,
  )
  return mutations
}

const formProps = () => vi.mocked(TodoForm).mock.lastCall![0]

it('creates a new task and reports a successful save', async () => {
  const user = userEvent.setup()
  const create = vi.fn().mockResolvedValue(todoFixture)
  const update = vi.fn()
  vi.mocked(useCreateTodoMutation).mockReturnValue({
    isPending: false,
    error: null,
    mutateAsync: create,
  } as unknown as ReturnType<typeof useCreateTodoMutation>)
  vi.mocked(useUpdateTodoMutation).mockReturnValue({
    isPending: false,
    error: null,
    mutateAsync: update,
  } as unknown as ReturnType<typeof useUpdateTodoMutation>)
  const onSaved = vi.fn()
  render(
    <TodoEditor todo="new" busy={false} onClose={vi.fn()} onSaved={onSaved} />,
  )
  expect(screen.getByRole('dialog', { name: 'New task' })).toBeVisible()
  await user.click(screen.getByRole('button', { name: 'Submit form' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith('New task added.'))
  expect(create).toHaveBeenCalledWith(todoFixture)
  expect(update).not.toHaveBeenCalled()
})

it('starts the form empty for a new task', () => {
  mockMutations()
  render(
    <TodoEditor todo="new" busy={false} onClose={vi.fn()} onSaved={vi.fn()} />,
  )
  expect(formProps()).toMatchObject({
    initial: undefined,
    busy: false,
    error: null,
  })
})

it('edits an existing task and reports the saved changes', async () => {
  const user = userEvent.setup()
  const { create, update } = mockMutations({
    update: { mutateAsync: vi.fn().mockResolvedValue(todoFixture) },
  })
  const onSaved = vi.fn()
  render(
    <TodoEditor
      todo={todoFixture}
      busy={false}
      onClose={vi.fn()}
      onSaved={onSaved}
    />,
  )
  expect(screen.getByRole('dialog', { name: 'Edit task' })).toBeVisible()
  expect(formProps().initial).toBe(todoFixture)
  await user.click(screen.getByRole('button', { name: 'Submit form' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledWith('Changes saved.'))
  expect(update.mutateAsync).toHaveBeenCalledWith({
    id: todoFixture.id,
    input: todoFixture,
  })
  expect(create.mutateAsync).not.toHaveBeenCalled()
})

it('keeps the editor open when saving fails', async () => {
  const user = userEvent.setup()
  const { update } = mockMutations({
    update: { mutateAsync: vi.fn().mockRejectedValue(new Error('Conflict')) },
  })
  const onSaved = vi.fn()
  render(
    <TodoEditor
      todo={todoFixture}
      busy={false}
      onClose={vi.fn()}
      onSaved={onSaved}
    />,
  )
  await user.click(screen.getByRole('button', { name: 'Submit form' }))
  await waitFor(() => expect(update.mutateAsync).toHaveBeenCalled())
  expect(onSaved).not.toHaveBeenCalled()
  expect(screen.getByRole('dialog', { name: 'Edit task' })).toBeVisible()
})

it('shows the error of the mutation that matches the editor mode', () => {
  mockMutations({
    create: { error: new Error('Create failed') },
    update: { error: new Error('Update failed') },
  })
  const { rerender } = render(
    <TodoEditor todo="new" busy={false} onClose={vi.fn()} onSaved={vi.fn()} />,
  )
  expect(formProps().error).toBe('Create failed')
  rerender(
    <TodoEditor
      todo={todoFixture}
      busy={false}
      onClose={vi.fn()}
      onSaved={vi.fn()}
    />,
  )
  expect(formProps().error).toBe('Update failed')
})

it.each([
  ['the page is busy', true, false],
  ['the save is pending', false, true],
])(
  'locks the form and ignores submissions while %s',
  async (_, busy, isPending) => {
    const user = userEvent.setup()
    const { update } = mockMutations({ update: { isPending } })
    const onSaved = vi.fn()
    render(
      <TodoEditor
        todo={todoFixture}
        busy={busy}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    )
    expect(formProps().busy).toBe(true)
    expect(screen.getByRole('button', { name: 'Close' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Submit form' }))
    expect(update.mutateAsync).not.toHaveBeenCalled()
    expect(onSaved).not.toHaveBeenCalled()
  },
)

it('closes from the drawer and from the form cancel action', async () => {
  const user = userEvent.setup()
  mockMutations()
  const onClose = vi.fn()
  render(
    <TodoEditor todo="new" busy={false} onClose={onClose} onSaved={vi.fn()} />,
  )
  await user.click(screen.getByRole('button', { name: 'Close' }))
  formProps().onCancel()
  expect(onClose).toHaveBeenCalledTimes(2)
})
