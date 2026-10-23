import { render, screen } from '@testing-library/react'
import { QueryClient, useQueryClient } from '@tanstack/react-query'
import { useTheme } from 'styled-components'
import { beforeEach, expect, it, vi } from 'vitest'
import { GlobalStyles, theme } from '../design-system'
import { queryClient } from '../lib/queryClient'
import { AppProviders } from './AppProviders'

vi.mock('../design-system', () => import('../design-system/mocks'))
beforeEach(() => vi.clearAllMocks())

const seen: { client?: QueryClient; theme?: unknown } = {}

function Probe() {
  seen.client = useQueryClient()
  seen.theme = useTheme()
  return <p>Application content</p>
}

it('renders children with the given query client, theme and global styles', () => {
  const client = new QueryClient()
  render(
    <AppProviders client={client}>
      <Probe />
    </AppProviders>,
  )
  expect(screen.getByText('Application content')).toBeVisible()
  expect(seen.client).toBe(client)
  expect(seen.theme).toBe(theme)
  expect(GlobalStyles).toHaveBeenCalled()
})

it('uses the shared application query client by default', () => {
  render(
    <AppProviders>
      <Probe />
    </AppProviders>,
  )
  expect(seen.client).toBe(queryClient)
})
