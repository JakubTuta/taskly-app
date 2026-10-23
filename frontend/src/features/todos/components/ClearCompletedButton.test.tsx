import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { ClearCompletedButton } from './ClearCompletedButton'

vi.mock('../../../design-system', () => import('../../../design-system/mocks'))
beforeEach(() => vi.clearAllMocks())

it('renders nothing when no task is completed', () => {
  const { container } = render(
    <ClearCompletedButton count={0} disabled={false} onClear={vi.fn()} />,
  )
  expect(container).toBeEmptyDOMElement()
})

it('shows the completed count and clears on click', async () => {
  const user = userEvent.setup()
  const onClear = vi.fn()
  render(<ClearCompletedButton count={3} disabled={false} onClear={onClear} />)
  await user.click(screen.getByRole('button', { name: 'Clear completed (3)' }))
  expect(onClear).toHaveBeenCalledTimes(1)
})

it('is disabled while another change is saving', async () => {
  const user = userEvent.setup()
  const onClear = vi.fn()
  render(<ClearCompletedButton count={2} disabled onClear={onClear} />)
  const button = screen.getByRole('button', { name: 'Clear completed (2)' })
  expect(button).toBeDisabled()
  await user.click(button)
  expect(onClear).not.toHaveBeenCalled()
})
