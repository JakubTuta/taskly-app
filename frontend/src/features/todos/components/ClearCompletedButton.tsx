import { Trash2 } from 'lucide-react'
import { Button } from '../../../design-system'

export function ClearCompletedButton({
  count,
  disabled,
  onClear,
}: {
  count: number
  disabled: boolean
  onClear: () => void
}) {
  if (!count) return null
  return (
    <Button variant="secondary" disabled={disabled} onClick={onClear}>
      <Trash2 size={16} aria-hidden="true" />
      Clear completed ({count})
    </Button>
  )
}
