import { describe, it, expect } from 'vitest'
import { cn } from './utils'

describe('cn()', () => {
  it('merges class names with clsx', () => {
    expect(cn('a', 'b')).toBe('a b')
  })

  it('filters falsy values', () => {
    expect(cn('a', false, null, undefined, 'b')).toBe('a b')
  })

  it('handles conditional objects', () => {
    expect(cn('base', { active: true, disabled: false })).toBe('base active')
  })

  it('resolves tailwind conflicts keeping the later class', () => {
    expect(cn('px-2', 'px-4')).toBe('px-4')
  })

  it('returns empty string for no inputs', () => {
    expect(cn()).toBe('')
  })
})
